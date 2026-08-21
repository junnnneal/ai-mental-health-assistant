"""
Agent工具层：把知识库RAG检索 + 后端心理数据接口包装成LLM可调用的工具。

后端接口需要用户token：前端请求头携带 → FastAPI层写入ContextVar → 这里读取透传，
每个请求的Agent工具都以此用户身份调用后端，天然隔离多用户。

RAG部分已拆到独立模块（对应架构图）：
  config.py（配置）/ knowledge_base.py（入库）/ vector_store.py（Chroma向量库）/
  rag.py（向量化+检索）——本文件只保留工具封装。
"""
import json
from contextvars import ContextVar
from datetime import date

import httpx
from langchain_core.tools import tool

import knowledge_base
import rag
from config import BACKEND_BASE

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

@tool
async def search_knowledge(query: str, top_k: int = 3) -> str:
    """在心理健康知识库中检索与问题最相关的文章小节。适用于需要专业知识支撑的场景：情绪困扰、睡眠问题、压力应对、人际沟通、心理科普等。返回文章标题、小节标题、内容摘要和相似度得分。"""
    # 知识库未就绪先补建（通常启动时后台已灌完，这里兜底）
    try:
        await knowledge_base.ensure_built()
    except Exception as e:  # noqa: BLE001 —— 知识库挂了不该拖垮Agent，让LLM凭常识答
        return _reply({"error": f"知识库暂不可用：{e}，请直接凭常识回答"})
    results = await rag.retrieve(query, top_k)
    if not results:
        return _reply({"info": "知识库中没有检索到相关内容，请直接凭常识回答"})
    # 返回结构与拆分前完全一致，Agent的解析行为零变化
    return _reply(
        [
            {
                "title": c["articleTitle"],
                "heading": c["heading"],
                "summary": c["text"][:200],
                "score": c["score"],
            }
            for c in results
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
