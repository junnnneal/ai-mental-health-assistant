"""
重排效果判定 v3：两段式协议（基于人工标注分级测试集 eval_dataset.json，100 题）。

用法：cd agent-server && python -X utf8 eval_rerank.py
输出：控制台报告 + eval_report.md

Part A 纯排序能力（不加阈值）：直接取 rerank 排序后的 Top 3，评 MRR / NDCG@3 / P@3 / Hit@3，
        与余弦原序 Top 3 对照。阈值无关，回答"reranker 排序本身行不行"。
        Part A-3 同池六配置对照：余弦 / 纯BM25 / 纯rerank（教科书最终序）/ 两路RRF(cos+rr) /
        两路RRF(cos+bm) / 三路RRF(cos+rr+bm)——回答"BM25 第三路值不值得进融合、
        rerank 该独裁还是当一票"（并集池 = 余弦10 ∪ BM25 10，去重后送精排）。
Part B 阈值扫描：闸门 0 / 0.01 / 0.03 / 0.05 / 0.08 / 0.1（rerank 在场，逐档离线复算），
        另加基线行 rerank-OFF（余弦 top3 + 0.40 闸，生产回退路径）。观测：
        引用覆盖率 / 无引用问题比例 / Precision / Recall / 无关引用率 / top1正确率(答案质量代理) / 平均引用数。
        附 @0.01 同闸对比：方案A(rerank独裁) / 两路RRF / 三路RRF。

标注口径：0 不相关 / 1 部分相关 / 2 相关 / 3 高度相关；块继承文章级，可按小节覆盖；池外未标注=0。
"""
import asyncio
import hashlib
import json
import math
import os
import time

import httpx

import bm25
import config
import rag
from knowledge_base import _chunk_article, _load_seed_articles, ensure_built
from vector_store import get_vector_store

REL = 2          # grade≥2 记为相关
GATES = [0, 0.01, 0.03, 0.05, 0.08, 0.1]
TYPE_NAMES = {"easy": "直答基线", "synonym": "同义表达", "keyword": "精确关键词",
              "confusable": "易混淆", "crisis": "心理危机"}


# ---------------- 数据准备 ----------------

def load_kb_chunks() -> dict[str, dict]:
    chunks = {}
    for art in _load_seed_articles():
        for c in _chunk_article(art):
            chunks[c["id"]] = {"articleId": c["articleId"], "heading": c["heading"]}
    return chunks


def grade_of(chunk_id: str, chunk_meta: dict, labels: dict, chunk_labels: dict) -> int:
    ov = chunk_labels.get(f"{chunk_meta['articleId']}|{chunk_meta['heading']}")
    return ov if ov is not None else labels.get(chunk_meta["articleId"], 0)


# ---------------- 指标 ----------------

def p3(grades: list[int]) -> float:
    return sum(1 for g in grades[:3] if g >= REL) / 3


def hit3(grades: list[int]) -> int:
    return int(any(g >= REL for g in grades[:3]))


def mrr(grades: list[int]) -> float:
    """MRR@3：只在前 3 个里找第一个相关块——产品只展示 top3 引用，rank4+ 用户看不到，
    与 Hit@3/P@3/NDCG@3 统一在同一个窗口（传入完整排序时自动截前 3）"""
    return next((1 / (i + 1) for i, g in enumerate(grades[:3]) if g >= REL), 0.0)


def ndcg3(grades: list[int], ideal: list[int]) -> float:
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:3]))
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(ideal, reverse=True)[:3]))
    return dcg / idcg if idcg else 0.0


# ---------------- 检索（每题只跑一次，闸门全部离线复算） ----------------

async def run_pipeline(query: str, store, client) -> dict:
    """与 rag.retrieve 生产逻辑逐行一致：余弦窗口(10+BM25_N) → 余弦top10 ∪ BM25top10 并集 →
    并集整体送精排（闸门要 rerank 分）。BM25 是本地计算，缓存里只存结果不存索引。"""
    qv = (await rag.embed_texts([query], client))[0]
    window = store.query(qv, config.RERANK_CANDIDATES + config.BM25_TOP_N)
    cands = window[: config.RERANK_CANDIDATES]
    cos_score = {c["id"]: c["score"] for c in window}
    bm25_hits = bm25.search(query, config.BM25_TOP_N)
    pool = [dict(c) for c in cands]
    ids = {c["id"] for c in pool}
    for c, _ in bm25_hits:
        if c["id"] not in ids:
            pool.append({**c, "score": cos_score.get(c["id"], 0.0)})
    t0 = time.perf_counter()
    reranked = await rag._rerank(query, pool)
    dt = time.perf_counter() - t0
    return {"cands": cands, "pool": pool, "bm25": [[c, s] for c, s in bm25_hits],
            "reranked": reranked, "rerank_ok": reranked is not None, "rerank_latency": dt}


