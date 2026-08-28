"""
RAG 核心：文本向量化（embedding）+ 检索 + 咨询页 prompt 组装。
对应架构图里的 rag.py。

措辞纪律：RAG_CHAT_SYSTEM_PROMPT 与 build_rag_context 是从
src/views/frontend/Consultation.vue 逐字迁移的（迁移前后的模型输入保持一致，
这是浏览器端→服务端迁移的行为基准，改动会让线上回答风格漂移）。
"""
import httpx

import bm25
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


# 精排专用长连接客户端：每次请求现开 AsyncClient 要付冷启 TLS 握手，
# Render（美国）打国内 API 一个来回就是几百毫秒——模块级复用连接，
# 第一条消息之后精排延迟稳定在网络往返+推理本身。惰性创建，进程退出自动回收。
_rerank_client: httpx.AsyncClient | None = None


def _get_rerank_client() -> httpx.AsyncClient:
    global _rerank_client
    if _rerank_client is None or _rerank_client.is_closed:
        _rerank_client = httpx.AsyncClient(timeout=config.RERANK_TIMEOUT)
    return _rerank_client


async def _rerank(query: str, candidates: list[dict]) -> list[tuple[dict, float]] | None:
    """cross-encoder 精排：query 与每段块文本拼对打分，按相关度重排候选。
    返回 [(候选, rerank分)] 按分数降序；None = 精排不可用（未配置/超时/接口异常），
    调用方回退向量原序——精排是增强项，任何失败都绝不拖垮或延迟主链路。

    分数语义：rerank 分数（0~1 relevance）与余弦分数不是一个尺度、分布也不同
    （实测 rerank 区分度高两个数量级），所以阈值两把尺子分开配、不混用；
    引用卡片对外仍统一展示余弦分。"""
    if not config.RERANK_API_KEY or len(candidates) < 2:
        return None
    # 送精排的文本带"文章标题 - 小节"语境（cross-encoder 比向量检索更吃上下文），单段截500字控延迟
    documents = [
        f"{c['articleTitle']} - {c['heading']}\n{c['text'][:500]}"
        for c in candidates
    ]
    try:
        r = await _get_rerank_client().post(
            config.RERANK_URL,
            headers={"Authorization": f"Bearer {config.RERANK_API_KEY}"},
            json={
                "model": config.RERANK_MODEL,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            },
        )
        r.raise_for_status()
        # 兼容 Jina/Cohere 风格响应：{results: [{index, relevance_score}, ...]}，按分数降序
        results = r.json().get("results") or []
        if not results:
            return None
        return [
            (candidates[item["index"]], float(item.get("relevance_score") or 0.0))
            for item in results
            if isinstance(item.get("index"), int) and 0 <= item["index"] < len(candidates)
        ]
    except Exception as e:  # noqa: BLE001 —— 精排失败≠检索失败
        print(f"[RAG] rerank 不可用，回退向量原序：{e}")
        return None


