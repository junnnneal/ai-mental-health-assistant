"""
Agent工具层：把知识库RAG检索 + 后端心理数据接口包装成LLM可调用的工具。

后端接口需要用户token：前端请求头携带 → FastAPI层写入ContextVar → 这里读取透传，
每个请求的Agent工具都以此用户身份调用后端，天然隔离多用户。
"""
import os
import re
import json
import math
from contextvars import ContextVar
from datetime import date

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://159.75.169.224:1235/api")
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
EMBED_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
EMBED_MODEL = "embedding-2"

# 当前请求的用户token（FastAPI请求处理器写入）
user_token: ContextVar[str] = ContextVar("user_token", default="")


def _headers() -> dict:
    return {"token": user_token.get(), "Content-Type": "application/json"}


def _json(r: httpx.Response) -> dict:
    """安全解析后端响应：token过期/网关错误时可能返回空体或非JSON，别让整个Agent流崩掉"""
    try:
        return r.json()
    except Exception:
        return {}


def _reply(payload: dict) -> str:
    """工具返回值统一走JSON字符串，LLM好解析，前端好展示"""
    return json.dumps(payload, ensure_ascii=False)


# ---------------- 工具一：知识库RAG检索 ----------------

# 进程内向量缓存：[{title, heading, text, embed_text, embedding}]，首次调用时构建
_knowledge_base: list[dict] = []


async def _embed_texts(texts: list[str], client: httpx.AsyncClient) -> list[list[float]]:
    """调用智谱embedding接口批量向量化（10条/批，按index还原顺序）"""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), 10):
        batch = texts[i : i + 10]
        r = await client.post(
            EMBED_URL,
            headers={"Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": EMBED_MODEL, "input": batch},
        )
        data = _json(r).get("data") or []
        ordered = [None] * len(batch)
        for item in data:
            ordered[item["index"]] = item["embedding"]
        vectors.extend(ordered)
    return vectors


async def _build_knowledge_base() -> int:
    """拉全量知识文章 → 按<h3>小节分块 → 批量向量化，进程内缓存"""
    global _knowledge_base
    async with httpx.AsyncClient(timeout=30) as client:
        articles = []
        page = 1
        while True:
            r = await client.get(
                f"{BACKEND_BASE}/knowledge/article/page",
                params={
                    "currentPage": page,
                    "size": 50,
                    "sortField": "readCount",
                    "sortDirection": "desc",
                },
                headers=_headers(),
            )
            data = _json(r).get("data") or {}
            records = data.get("records") or []
            articles.extend(records)
            if not records or page * 50 >= (data.get("total") or 0):
                break
            page += 1

        chunks = []
        for a in articles:
            detail = _json(
                await client.get(
                    f"{BACKEND_BASE}/knowledge/article/{a['id']}",
                    headers=_headers(),
                )
            ).get("data") or {}
            html = str(detail.get("content") or "")
            category = a.get("categoryName") or ""
            title = a.get("title") or ""
            # 与前端chunker同款逻辑：<h3>是天然的语义分块边界
            for sec in filter(None, (s.strip() for s in re.split(r"(?=<h3>)", html))):
                m = re.search(r"<h3>(.*?)</h3>", sec)
                heading = m.group(1) if m else title
                text = re.sub(r"<[^>]+>", "", sec).strip()
                if len(text) < 20:
                    continue
                chunks.append(
                    {
                        "title": title,
                        "heading": heading,
                        "text": text,
                        # 向量化文本带"分类+标题+小节"上下文前缀，提升检索命中率
                        "embed_text": f"【{category}】{title} - {heading}\n{text}",
                    }
                )

        vectors = await _embed_texts([c["embed_text"] for c in chunks], client)
        for chunk, vec in zip(chunks, vectors):
            if vec:
                chunk["embedding"] = vec
        _knowledge_base = [c for c in chunks if "embedding" in c]
        print(f"[RAG] 知识库构建完成：{len(articles)}篇文章 → {len(_knowledge_base)}个知识块")
        return len(_knowledge_base)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb or 1)