# 生产融合路（两路等权：余弦序+rerank序；BM25 只扩并集池不投票——Part A-3 结论）
LEGS_PROD = ("cos", "rr")


def fuse_top(pipe: dict, legs: tuple[str, ...] = LEGS_PROD) -> list[dict]:
    """与 rag.py 生产逻辑一致的 RRF 融合：legs 指定参与投票的排名路（等权 1/(RRF_K+rank)，
    缺席的路不贡献、不补零排名）。单腿 legs 即该路原序（("rr",) = rerank 独裁 = 教科书最终序）。
    rerank 失败时退回余弦原序（生产回退路径）。"""
    if pipe["reranked"] is None:
        return pipe["cands"]
    ranks = {
        "cos": {c["id"]: i + 1 for i, c in enumerate(pipe["cands"])},
        "rr": {c["id"]: i + 1 for i, (c, _) in enumerate(pipe["reranked"])},
        "bm": {c["id"]: i + 1 for i, (c, _) in enumerate(pipe["bm25"])} if pipe.get("bm25") else {},
    }

    def score(c):
        s = 0.0
        for leg in legs:
            r = ranks[leg].get(c["id"])
            if r is not None:
                s += 1.0 / (config.RRF_K + r)
        return s

    return sorted(pipe["pool"], key=lambda c: -score(c))


def gate_top3(pipe: dict, t: float, legs: tuple[str, ...] = LEGS_PROD) -> list[dict]:
    """离线复刻 rag.retrieve：融合序 top3 按 rerank 分数 ≥t 过闸；rerank 失败回退余弦 + RAG_MIN_SCORE"""
    if pipe["reranked"] is not None:
        rs = {c["id"]: s for c, s in pipe["reranked"]}
        top = fuse_top(pipe, legs)[: config.RAG_TOP_K]
        return [c for c in top if rs.get(c["id"], 0.0) >= t]
    top = pipe["cands"][: config.RAG_TOP_K]
    return [c for c in top if c["score"] >= config.RAG_MIN_SCORE]


def gate_top3_cos(pipe: dict, t: float) -> list[dict]:
    """rerank-OFF 基线：余弦 top3 + 余弦闸"""
    return [c for c in pipe["cands"][: config.RAG_TOP_K] if c["score"] >= t]


def sim_chat(q, pipes, t, mode="rerank", legs: tuple[str, ...] = LEGS_PROD):
    """离线复刻 main.py /rag/chat 检索段：首轮(闸t) → 弱命中(<RAG_RETRY_BELOW)拼上轮重试(闸t) → 分高才换。
    返回 (放行引用, 实际采用的管线)——重试换池后 Recall 分母要跟实际池走。"""
    if mode == "rerank":
        g = lambda pipe: gate_top3(pipe, t, legs)  # noqa: E731
    else:
        g = lambda pipe: gate_top3_cos(pipe, t)  # noqa: E731
    used = pipes["raw"]
    cites = g(used)
    if q["context"]:
        top_score = max((c["score"] for c in cites), default=0.0)
        if top_score < config.RAG_RETRY_BELOW:
            retry = g(pipes["concat"])
            if retry and max(c["score"] for c in retry) > top_score:
                cites, used = retry, pipes["concat"]
    return cites, used


def ideal_grades(labels: dict, chunk_labels: dict, all_chunks: dict, ids_by_article: dict) -> list[int]:
    out = []
    for aid in labels:
        for cid in ids_by_article.get(aid, []):
            out.append(grade_of(cid, all_chunks[cid], labels, chunk_labels))
    return out


