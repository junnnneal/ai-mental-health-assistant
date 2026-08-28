"""
FastAPI 入口。两类业务路由 + 管理端点：

  POST /chat       LangGraph Agent（AI健康管家）：astream_events(v2) 翻译成 SSE
                   token / tool_start / tool_end / done / error
  POST /rag/chat   咨询页 RAG 对话：服务端检索 top-k → 注入 system prompt →
                   LLM 直流式（不走 ReAct 图，无 tool 事件）
                   首事件额外发 citations（引用卡片数据），无命中则整帧省略
  POST /analyze    情绪分析（非流式）：逻辑逐字迁移自前端 useEmotionAnalysis
  POST /kb/rebuild 知识库强制重建（x-admin-token 保护）
  GET  /health     健康检查 + 知识库状态（保活 ping 也打这里）

启动时 lifespan 后台预热知识库（判空灌库），不阻塞服务就绪。
"""
import asyncio
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.errors import GraphRecursionError

import bm25
import config
import knowledge_base
import rag
import verify
from graph import agent
from llm import analyze_llm, rag_llm
from tools import user_token
from vector_store import get_vector_store


async def _warmup_kb():
    """启动预热：失败只打日志不炸启动，首次检索时会自动重试"""
    try:
        await knowledge_base.ensure_built()
        # BM25 词法索引顺带预热（本地分词+统计约 1s，放线程池不占事件循环），
        # 首条消息就不必现场建索引
        await asyncio.to_thread(bm25.get_index)
    except Exception as e:  # noqa: BLE001
        print(f"[启动] 知识库预热失败（将在首次检索时重试）：{e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_warmup_kb())
    yield
    task.cancel()


app = FastAPI(title="AI健康管家 Agent 服务", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # 生产走 Netlify 同源转发，这里主要服务本地直连调试
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _content_text(content) -> str:
    """模型返回的 content 可能是 str 也可能是分块 list（GLM 兼容协议两种都有）"""
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


def _history_messages(history: list, message: str):
    """[{role, content}] → LangChain 消息列表（截最近10条，与 /chat 同规则）"""
    msgs = []
    for h in (history or [])[-10:]:
        role, content = h.get("role"), str(h.get("content") or "")
        if not content:
            continue
        msgs.append(HumanMessage(content) if role == "user" else AIMessage(content))
    msgs.append(HumanMessage(message))
    return msgs


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = str(body.get("message") or "").strip()
    history = body.get("history") or []  # [{role, content}]，前端只传最近几轮

    if not message:
        return StreamingResponse(iter([_sse({"type": "error", "message": "消息不能为空"})]),
                                 media_type="text/event-stream")

    # 用户token透传：本轮Agent内所有工具调用都以该用户身份访问后端
    token = request.headers.get("token") or request.headers.get("authorization") or ""
    user_token.set(token.removeprefix("Bearer ").strip())

    msgs = _history_messages(history, message)

    async def event_stream():
        try:
            async for ev in agent.astream_events({"messages": msgs}, version="v2"):
                kind = ev["event"]

                if kind == "on_chat_model_stream":
                    delta = _content_text(ev["data"]["chunk"].content)
                    if delta:
                        yield _sse({"type": "token", "text": delta})

                elif kind == "on_tool_start":
                    yield _sse({
                        "type": "tool_start",
                        "name": ev["name"],
                        "args": ev["data"].get("input") or {},
                    })

                elif kind == "on_tool_end":
                    out = ev["data"].get("output")
                    # output是ToolMessage，取content本体而不是str()带壳的
                    result = getattr(out, "content", out)
                    yield _sse({
                        "type": "tool_end",
                        "name": ev["name"],
                        "result": str(result)[:500],
                    })

            yield _sse({"type": "done"})
        except GraphRecursionError:
            yield _sse({"type": "error", "message": "思考轮次过多，请换个更具体的问题"})
        except Exception as e:  # noqa: BLE001 —— SSE 里任何异常都要吐给前端而不是断流
            yield _sse({"type": "error", "message": f"Agent 执行出错：{e}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/rag/chat")
async def rag_chat(request: Request):
    """咨询页对话：检索 → citations 事件 → LLM 流式回答。不需要用户token。"""
    body = await request.json()
    message = str(body.get("message") or "").strip()
    history = body.get("history") or []

    if not message:
        return StreamingResponse(iter([_sse({"type": "error", "message": "消息不能为空"})]),
                                 media_type="text/event-stream")

    async def event_stream():
        try:
            # 知识库就绪等待3s软超时：冷启动撞上灌库时降级为无引用回答，绝不拖首字
            try:
                await asyncio.wait_for(knowledge_base.ensure_built(), timeout=3)
            except Exception:  # noqa: BLE001 —— 超时/失败都按无引用继续
                print("[RAG] 知识库3秒内未就绪，本条消息降级为无引用对话")

            citations = await rag.retrieve(message)
            # 指代型追问（"第二种方法是什么"）单看当前消息检索不到，而且未必是空结果——
            # 会模模糊糊命中"第二步怎么做"这种序数语义的无关块（非空但错，实测0.31）。
            # 所以触发线是"空结果 或 最高分 < RAG_RETRY_BELOW（弱命中）"，命中才拼上
            # 最近一条用户提问重检一次，重检分更高才替换。只在弱命中时花这次额外检索：
            # 独立完整的问题首轮高分通过，行为不变。不做"永远拼接"——历史话题会稀释
            # 当前问题的向量，独立问题反而被带偏。
            if history:
                top_score = max((c["score"] for c in citations), default=0.0)
                if top_score < config.RAG_RETRY_BELOW:
                    last_user = next(
                        (str(m.get("content") or "") for m in reversed(history) if m.get("role") == "user"),
                        "",
                    ).strip()
                    if last_user:
                        retry = await rag.retrieve(f"{last_user[:80]}\n{message}")
                        if retry and max(c["score"] for c in retry) > top_score:
                            citations = retry
            if citations:
                # 引用卡片数据前置下发：回答还没开始就能渲染来源
                yield _sse({
                    "type": "citations",
                    "citations": [
                        {
                            "index": c["index"],
                            "articleId": c["articleId"],
                            "articleTitle": c["articleTitle"],
                            "heading": c["heading"],
                            "score": c["score"],
                        }
                        for c in citations
                    ],
                })

            system_content = "\n\n".join(
                x for x in [rag.RAG_CHAT_SYSTEM_PROMPT, rag.build_rag_context(citations)] if x
            )
            msgs = [SystemMessage(content=system_content), *_history_messages(history, message)]

            answer_parts: list[str] = []
            async for chunk in rag_llm.astream(msgs):
                delta = _content_text(chunk.content)
                if delta:
                    answer_parts.append(delta)
                    yield _sse({"type": "token", "text": delta})
            # 生成后幻觉自检：必须在 done 之前发（前端收到 done 即断流）；
            # 仅在有引用且回答成形时做，任何失败静默跳过、照常 done
            answer = "".join(answer_parts).strip()
            if citations and config.RAG_VERIFY and len(answer) >= 30:
                v = await verify.verify_answer(citations, answer)
                if v:
                    yield _sse({"type": "verify", **v})
            yield _sse({"type": "done"})
        except Exception as e:  # noqa: BLE001 —— SSE 里任何异常都要吐给前端而不是断流
            yield _sse({"type": "error", "message": f"RAG 对话出错：{e}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------- 情绪分析（原 useEmotionAnalysis 逐字迁移） ----------------

ANALYZE_SYSTEM_PROMPT = "\n".join([
    "你是心理咨询师的情绪分析助手。分析用户与AI助手的对话，判断用户当前的情绪状态。",
    "只输出一个JSON对象，不要输出任何其他文字、解释或markdown代码块，字段如下：",
    "{",
    '  "primaryEmotion": "主要情绪，一到两个词，如：焦虑、低落、平静、开心",',
    '  "emotionScore": 0到100的整数，表示情绪强度（越强烈越高，与正面负面无关）,',
    '  "isNegative": true或false，是否为负面情绪,',
    '  "riskLevel": "low、medium、high三选一，用户心理风险等级",',
    '  "summary": "一句话概括用户当前的情绪状态",',
    '  "suggestion": "一句温和、可操作的情绪调节建议",',
    '  "actionItems": ["三条可以立刻执行的缓解行动，每条不超过15字"]',
    "}",
])


def _parse_json_loose(raw: str) -> dict | None:
    """模型偶尔裹```json代码块或前后加说明文字：取第一个{到最后一个}之间兜底解析"""
    text = raw.replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


@app.post("/analyze")
async def analyze(request: Request):
    """情绪分析是辅助信息，任何内部异常都返回 result=null，不抛5xx"""
    try:
        body = await request.json()
        messages = body.get("messages") or []
        # 没有用户发言无从分析（只有AI欢迎语的空会话等场景）
        if not any(
            m.get("role") == "user" and str(m.get("content") or "").strip()
            for m in messages if isinstance(m, dict)
        ):
            return {"result": None}
        # 每条截断到500字：分析看的是情绪倾向，不需要全文，控制token与耗时
        transcript = "\n".join(
            f"{'用户' if m.get('role') == 'user' else 'AI'}：{str(m.get('content') or '')[:500]}"
            for m in messages if isinstance(m, dict)
        )
        raw = await analyze_llm.ainvoke([
            SystemMessage(content=ANALYZE_SYSTEM_PROMPT),
            HumanMessage(content=f"对话记录：\n{transcript}"),
        ])
        return {"result": _parse_json_loose(_content_text(raw.content))}
    except Exception as e:  # noqa: BLE001 —— 情绪面板缺一轮数据无伤大雅
        print(f"[analyze] 情绪分析失败：{e}")
        return {"result": None}


# ---------------- 知识库管理 ----------------

@app.post("/kb/rebuild")
async def kb_rebuild(request: Request):
    """强制重建知识库（后台执行）。管理令牌未配置或校验不过一律403。"""
    if not config.ADMIN_TOKEN:
        return JSONResponse({"error": "ADMIN_TOKEN 未配置，端点禁用"}, status_code=403)
    token = request.headers.get("x-admin-token") or ""
    if not secrets.compare_digest(token, config.ADMIN_TOKEN):
        return JSONResponse({"error": "管理令牌错误"}, status_code=403)

    async def _bg():
        try:
            await knowledge_base.rebuild()
        except Exception as e:  # noqa: BLE001 —— 后台任务没人接异常，必须自己吞
            print(f"[kb/rebuild] 重建失败：{e}")

    asyncio.create_task(_bg())
    return {"started": True}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "kb": {
            "chunks": knowledge_base.chunk_count(),
            "building": knowledge_base.is_building(),
            "backend": get_vector_store().backend_name,
        },
    }