@tool
async def search_knowledge(query: str, top_k: int = 3) -> str:
    """在心理健康知识库中检索与问题最相关的文章小节。适用于需要专业知识支撑的场景：情绪困扰、睡眠问题、压力应对、人际沟通、心理科普等。返回文章标题、小节标题、内容摘要和相似度得分。"""
    if not _knowledge_base:
        if await _build_knowledge_base() == 0:
            return _reply({"error": "知识库构建失败或为空，请直接凭常识回答"})
    async with httpx.AsyncClient(timeout=30) as client:
        qv = (await _embed_texts([query], client))[0]
    ranked = sorted(
        ((_cosine(qv, c["embedding"]), c) for c in _knowledge_base),
        key=lambda x: x[0],
        reverse=True,
    )[:top_k]
    return _reply(
        [
            {
                "title": c["title"],
                "heading": c["heading"],
                "summary": c["text"][:200],
                "score": round(s, 4),
            }
            for s, c in ranked
        ]
    )


# ---------------- 工具二：最近会话情绪分析 ----------------


@tool
async def get_emotion_analysis() -> str:
    """获取当前用户最近一次AI咨询会话的情绪分析结果（主要情绪、强度、风险等级、总结与建议）。当用户想了解自己最近的情绪状态、情绪变化时调用。"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BACKEND_BASE}/psychological-chat/sessions",
            params={"pageNum": 1, "pageSize": 1},
            headers=_headers(),
        )
        data = _json(r).get("data") or {}
        records = data.get("records") or (data if isinstance(data, list) else [])
        if not records:
            return _reply({"info": "用户暂无咨询会话记录，可以建议用户先去AI咨询聊聊"})
        sid = records[0].get("id")
        r2 = await client.get(
            f"{BACKEND_BASE}/psychological-chat/session/session_{sid}/emotion",
            headers=_headers(),
        )
        return _reply(_json(r2).get("data") or {"info": "该会话暂无情绪分析结果"})


# ---------------- 工具三：最近会话列表 ----------------


@tool
async def get_recent_sessions(limit: int = 5) -> str:
    """获取当前用户最近的AI咨询会话列表（标题、时间、消息数、时长）。用于快速了解用户最近的咨询历史概况。"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BACKEND_BASE}/psychological-chat/sessions",
            params={"pageNum": 1, "pageSize": limit},
            headers=_headers(),
        )
        data = _json(r).get("data") or {}
        records = data.get("records") or (data if isinstance(data, list) else [])
        return _reply(
            [
                {
                    "title": s.get("sessionTitle"),
                    "startedAt": s.get("startedAt"),
                    "messageCount": s.get("messageCount"),
                    "durationMinutes": s.get("durationMinutes"),
                }
                for s in records
            ]
        )


# ---------------- 工具四：写情绪日记 ----------------


@tool
async def save_emotion_diary(
    dominant_emotion: str,
    mood_score: int,
    diary_content: str,
    emotion_triggers: str = "",
    sleep_quality: int = 3,
    stress_level: int = 3,
) -> str:
    """为当前用户写一条今天的情绪日记（同一天会覆盖更新）。参数：dominant_emotion主要情绪词（如焦虑/平静/低落/开心）；mood_score情绪评分0-100；diary_content日记正文；emotion_triggers触发事件；sleep_quality睡眠质量1-5（5最好）；stress_level压力水平1-5（5最大）。当用户表达"帮我记一下今天的心情"之类诉求时调用。"""
    payload = {
        "diaryDate": str(date.today()),
        "moodScore": mood_score,
        "dominantEmotion": dominant_emotion,
        "emotionTriggers": emotion_triggers,
        "diaryContent": diary_content,
        "sleepQuality": sleep_quality,
        "stressLevel": stress_level,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{BACKEND_BASE}/emotion-diary",
            headers=_headers(),
            json=payload,
        )
        ok = str(_json(r).get("code")) == "200"
        return _reply(
            {
                "success": ok,
                "diaryDate": payload["diaryDate"],
                "saved": payload if ok else None,
            }
        )