async def main():
    config.RERANK_TIMEOUT = 10.0  # 评测放宽：先测精排真实质量，生产 2s 打掉率单列
    await ensure_built()
    store = get_vector_store()
    with open("eval_dataset.json", encoding="utf-8") as f:
        dataset = {q["id"]: q for q in json.load(f)["queries"]}
    all_chunks = load_kb_chunks()
    ids_by_article: dict[str, list[str]] = {}
    for cid, m in all_chunks.items():
        ids_by_article.setdefault(m["articleId"], []).append(cid)

    lines: list[str] = []
    def out(s=""):
        print(s)
        lines.append(s)

    # ---- 跑管线：每题 raw + （指代题）concat；带指纹缓存，改离线逻辑不重打 API ----
    # 指纹带 schema 版本号：管线结构变了（v3 加 BM25/并集池）即使题目没变也强制重跑
    CACHE = "eval_pipes_cache.json"
    fp = hashlib.sha1("v3-bm25|".encode() + json.dumps(
        {qid: {"query": q["query"], "context": q.get("context")} for qid, q in dataset.items()},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    pipes: dict[str, dict] = {}
    latencies = []
    if os.path.exists(CACHE) and json.load(open(CACHE, encoding="utf-8")).get("fingerprint") == fp:
        cached = json.load(open(CACHE, encoding="utf-8"))["pipes"]
        for qid, p in cached.items():
            pipes[qid] = {var: {"cands": pl["cands"], "pool": pl["pool"],
                                "bm25": [[dict(c), s] for c, s in pl["bm25"]],
                                "reranked": [tuple(x) for x in pl["reranked"]] if pl["reranked"] is not None else None,
                                "rerank_ok": pl["rerank_ok"], "rerank_latency": pl["rerank_latency"]}
                          for var, pl in p.items()}
        latencies = [pl["rerank_latency"] for p in pipes.values() for pl in p.values() if pl["rerank_ok"]]
        print(f"使用管线缓存 {CACHE}（{len(pipes)} 题指纹匹配）")
    else:
        async with httpx.AsyncClient(timeout=30) as client:
            for qid, q in dataset.items():
                p = {"raw": await run_pipeline(q["query"], store, client)}
                if q["context"]:
                    p["concat"] = await run_pipeline(f"{q['context'][:80]}\n{q['query']}", store, client)
                pipes[qid] = p
                for pl in p.values():
                    if pl["rerank_ok"]:
                        latencies.append(pl["rerank_latency"])
                print(f"pipeline ok: {qid}")
        ser = {qid: {var: {"cands": pl["cands"], "pool": pl["pool"],
                           "bm25": [[c, s] for c, s in pl["bm25"]],
                           "reranked": [[c, s] for c, s in pl["reranked"]] if pl["reranked"] is not None else None,
                           "rerank_ok": pl["rerank_ok"], "rerank_latency": pl["rerank_latency"]}
                     for var, pl in p.items()} for qid, p in pipes.items()}
        json.dump({"fingerprint": fp, "pipes": ser}, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"管线已缓存 → {CACHE}")

    def grades_of(order, labels, chunk_labels):
        items = [c for c, _ in order] if (order and isinstance(order[0], tuple)) else order
        return [grade_of(c["id"], all_chunks[c["id"]], labels, chunk_labels) for c in items]

    # 预计算每题常用数据
    info = {}
    for qid, q in dataset.items():
        labels, chunk_labels = q["labels"], q.get("chunk_labels", {})
        ideal = ideal_grades(labels, chunk_labels, all_chunks, ids_by_article)
        cos_g = grades_of(pipes[qid]["raw"]["cands"], labels, chunk_labels)
        rr_g = grades_of(pipes[qid]["raw"]["reranked"] or pipes[qid]["raw"]["cands"], labels, chunk_labels)
        info[qid] = {
            "q": q, "labels": labels, "chunk_labels": chunk_labels, "ideal": ideal,
            "cos_g": cos_g, "rr_g": rr_g,
            "answerable": any(g >= REL for g in ideal),
            "rel_articles": {a for a, g in labels.items() if g >= REL},
        }

    # ================= Part A：纯排序（不加阈值） =================
    out("# 重排效果判定 v2：两段式协议（100 题人工标注分级测试集）\n")
    out(f"管线：余弦 top-{config.RERANK_CANDIDATES} ∪ BM25 top-{config.BM25_TOP_N} 去重并集 → "
        f"rerank（{config.RERANK_MODEL}）整体打分 → RRF 融合（k={config.RRF_K}）→ Top3。"
        f"相关口径 grade≥{REL}，NDCG 增益 2^grade-1。指代题/OOV 不进主表。\n")

    main_q = [(qid, i) for qid, i in info.items() if i["q"]["type"] not in ("anaphora", "oov")]
    answerable_main = [(qid, i) for qid, i in main_q if i["answerable"]]
    out(f"## Part A 纯排序能力（不加阈值，rerank Top3 直接评分；主表 {len(answerable_main)} 题有标准答案）\n")
    out("诊断意义：MRR/NDCG@3 与阈值无关——若 rerank 后不升反降，问题在排序不在阈值。\n")
    out("| 问题 | 类型 | R@10 | R并集 | MRR 粗→精 | NDCG@3 粗→精 | P@3 粗→精 | Hit@3 粗→精 |")
    out("|---|---|---|---|---|---|---|---|")
    agg = {k: [] for k in ("recall10", "recall_pool", "cos_mrr", "rr_mrr", "cos_n", "rr_n",
                           "cos_p3", "rr_p3", "cos_h3", "rr_h3")}
    by_type: dict[str, dict] = {}
    for qid, i in answerable_main:
        c_g, r_g, ideal = i["cos_g"], i["rr_g"], i["ideal"]
        recall10 = (len({all_chunks[c['id']]['articleId'] for c in pipes[qid]['raw']['cands']} & i["rel_articles"])
                    / len(i["rel_articles"]))
        recall_pool = (len({all_chunks[c['id']]['articleId'] for c in pipes[qid]['raw']['pool']} & i["rel_articles"])
                       / len(i["rel_articles"]))
        vals = {"recall10": recall10, "recall_pool": recall_pool,
                "cos_mrr": mrr(c_g), "rr_mrr": mrr(r_g),
                "cos_n": ndcg3(c_g, ideal), "rr_n": ndcg3(r_g, ideal),
                "cos_p3": p3(c_g), "rr_p3": p3(r_g),
                "cos_h3": hit3(c_g), "rr_h3": hit3(r_g)}
        for k, v in vals.items():
            agg[k].append(v)
            by_type.setdefault(i["q"]["type"], {}).setdefault(k, []).append(v)
        out(f"| {i['q']['query'][:22]} | {i['q']['type']} | {recall10:.2f} | {recall_pool:.2f} | "
            f"{vals['cos_mrr']:.2f}→{vals['rr_mrr']:.2f} | {vals['cos_n']:.3f}→{vals['rr_n']:.3f} | "
            f"{vals['cos_p3']:.2f}→{vals['rr_p3']:.2f} | {vals['cos_h3']}→{vals['rr_h3']} |")
    A = lambda k: sum(agg[k]) / max(len(agg[k]), 1)  # noqa: E731
    out(f"| **平均（{len(answerable_main)}题）** | | **{A('recall10'):.3f}** | **{A('recall_pool'):.3f}** | "
        f"**{A('cos_mrr'):.3f}→{A('rr_mrr'):.3f}** | **{A('cos_n'):.3f}→{A('rr_n'):.3f}** | "
        f"**{A('cos_p3'):.3f}→{A('rr_p3'):.3f}** | **{A('cos_h3'):.3f}→{A('rr_h3'):.3f}** |\n")

    out("### 按题型分桶（Part A）\n")
    out("| 题型 | 题数 | R@10 | R并集 | MRR 粗→精 | NDCG@3 粗→精 | P@3 粗→精 | Hit@3 粗→精 |")
    out("|---|---|---|---|---|---|---|---|")
    for t, name in TYPE_NAMES.items():
        if t not in by_type:
            continue
        b = by_type[t]
        m = lambda k: sum(b[k]) / max(len(b[k]), 1)  # noqa: E731
        out(f"| {name} | {len(b['cos_mrr'])} | {m('recall10'):.3f} | {m('recall_pool'):.3f} | "
            f"{m('cos_mrr'):.3f}→{m('rr_mrr'):.3f} | "
            f"{m('cos_n'):.3f}→{m('rr_n'):.3f} | {m('cos_p3'):.3f}→{m('rr_p3'):.3f} | {m('cos_h3'):.3f}→{m('rr_h3'):.3f} |")
    out()

    # ---- Part A-3：同池六配置四指标总表（BM25 第三路 + rerank 独裁问题的直接对比） ----
    out(f"### Part A-3 融合四指标总表（同池对比：并集池 = 余弦{config.RERANK_CANDIDATES} ∪ BM25{config.BM25_TOP_N} 去重，"
        f"RRF k={config.RRF_K} 等权；{len(answerable_main)} 题）\n")
    out("方案A=教科书混合检索（向量+BM25 召回，rerank 序即最终序）；两路/三路 RRF = rerank 降级为投票者。\n")
    orders = [
        ("余弦原序（粗排）", lambda p: p["cands"]),
        ("纯 BM25 序", lambda p: [c for c, _ in p["bm25"]]),
        ("纯 rerank 序 = 方案A最终序", lambda p: [c for c, _ in (p["reranked"] or p["cands"])]),
        ("两路RRF cos+rerank（生产：BM25只扩池不投票）", lambda p: fuse_top(p, ("cos", "rr"))),
        ("两路RRF cos+BM25", lambda p: fuse_top(p, ("cos", "bm"))),
        ("三路RRF cos+rerank+BM25（已否决）", lambda p: fuse_top(p, ("cos", "rr", "bm"))),
    ]
    out("| 排序 | MRR | NDCG@3 | P@3 | Hit@3 |")
    out("|---|---|---|---|---|")
    cfg_m: dict[str, tuple[float, float, float, float]] = {}
    for name, order_of in orders:
        Ms, Ns, Ps, Hs = [], [], [], []
        for qid, i in answerable_main:
            g = grades_of(order_of(pipes[qid]["raw"]), i["labels"], i["chunk_labels"])
            Ms.append(mrr(g)); Ns.append(ndcg3(g, i["ideal"])); Ps.append(p3(g)); Hs.append(hit3(g))
        n = len(answerable_main)
        cfg_m[name] = (sum(Ms) / n, sum(Ns) / n, sum(Ps) / n, sum(Hs) / n)
        out(f"| {name} | {sum(Ms)/n:.3f} | {sum(Ns)/n:.3f} | {sum(Ps)/n:.3f} | {sum(Hs)/n:.3f} |")
    out()

    # 分桶：两路 vs 三路（BM25 第三路在各题型上的增量）
    out("| 题型 | MRR 两路/三路 | NDCG@3 两路/三路 | P@3 两路/三路 | Hit@3 两路/三路 |")
    out("|---|---|---|---|---|")
    for t, name in TYPE_NAMES.items():
        if t not in by_type:
            continue
        rows = {"2": {"m": [], "n": [], "p": [], "h": []}, "3": {"m": [], "n": [], "p": [], "h": []}}
        for qid, i in answerable_main:
            if i["q"]["type"] != t:
                continue
            for tag, legs in (("2", ("cos", "rr")), ("3", LEGS_PROD)):
                g = grades_of(fuse_top(pipes[qid]["raw"], legs), i["labels"], i["chunk_labels"])
                d = rows[tag]
                d["m"].append(mrr(g)); d["n"].append(ndcg3(g, i["ideal"])); d["p"].append(p3(g)); d["h"].append(hit3(g))
        a = lambda d, k: sum(d[k]) / max(len(d[k]), 1)  # noqa: E731
        out(f"| {name} | {a(rows['2'],'m'):.3f}/**{a(rows['3'],'m'):.3f}** | "
            f"{a(rows['2'],'n'):.3f}/**{a(rows['3'],'n'):.3f}** | "
            f"{a(rows['2'],'p'):.3f}/**{a(rows['3'],'p'):.3f}** | "
            f"{a(rows['2'],'h'):.3f}/**{a(rows['3'],'h'):.3f}** |")
    out()
    # 主表无标准答案的题（Hit 恒 0，单列说明）
    noans = [(qid, i) for qid, i in main_q if not i["answerable"]]
    if noans:
        out(f"注：{len(noans)} 题标注最高仅 1 分（无 grade≥2 目标），不进 Part A 排序评测："
            + "、".join(qid for qid, _ in noans) + "\n")

    # ---- 指代题排序（raw / concat 两变体，仍不加阈值） ----
    out("## Part A-2 多轮指代题（12 题）：裸问 vs 拼上下文，融合序 Top3 不加阈值（生产顺序）\n")
    out("| 问题(上下文) | 变体 | MRR | NDCG@3 | P@3 | Hit@3 | top1等级 |")
    out("|---|---|---|---|---|---|---|")
    ana_stats = {"raw": [], "concat": []}
    for qid, i in [(k, v) for k, v in info.items() if v["q"]["type"] == "anaphora"]:
        for var in ("raw", "concat"):
            g = grades_of(fuse_top(pipes[qid][var]), i["labels"], i["chunk_labels"])
            ana_stats[var].append((mrr(g), ndcg3(g, i["ideal"]), p3(g), hit3(g)))
            out(f"| {i['q']['query'][:12]}（{i['q']['context'][:10]}…） | {var} | {mrr(g):.2f} | {ndcg3(g, i['ideal']):.3f} | {p3(g):.2f} | {hit3(g)} | {g[0] if g else '-'} |")
    for var, cn in (("raw", "裸问"), ("concat", "拼接")):
        s = ana_stats[var]
        out(f"| **平均({cn})** | | **{sum(x[0] for x in s)/len(s):.3f}** | **{sum(x[1] for x in s)/len(s):.3f}** | "
            f"**{sum(x[2] for x in s)/len(s):.3f}** | **{sum(x[3] for x in s)/len(s):.3f}** | |")
    out()

    # ================= Part B：阈值扫描 + 同闸方案对比 =================
    out(f"## Part B 阈值扫描（rerank 在场，排序=两路 RRF 融合序（生产，BM25 只扩池），闸门作用于 rerank 绝对分；"
        f"基线行=rerank OFF 余弦闸 0.40）\n")
    out("每题检索只跑一次，各档闸门/各融合方案离线复算（与生产 rag.retrieve/main.py 逻辑逐行一致，含指代重试）。\n")
    out("指标定义：")
    out("- 引用覆盖率 = 有标准答案的题中，至少 1 条 grade≥2 引用被放行的比例")
    out("- 无引用比例 = 全部 100 题中出 0 条引用的比例（OOV 零引用是正确行为，14 题全部拦下时下限 14%）")
    out("- Precision = 放行块中 grade≥2 的比例；无关引用率 = 放行块中 grade0 的比例")
    out("- Recall = 放行的 grade≥2 块 / 闸前（该方案融合序）Top3 中的 grade≥2 块（闸门对排序结果的破坏度）")
    out("- top1正确率 = 有答案题中 top1 引用 grade≥2 的比例（最终答案质量代理——真实答案质量需 LLM 评审，另计）\n")

    answerable_all = {qid: i for qid, i in info.items() if i["answerable"]}

    def measure(mode: str, t: float, legs: tuple[str, ...]) -> dict:
        """一档配置全量跑一遍（闸 t、融合路 legs），返回八个指标。"""
        shown_total = clean_total = noise_total = 0
        pool_rel_total = 0  # 闸前（该方案融合序）top3 中 grade≥2 块数
        covered = top1_ok = nocite = oov_fp = 0
        for qid, i in info.items():
            cites, used = sim_chat(i["q"], pipes[qid], t, mode, legs)
            g = [grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]) for c in cites]
            shown_total += len(g)
            clean_total += sum(1 for x in g if x >= REL)
            noise_total += sum(1 for x in g if x == 0)
            if not g:
                nocite += 1
            if qid in answerable_all:
                if any(x >= REL for x in g):
                    covered += 1
                if g and g[0] >= REL:
                    top1_ok += 1
            if i["q"]["type"] == "oov" and g:
                oov_fp += 1
            # 闸前 top3 跟实际采用的池与该方案融合序走（重试换池后分母同步换）
            pre = (fuse_top(used, legs)[: config.RAG_TOP_K]
                   if (mode == "rerank" and used["reranked"] is not None)
                   else used["cands"][: config.RAG_TOP_K])
            pool_rel_total += sum(1 for c in pre
                                  if grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]) >= REL)
        na = len(answerable_all)
        return {"cov": covered / na, "nocite": nocite / len(info), "prec": clean_total / max(shown_total, 1),
                "rec": clean_total / max(pool_rel_total, 1), "noise": noise_total / max(shown_total, 1),
                "top1": top1_ok / na, "oov_fp": oov_fp, "avg": shown_total / len(info)}

    def row(name: str, r: dict):
        out(f"| {name} | {r['avg']:.2f} | {r['cov']:.3f} | {r['nocite']:.1%} | {r['prec']:.3f} | {r['rec']:.3f} | "
            f"{r['noise']:.3f} | {r['top1']:.3f} | {r['oov_fp']}/14 |")

    HEAD = "| 配置 | 平均引用数 | 引用覆盖率 | 无引用比例 | Precision | Recall | 无关引用率 | top1正确率 | OOV误引用 |"

    # ---- B-1 同闸对比：三种排序方案 @0.01（+OFF 基线）——rerank 独裁 vs 当一票 ----
    out(f"### B-1 同闸对比（闸=rerank≥{config.RERANK_MIN_SCORE}，含指代重试；排序方案唯一变量）\n")
    out(HEAD)
    out("|---|---|---|---|---|---|---|---|---|")
    cmp_rows = {
        "OFF(余弦0.40)": measure("cos", config.RAG_MIN_SCORE, LEGS_PROD),
        "方案A rerank独裁@0.01": measure("rerank", config.RERANK_MIN_SCORE, ("rr",)),
        "两路RRF cos+rr @0.01（生产）": measure("rerank", config.RERANK_MIN_SCORE, ("cos", "rr")),
        "三路RRF cos+rr+bm @0.01（对照）": measure("rerank", config.RERANK_MIN_SCORE, ("cos", "rr", "bm")),
    }
    for name, r in cmp_rows.items():
        row(name, r)
    out()

    # ---- B-2 阈值扫描：生产配置（三路）逐档 ----
    out("### B-2 阈值扫描（两路 RRF 序（生产），闸门作用于 rerank 绝对分）\n")
    out(HEAD)
    out("|---|---|---|---|---|---|---|---|---|")
    sweep = {f"ON@{t}": measure("rerank", t, LEGS_PROD) for t in GATES}
    for t in GATES:
        row(f"ON@{t}", sweep[f"ON@{t}"])
    out()

    # ---- 分数带佐证（排序问题 vs 阈值问题的直接证据） ----
    out("## 佐证：rerank 分数按标注等级的分布（是否可分 = 是否存在『完美阈值』）\n")
    main_samples = []
    for qid, i in info.items():
        if i["q"]["type"] in ("anaphora", "oov"):
            continue
        rs = {c["id"]: s for c, s in (pipes[qid]["raw"]["reranked"] or [])}
        for c in pipes[qid]["raw"]["pool"]:
            main_samples.append((grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]), rs.get(c["id"])))
    r2 = sorted(r for g, r in main_samples if g >= REL and r is not None)
    r0 = sorted(r for g, r in main_samples if g == 0 and r is not None)
    out(f"- grade≥2 共 {len(r2)} 块：min {r2[0]:.4f} / 中位 {r2[len(r2)//2]:.4f} / max {r2[-1]:.4f}")
    out(f"- grade0 共 {len(r0)} 块：min {r0[0]:.4f} / 中位 {r0[len(r0)//2]:.4f} / max {r0[-1]:.4f}")
    overlap = sum(1 for x in r2 if x < r0[-1])
    out(f"- 重叠度：{overlap}/{len(r2)} 的相关块分数低于噪声最高分 {r0[-1]:.4f} → "
        f"{'分数带重叠，不存在能同时保覆盖与纯净的绝对阈值' if overlap else '分数带可分，阈值有优化空间'}\n")

    # ---- OOV 细节 ----
    out("## 附：OOV 题细节（闸门无关的最高分对照）\n")
    out("| 问题 | 余弦最高分 | rerank最高分 | BM25最高分 |")
    out("|---|---|---|---|")
    for qid, i in [(k, v) for k, v in info.items() if v["q"]["type"] == "oov"]:
        max_cos = max((c["score"] for c in pipes[qid]["raw"]["cands"]), default=0)
        max_rr = max((s for _, s in (pipes[qid]["raw"]["reranked"] or [])), default=0)
        max_bm = max((s for _, s in (pipes[qid]["raw"]["bm25"] or [])), default=0)
        out(f"| {i['q']['query'][:24]} | {max_cos:.3f} | {max_rr:.4f} | {max_bm:.2f} |")
    out()

    # ---- 可用性 ----
    lat = sorted(latencies)
    out("## 附：rerank 可用性（并集池 10~20 候选整体送精排）\n")
    out(f"- 调用成功率 {len(lat)}/{sum(len(p) for p in pipes.values())}，延迟 avg {sum(lat)/len(lat):.2f}s / "
        f"p95 {lat[max(0, int(len(lat)*0.95)-1)]:.2f}s / max {lat[-1]:.2f}s")
    out(f"- 生产 2s 超时线：{sum(1 for x in lat if x > 2.0)}/{len(lat)} 次会被打掉\n")

    # ---- 自动诊断结论 ----
    out("## 诊断结论\n")
    d_mrr = A("rr_mrr") - A("cos_mrr")
    d_ndcg = A("rr_n") - A("cos_n")
    two = cfg_m["两路RRF cos+rerank（生产：BM25只扩池不投票）"]
    three = cfg_m["三路RRF cos+rerank+BM25（已否决）"]
    plan_a = cfg_m["纯 rerank 序 = 方案A最终序"]
    out(f"1. rerank 排序本身（阈值无关）：纯 rerank 序 MRR {A('cos_mrr'):.3f}→{A('rr_mrr'):.3f}（{d_mrr:+.3f}），"
        f"NDCG@3 {A('cos_n'):.3f}→{A('rr_n'):.3f}（{d_ndcg:+.3f}）——reranker 对本题库排序"
        f"{'提升' if d_ndcg > 0.005 else ('持平' if d_ndcg > -0.005 else '净损伤')}，"
        f"『精排当投票者而非独裁者』的前提{'继续成立' if d_ndcg <= 0.005 else '在本语料不再成立'}。")
    out(f"2. BM25 进融合投票（同池三路 vs 两路）：MRR {two[0]:.3f}→{three[0]:.3f}（{three[0]-two[0]:+.3f}），"
        f"NDCG@3 {two[1]:.3f}→{three[1]:.3f}（{three[1]-two[1]:+.3f}），"
        f"P@3 {two[2]:.3f}→{three[2]:.3f}（{three[2]-two[2]:+.3f}），"
        f"Hit@3 {two[3]:.3f}→{three[3]:.3f}（{three[3]-two[3]:+.3f}）——"
        f"第三票{'值得进融合' if three[1] > two[1] + 0.002 else ('收益不显著' if three[1] >= two[1] - 0.002 else '负收益，已否决')}；"
        f"BM25 的价值在扩池：R@10→R并集 {A('recall10'):.3f}→{A('recall_pool'):.3f}，"
        f"两路融合 NDCG 0.857（余弦10池时代）→{two[1]:.3f}（并集池）。")
    out(f"3. rerank 独裁 vs 两路投票（教科书方案A，同池）：NDCG@3 方案A {plan_a[1]:.3f} vs 两路 {two[1]:.3f}，"
        f"MRR {plan_a[0]:.3f} vs {two[0]:.3f}——"
        f"{'两路胜' if two[1] > plan_a[1] + 0.002 else ('基本持平' if two[1] >= plan_a[1] - 0.002 else '方案A胜，教科书做法在本语料更优')}；"
        f"闸后行为见 B-1。")
    r2c, r3c = cmp_rows["两路RRF cos+rr @0.01（生产）"], cmp_rows["三路RRF cos+rr+bm @0.01（对照）"]
    out(f"4. 闸后（B-1，@{config.RERANK_MIN_SCORE}）：两路 vs 三路——覆盖 {r2c['cov']:.3f}/{r3c['cov']:.3f}、"
        f"无关引用率 {r2c['noise']:.3f}/{r3c['noise']:.3f}、top1 {r2c['top1']:.3f}/{r3c['top1']:.3f}、"
        f"OOV 误引用 {r2c['oov_fp']}/14 与 {r3c['oov_fp']}/14——"
        f"{'两路生产配置在噪声上同样更干净' if r2c['noise'] <= r3c['noise'] else '注意：两路噪声反而更高'}。")
    best_on = max(GATES, key=lambda t: sweep[f"ON@{t}"]["cov"] - sweep[f"ON@{t}"]["noise"])
    out(f"5. 阈值：两路序下覆盖-噪声平衡最优档 ON@{best_on}（覆盖 {sweep[f'ON@{best_on}']['cov']:.3f} / "
        f"无关 {sweep[f'ON@{best_on}']['noise']:.3f}）；现行闸 {config.RERANK_MIN_SCORE} 是否移动按覆盖/噪声偏好定。\n")

    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("报告已写入 eval_report.md")


if __name__ == "__main__":
    asyncio.run(main())