async def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """问题向量化 → 向量粗排 top-10 ∪ BM25 词法 top-N 并集 → （可选）cross-encoder 精排
    → 余弦序+rerank序 两路 RRF 融合 → 取 top_k → 阈值过滤。
    任何失败都返回 []（调用方降级为无引用对话），检索绝不能拖垮聊天主链路。

    混合检索（BM25 只扩池、不投票）：稠密语义捞不准的精确词面（术语/专有名词）由稀疏
    词法补——精排只能重排已召回的候选，两路各捞、去重并集送精排。100 题同池对照
    （eval_report.md Part A-3）：并集池让 R@10 0.915→0.940、两路融合 NDCG 0.857→0.863；
    但给 BM25 第三票等权 RRF 会把摆位投乱（NDCG →0.820）、教科书"rerank 独裁定序"
    更差（→0.777）——所以词法路的贡献被限制在候选池扩展，排序权仍归余弦+精排。
    BM25 失败/关闭时并集退化为纯余弦 top-10，行为与历史完全一致（降级链第六层）。

    融合：余弦序与 rerank 序两路排名等权 RRF（1/(RRF_K+rank)）。纯 rerank 序在本语料上
    有净损伤，rerank 只当一票不当独裁者；BM25 独有候选凭精排的高排名单独过闸上位。

    阈值过滤：弱相关的候选不进 prompt、不展示卡片（宁可无引用，不拿噪声污染回答）。
    精排在场用 rerank 尺（RERANK_MIN_SCORE），关闭时用余弦尺（RAG_MIN_SCORE）——
    两把尺子分布不同，分开校准，谁在场用谁。未配 RERANK_API_KEY 时 _rerank 返回 None，
    退化为纯余弦 top_k + 余弦闸（与历史行为一致，配置即开关）。
    返回项：{index(1起), id, articleId, articleTitle, heading, text, score}（score 恒为余弦分；
    BM25 独有候选的余弦分取自加宽的余弦窗口，窗口外按 0=弱命中处理）"""
    query = (query or "").strip()
    if not query:
        return []
    final_k = top_k or config.RAG_TOP_K
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            qv = (await embed_texts([query], client))[0]
        if not qv:
            return []
        # 余弦窗口比粗排宽一个 BM25_TOP_N：并集里 BM25 独有的候选也能拿到真实余弦分，
        # 引用卡片"分数恒为余弦"的语义不破（余弦排名 >20 的才按 0 处理）
        window = get_vector_store().query(
            qv, max(final_k, config.RERANK_CANDIDATES) + config.BM25_TOP_N)
        candidates = window[: max(final_k, config.RERANK_CANDIDATES)]
        cos_score = {c["id"]: c["score"] for c in window}
        bm25_hits = bm25.search(query, config.BM25_TOP_N)
        pool = [dict(c) for c in candidates]
        pool_ids = {c["id"] for c in pool}
        for c, _ in bm25_hits:
            if c["id"] not in pool_ids:
                pool.append({**c, "score": cos_score.get(c["id"], 0.0)})
        reranked = await _rerank(query, pool)
        if reranked is not None:
            # 两路 RRF：各路记完整排名（不在融合前过滤），缺席不贡献、不补零排名。
            # rank_cos 只认余弦 top-10（加宽窗口里 11-20 名是取分数用的，不算检索命中）；
            # BM25 不投票——它捞回的候选要上位，得靠精排给它在 rank_rr 里排到前面
            rank_cos = {c["id"]: i + 1 for i, c in enumerate(candidates)}
            rank_rr = {c["id"]: i + 1 for i, (c, _) in enumerate(reranked)}
            rr_score = {c["id"]: s for c, s in reranked}

            def fused_score(c: dict) -> float:
                s = 0.0
                for rank in (rank_cos, rank_rr):
                    r = rank.get(c["id"])
                    if r is not None:
                        s += 1.0 / (config.RRF_K + r)
                return s

            fused = sorted(pool, key=lambda c: -fused_score(c))
            top = fused[:final_k]
            # 闸门仍用 rerank 绝对分（融合分只有序意义，无语义尺度；
            # BM25 绝对分对无关题也有 6~13 分，完全没有闸门区分度）
            results = [c for c in top if rr_score.get(c["id"], 0.0) >= config.RERANK_MIN_SCORE]
            gate = f"{'混合并集池' if len(pool) > len(candidates) else '余弦池'}两路RRF序 + rerank分≥{config.RERANK_MIN_SCORE}"
            dropped = [round(rr_score.get(c["id"], 0.0), 3) for c in top
                       if rr_score.get(c["id"], 0.0) < config.RERANK_MIN_SCORE]
        else:
            top = [(c, c["score"]) for c in candidates[:final_k]]
            results = [c for c, s in top if s >= config.RAG_MIN_SCORE]
            gate = f"余弦≥{config.RAG_MIN_SCORE}"
            dropped = [round(s, 3) for _, s in top if s < config.RAG_MIN_SCORE]
        if len(results) < len(top):
            print(f"[RAG] 阈值过滤：{len(top)} 个候选保留 {len(results)}（{gate}），被滤分数：{dropped}")
    except Exception as e:  # noqa: BLE001 —— 检索失败≠对话失败
        print(f"[RAG] 检索失败，本条消息降级为无引用：{e}")
        return []
    for i, item in enumerate(results):
        item["index"] = i + 1
    return results
