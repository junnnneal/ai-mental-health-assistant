"""
FastAPI 入口：POST /chat 把前端消息喂给 LangGraph Agent，
用 astream_events(v2) 把执行过程翻译成 SSE 事件流：
  token      —— LM 正在输出的字（打字机）
  tool_start —— Agent 决定调用某工具（前端渲染"思考步骤"卡片）
  tool_end   —— 工具返回结果
  done / error
前端拿到的不只是答案，还有 Agent 的完整决策过程，用于过程可视化。
"""
import json

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.errors import GraphRecursionError

from graph import agent
from tools import user_token

app = FastAPI(title="AI健康管家 Agent 服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


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

    msgs = []
    for h in history[-10:]:
        role, content = h.get("role"), str(h.get("content") or "")
        if not content:
            continue
        msgs.append(HumanMessage(content) if role == "user" else AIMessage(content))
    msgs.append(HumanMessage(message))

    async def event_stream():
        try:
            async for ev in agent.astream_events({"messages": msgs}, version="v2"):
                kind = ev["event"]

                if kind == "on_chat_model_stream":
                    delta = ev["data"]["chunk"].content
                    # 兼容 content 为分块列表的模型返回
                    if isinstance(delta, list):
                        delta = "".join(
                            p.get("text", "") for p in delta if isinstance(p, dict)
                        )
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


@app.get("/health")
async def health():
    return {"status": "ok"}
