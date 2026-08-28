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
    """问题向量化 → 混合召回（余弦 top-N ∪ BM25 top-N）→ RRF(cos序,BM25序) 合并取前
    RERANK_CANDIDATES → （可选）cross-encoder 精排 → RRF(池内余弦序,rerank序) 融合定序
    → 取 top_k → 阈值过滤。任何失败都返回 []（调用方降级为无引用对话），
    检索绝不能拖垮聊天主链路。

    两段式 RRF（100 题标注集三轮对照定案，eval_weighted_report.md / eval_width_report.md）：
      合并处：两路召回排名等权 1/(RRF_K+rank)——纯排名融合，不配权重不归一化
        （加权扫描 w_bm∈{0,0.25,0.5,1,2,∞}：曲面台阶状，≥2 退化纯词法 NDCG 0.714、
        ≤0.5 退化纯余弦 0.812，1:1 是唯一吃到两路互补的点）；
      召回宽、精排池小：15+15 召回 R@0.976，合并只留 10 送精排（比并集池 10~16 个省），
        keep15 对 top-3 无增益反而 top1 0.894→0.882；
      定序处：rerank 不当独裁者（独裁 NDCG 0.791/0.807，任何宽度都是最差行），
        与池内余弦序再做一次等权 RRF——两个强但不完美的排序器互相兜底。

    降级链：BM25 关闭/失败 → 合并退化为余弦序；rerank 不可用 → 直接用合并 RRF 序
    + 余弦闸（"rerank 不可靠时用 RRF 结果"）；未配 RERANK_API_KEY 时全程无精排。
    阈值过滤：精排在场用 rerank 尺（RERANK_MIN_SCORE），否则余弦尺（RAG_MIN_SCORE），
    两把尺子分开校准，谁在场用谁。
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
        # 两路召回各取 top-召回宽度；余弦窗口再加宽一个 BM25 深度，
        # 让 BM25 独有的候选也拿到真实余弦分（引用卡片"分数恒为余弦"的语义不破）
        bm_n = config.BM25_TOP_N
        window = get_vector_store().query(qv, config.RAG_RECALL_N + bm_n)
        candidates = window[: config.RAG_RECALL_N]
        cos_score = {c["id"]: c["score"] for c in window}
        bm25_hits = bm25.search(query, bm_n) if bm_n > 0 else []
        pool = [dict(c) for c in candidates]
        pool_ids = {c["id"] for c in pool}
        for c, _ in bm25_hits:
            if c["id"] not in pool_ids:
                pool.append({**c, "score": cos_score.get(c["id"], 0.0)})

        # 合并处 RRF：两路召回排名等权融合，取前 RERANK_CANDIDATES 送精排
        # （缺席的路不贡献、不补零排名；BM25 关闭时即余弦原序）
        rank_cos0 = {c["id"]: i + 1 for i, c in enumerate(candidates)}
        rank_bm = {c["id"]: i + 1 for i, (c, _) in enumerate(bm25_hits)}

        def merge_score(c: dict) -> float:
            s = 0.0
            r = rank_cos0.get(c["id"])
            if r is not None:
                s += 1.0 / (config.RRF_K + r)
            r = rank_bm.get(c["id"])
            if r is not None:
                s += 1.0 / (config.RRF_K + r)
            return s

        pool = sorted(pool, key=lambda c: -merge_score(c))[: config.RERANK_CANDIDATES]

        reranked = await _rerank(query, pool)
        if reranked is not None:
            # 定序处 RRF：池内余弦序 + rerank 序等权融合（缺席不贡献、不补零排名）
            rank_cos = {c["id"]: i + 1 for i, c in enumerate(sorted(pool, key=lambda c: -c["score"]))}
            rank_rr = {c["id"]: i + 1 for i, (c, _) in enumerate(reranked)}
            rr_score = {c["id"]: s for c, s in reranked}

            def fused_score(c: dict) -> float:
                s = 1.0 / (config.RRF_K + rank_cos[c["id"]])
                r = rank_rr.get(c["id"])
                if r is not None:
                    s += 1.0 / (config.RRF_K + r)
                return s

            fused = sorted(pool, key=lambda c: -fused_score(c))
            top = fused[:final_k]
            # 闸门仍用 rerank 绝对分（融合分只有序意义，无语义尺度；
            # BM25 绝对分对无关题也有 6~13 分，完全没有闸门区分度）
            results = [c for c in top if rr_score.get(c["id"], 0.0) >= config.RERANK_MIN_SCORE]
            gate = f"两段RRF(合并+定序) + rerank分≥{config.RERANK_MIN_SCORE}"
            dropped = [round(rr_score.get(c["id"], 0.0), 3) for c in top
                       if rr_score.get(c["id"], 0.0) < config.RERANK_MIN_SCORE]
        else:
            # 精排不可用：直接用合并 RRF 序 + 余弦闸（rerank 不可靠时用 RRF 结果）
            top = pool[:final_k]
            results = [c for c in top if c["score"] >= config.RAG_MIN_SCORE]
            gate = f"合并RRF序 + 余弦≥{config.RAG_MIN_SCORE}"
            dropped = [round(c["score"], 3) for c in top if c["score"] < config.RAG_MIN_SCORE]
        if len(results) < len(top):
            print(f"[RAG] 阈值过滤：{len(top)} 个候选保留 {len(results)}（{gate}），被滤分数：{dropped}")
    except Exception as e:  # noqa: BLE001 —— 检索失败≠对话失败
        print(f"[RAG] 检索失败，本条消息降级为无引用：{e}")
        return []
    for i, item in enumerate(results):
        item["index"] = i + 1
    return results
