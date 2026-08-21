"""
RAG 核心：文本向量化（embedding）+ 检索 + 咨询页 prompt 组装。
对应架构图里的 rag.py。

措辞纪律：RAG_CHAT_SYSTEM_PROMPT 与 build_rag_context 是从
src/views/frontend/Consultation.vue 逐字迁移的（迁移前后的模型输入保持一致，
这是浏览器端→服务端迁移的行为基准，改动会让线上回答风格漂移）。
"""
import httpx

import config
from vector_store import get_vector_store

# 咨询页人设（原 Consultation.vue 的 GLM_SYSTEM_PROMPT，逐字迁移）
RAG_CHAT_SYSTEM_PROMPT = "\n".join([
    "你是Junnnneal AI助手，一位温暖、专业的心理健康陪伴助手。",
    "请先用温和共情的语气回应对方的情绪，再给出具体、可操作的建议；回复保持简洁，一般不超过300字。",
    "如果用户表现出明显的自伤或危机倾向，请优先建议拨打心理援助热线（如希望24热线400-161-9995）或联系信任的人。",
])


def build_rag_context(citations: list[dict]) -> str:
    """检索结果注入 system prompt（原 Consultation.vue 的 ragContext 组装，逐字复刻）。
    正文截300字；回答里不标序号，来源统一由前端引用卡片展示。"""
    if not citations:
        return ""
    return "\n\n".join(
        [
            "以下是知识库中与用户问题相关的资料，回答时自然地参考；与问题无关的请忽略，不要在回答里标注来源序号（如[1][2]）：",
            *[
                f"[{i + 1}] 《{c['articleTitle']}》—— {c['heading']}\n{c['text'][:300]}"
                for i, c in enumerate(citations)
            ],
        ]
    )


async def embed_texts(texts: list[str], client: httpx.AsyncClient) -> list[list[float]]:
    """批量向量化：直调智谱 embedding 接口（EMBED_BATCH_SIZE 条/批，按 index 还原顺序）。
    原 tools.py 的 _embed_texts 原样迁移，knowledge_base 入库与本文件检索共用。"""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), config.EMBED_BATCH_SIZE):
        batch = texts[i: i + config.EMBED_BATCH_SIZE]
        r = await client.post(
            config.EMBED_URL,
            headers={"Authorization": f"Bearer {config.GLM_API_KEY}"},
            json={"model": config.EMBED_MODEL, "input": batch},
        )
        try:
            data = r.json().get("data") or []
        except Exception:
            data = []
        ordered: list = [None] * len(batch)
        for item in data:
            ordered[item["index"]] = item["embedding"]
        vectors.extend(ordered)
    return vectors


async def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """问题向量化 → 向量库取 top_k。
    任何失败都返回 []（调用方降级为无引用对话），检索绝不能拖垮聊天主链路。
    返回项：{index(1起), id, articleId, articleTitle, heading, text, score}"""
    query = (query or "").strip()
    if not query:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            qv = (await embed_texts([query], client))[0]
        if not qv:
            return []
        results = get_vector_store().query(qv, top_k or config.RAG_TOP_K)
    except Exception as e:  # noqa: BLE001 —— 检索失败≠对话失败
        print(f"[RAG] 检索失败，本条消息降级为无引用：{e}")
        return []
    for i, item in enumerate(results):
        item["index"] = i + 1
    return results
