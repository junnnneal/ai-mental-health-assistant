"""
候选宽度对照实验 v1：检验「召回宽一些提高召回率、最终上下文小一些减噪」在本语料的得失。

架构固定为已定案的两段式（RRF(cos,bm)=1:1 合并选池 → rerank → RRF(cos,rr) 定序），
扫宽度：召回 10+10 vs 15+15，合并保留 keep 10 vs 15；另带两个对照：
  教科书（15+15→15，rerank 序即最终序，即参考流程原样）
  生产（union 池 + RRF(cos,rr)，10 宽度 = 现网行为锚点）

管线上限抓宽（余弦窗 30 / BM25 15 / 精排 union15），所有配置的池都是它的子集——
rerank 逐对独立打分，子池分数 = 全池分数，因此一轮 API 跑完全部离线复算。

用法：cd agent-server && python -X utf8 eval_width.py
输出：控制台 + eval_width_report.md
"""
import asyncio
import hashlib
import json
import os
import time

import httpx

import bm25
import config
import rag
from eval_rerank import (REL, TYPE_NAMES, grade_of, hit3, load_kb_chunks, mrr,
                         ndcg3, p3)
from knowledge_base import ensure_built
from vector_store import get_vector_store

K = config.RRF_K
TOPK = config.RAG_TOP_K
GATE = config.RERANK_MIN_SCORE
W = 15  # 宽路召回深度（cos 与 bm 同宽；窄路 10 从宽路前缀截取）


async def run_wide(query: str, store, client) -> dict:
    """宽抓管线：余弦窗 30（cands15 + bm 独有候选的余弦分）、BM25 top-15、
    union15 整体送精排。窄路全部量都是它的前缀/子集。"""
    qv = (await rag.embed_texts([query], client))[0]
    window = store.query(qv, 30)
    cands = window[:W]
    cos_score = {c["id"]: c["score"] for c in window}
    bm_hits = bm25.search(query, W)
    pool = [dict(c) for c in cands]
    ids = {c["id"] for c in pool}
    for c, _ in bm_hits:
        if c["id"] not in ids:
            pool.append({**c, "score": cos_score.get(c["id"], 0.0)})
    t0 = time.perf_counter()
    reranked = await rag._rerank(query, pool)
    return {"cands": cands, "bm": [[c, s] for c, s in bm_hits], "pool": pool,
            "cos": cos_score,
            "reranked": reranked, "rerank_ok": reranked is not None,
            "rerank_latency": time.perf_counter() - t0}


def build_pipe(wide: dict, width: int) -> dict:
    """从宽缓存裁出指定宽度的 pipe（与 eval_rerank 缓存同 shape）：
    cands=余弦前 width、bm25=BM25 前 width、pool=两者并集（bm 独有带真实余弦分）、
    reranked=全量精分按池过滤（逐对独立，过滤后 = 只送该池会得到的分与序）。"""
    cands = wide["cands"][:width]
    bm = wide["bm"][:width]
    cos_score = wide["cos"]
    pool = [dict(c) for c in cands]
    ids = {c["id"] for c in pool}
    for c, _ in bm:
        if c["id"] not in ids:
            pool.append({**c, "score": cos_score.get(c["id"], 0.0)})
    pool_ids = {c["id"] for c in pool}
    reranked = ([(c, s) for c, s in wide["reranked"] if c["id"] in pool_ids]
                if wide["reranked"] is not None else None)
    return {"cands": cands, "bm25": bm, "pool": pool, "reranked": reranked}


def merged_order(pipe: dict, keep: int, w_bm: float = 1.0) -> list[dict]:
    """合并处加权 RRF(cos,bm)：对并集池按 Σ w/(k+rank) 排序取前 keep（精排不可用时的回退序）"""
    rank_cos = {c["id"]: i + 1 for i, c in enumerate(pipe["cands"])}
    rank_bm = {c["id"]: i + 1 for i, (c, _) in enumerate(pipe["bm25"])}

    def sc(c: dict) -> float:
        s = 0.0
        if c["id"] in rank_cos:
            s += 1.0 / (K + rank_cos[c["id"]])
        if c["id"] in rank_bm:
            s += w_bm / (K + rank_bm[c["id"]])
        return s

    return sorted(pipe["pool"], key=lambda c: -sc(c))[:keep]


def make_two_stage(width: int, keep: int, w_bm: float = 1.0):
    """两段式定案架构：RRF(cos,bm) 合并选 keep → 池内 RRF(cos序,rerank序) 定序"""
    def order(pipe: dict) -> list[dict]:
        merged = merged_order(pipe, keep, w_bm)
        if pipe["reranked"] is None:
            return merged  # 精排不可用：回退合并序（参考原则"rerank 不可靠时直接用 RRF 结果"）
        rs = {c["id"]: s for c, s in pipe["reranked"]}
        rank_cos = {c["id"]: i + 1 for i, c in enumerate(sorted(merged, key=lambda c: -c["score"]))}
        rank_rr = {c["id"]: i + 1 for i, c in enumerate(sorted(merged, key=lambda c: -rs.get(c["id"], float("-inf"))))}
        return sorted(merged, key=lambda c: -(
            1.0 / (K + rank_cos[c["id"]]) + (1.0 / (K + rank_rr[c["id"]]) if c["id"] in rank_rr else 0.0)))
    return order


def make_textbook(width: int, keep: int):
    """参考流程原样：RRF(cos,bm)=1:1 合并选 keep → rerank 序即最终序"""
    def order(pipe: dict) -> list[dict]:
        merged = merged_order(pipe, keep)
        if pipe["reranked"] is None:
            return merged
        rs = {c["id"]: s for c, s in pipe["reranked"]}
        return sorted(merged, key=lambda c: -rs.get(c["id"], float("-inf")))
    return order


def make_prod():
    """生产语义：union 池 → RRF(余弦原序, rerank序) 定序（BM25 不投票）"""
    def order(pipe: dict) -> list[dict]:
        if pipe["reranked"] is None:
            return pipe["cands"]
        rank_cos = {c["id"]: i + 1 for i, c in enumerate(pipe["cands"])}
        rank_rr = {c["id"]: i + 1 for i, (c, _) in enumerate(pipe["reranked"])}
        return sorted(pipe["pool"], key=lambda c: -(
            (1.0 / (K + rank_cos[c["id"]]) if c["id"] in rank_cos else 0.0)
            + (1.0 / (K + rank_rr[c["id"]]) if c["id"] in rank_rr else 0.0)))
    return order


def sim_chat(q, pipes, order_fn):
    """离线复刻 main.py /rag/chat 检索段（闸恒 rerank≥GATE，含指代重试）"""
    def g(pipe):
        if pipe["reranked"] is None:
            return [c for c in pipe["cands"][:TOPK] if c["score"] >= config.RAG_MIN_SCORE]
        rs = {c["id"]: s for c, s in pipe["reranked"]}
        return [c for c in order_fn(pipe)[:TOPK] if rs.get(c["id"], 0.0) >= GATE]

    used = pipes["raw"]
    cites = g(used)
    if q["context"]:
        top_score = max((c["score"] for c in cites), default=0.0)
        if top_score < config.RAG_RETRY_BELOW:
            retry = g(pipes["concat"])
            if retry and max(c["score"] for c in retry) > top_score:
                cites, used = retry, pipes["concat"]
    return cites, used


async def main():
    config.RERANK_TIMEOUT = 10.0  # 评测放宽：测真实质量，生产 2s 打掉率另看
    await ensure_built()
    store = get_vector_store()
    with open("eval_dataset.json", encoding="utf-8") as f:
        dataset = {q["id"]: q for q in json.load(f)["queries"]}

    CACHE = "eval_width_cache.json"
    fp = hashlib.sha1(f"v1-width{W}|".encode() + json.dumps(
        {qid: {"query": q["query"], "context": q.get("context")} for qid, q in dataset.items()},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    wide: dict[str, dict] = {}
    lat = []
    if os.path.exists(CACHE) and json.load(open(CACHE, encoding="utf-8")).get("fingerprint") == fp:
        cached = json.load(open(CACHE, encoding="utf-8"))["wide"]
        for qid, p in cached.items():
            wide[qid] = {var: {"cands": pl["cands"], "pool": pl["pool"], "cos": pl["cos"],
                                "bm": [[dict(c), s] for c, s in pl["bm"]],
                                "reranked": [tuple(x) for x in pl["reranked"]] if pl["reranked"] is not None else None,
                                "rerank_ok": pl["rerank_ok"], "rerank_latency": pl["rerank_latency"]}
                          for var, pl in p.items()}
        lat = [pl["rerank_latency"] for p in wide.values() for pl in p.values() if pl["rerank_ok"]]
        print(f"使用宽缓存 {CACHE}（{len(wide)} 题指纹匹配）")
    else:
        async with httpx.AsyncClient(timeout=30) as client:
            for qid, q in dataset.items():
                p = {"raw": await run_wide(q["query"], store, client)}
                if q["context"]:
                    p["concat"] = await run_wide(f"{q['context'][:80]}\n{q['query']}", store, client)
                wide[qid] = p
                for pl in p.values():
                    if pl["rerank_ok"]:
                        lat.append(pl["rerank_latency"])
                print(f"wide ok: {qid}")
        ser = {qid: {var: {"cands": pl["cands"], "pool": pl["pool"], "bm": pl["bm"],
                            "cos": pl["cos"],
                            "reranked": [[c, s] for c, s in pl["reranked"]] if pl["reranked"] is not None else None,
                            "rerank_ok": pl["rerank_ok"], "rerank_latency": pl["rerank_latency"]}
                     for var, pl in p.items()} for qid, p in wide.items()}
        json.dump({"fingerprint": fp, "wide": ser}, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"宽管线已缓存 → {CACHE}")

    # 每题两个宽度的 pipe
    pipes = {qid: {var: {10: build_pipe(pl, 10), 15: build_pipe(pl, 15)}
                   for var, pl in p.items()} for qid, p in wide.items()}

    all_chunks = load_kb_chunks()
    ids_by_article: dict[str, list[str]] = {}
    for cid, m in all_chunks.items():
        ids_by_article.setdefault(m["articleId"], []).append(cid)
    info = {}
    for qid, q in dataset.items():
        labels, chunk_labels = q["labels"], q.get("chunk_labels", {})
        ideal = [grade_of(cid, all_chunks[cid], labels, chunk_labels)
                 for aid in labels for cid in ids_by_article.get(aid, [])]
        info[qid] = {"q": q, "labels": labels, "chunk_labels": chunk_labels, "ideal": ideal,
                     "answerable": any(g >= REL for g in ideal),
                     "rel_articles_set": {a for a, g in labels.items() if g >= REL}}
    main_q = [(qid, i) for qid, i in info.items() if i["q"]["type"] not in ("anaphora", "oov")]
    answerable_main = [(qid, i) for qid, i in main_q if i["answerable"]]

    lines: list[str] = []
    def out(s=""):
        print(s)
        lines.append(s)

    CFGS = [
        ("两段式 10+10 keep10（=v3 定案）", 10, make_two_stage(10, 10)),
        ("两段式 15+15 keep10", 15, make_two_stage(15, 10)),
        ("两段式 15+15 keep15", 15, make_two_stage(15, 15)),
        ("教科书 15+15 keep15（参考流程原样）", 15, make_textbook(15, 15)),
        ("生产 union15 RRF(cos,rr)", 15, make_prod()),
        ("生产 union10 RRF(cos,rr)（现网锚点）", 10, make_prod()),
    ]

    # ---- 召回宽度收益 ----
    out("# 候选宽度对照实验（两段式定案架构上扫宽度；rerank 逐对独立，一轮宽抓全量复算）\n")
    out(f"## 召回随宽度的变化（{len(answerable_main)} 题，文章级 R@N）\n")
    out("| 宽度 | R@cos10 | R@cos15 | R@union10 | R@union15 |")
    out("|---|---|---|---|---|")
    rec = {k: [] for k in ("r10", "r15", "u10", "u15")}
    for qid, i in answerable_main:
        def R(pipe):
            return (len({all_chunks[c["id"]]["articleId"] for c in pipe["pool"]} & i["rel_articles_set"])
                    / len(i["rel_articles_set"]))
        p10, p15 = pipes[qid]["raw"][10], pipes[qid]["raw"][15]
        rec["r10"].append(R({"pool": p10["cands"]}))
        rec["r15"].append(R({"pool": p15["cands"]}))
        rec["u10"].append(R(p10))
        rec["u15"].append(R(p15))
    m = lambda k: sum(rec[k]) / max(len(rec[k]), 1)  # noqa: E731
    out(f"| 平均 | {m('r10'):.3f} | {m('r15'):.3f} | {m('u10'):.3f} | {m('u15'):.3f} |\n")

    # ---- Part A 排序 ----
    out("## Part A 纯排序四指标（不加阈值）\n")
    out("| 配置 | MRR | NDCG@3 | P@3 | Hit@3 |")
    out("|---|---|---|---|---|")
    part_a: dict[str, tuple[float, float, float, float]] = {}
    for name, width, order_fn in CFGS:
        Ms, Ns, Ps, Hs = [], [], [], []
        for qid, i in answerable_main:
            g = [grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"])
                 for c in order_fn(pipes[qid]["raw"][width])]
            Ms.append(mrr(g)); Ns.append(ndcg3(g, i["ideal"])); Ps.append(p3(g)); Hs.append(hit3(g))
        n = len(answerable_main)
        part_a[name] = (sum(Ms) / n, sum(Ns) / n, sum(Ps) / n, sum(Hs) / n)
        out(f"| {name} | {part_a[name][0]:.3f} | {part_a[name][1]:.3f} | {part_a[name][2]:.3f} | {part_a[name][3]:.3f} |")
    out()

    # ---- Part B 闸后 ----
    out(f"## Part B 闸后全链路（闸=rerank≥{GATE}，含指代重试，100 题）\n")
    out("| 配置 | 平均引用数 | 覆盖率 | 无引用比例 | Precision | Recall | 无关引用率 | top1正确率 | OOV误引用 |")
    out("|---|---|---|---|---|---|---|---|---|")
    answerable_all = {qid for qid, i in info.items() if i["answerable"]}
    for name, width, order_fn in CFGS:
        shown = clean = noise = pre_rel = covered = top1ok = nocite = oov_fp = 0
        for qid, i in info.items():
            cites, used = sim_chat(i["q"], {v: pipes[qid][v][width] for v in pipes[qid]}, order_fn)
            g = [grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]) for c in cites]
            shown += len(g)
            clean += sum(1 for x in g if x >= REL)
            noise += sum(1 for x in g if x == 0)
            nocite += int(not g)
            if qid in answerable_all:
                covered += int(any(x >= REL for x in g))
                top1ok += int(bool(g) and g[0] >= REL)
            if i["q"]["type"] == "oov" and g:
                oov_fp += 1
            pre = (order_fn(used)[:TOPK] if used["reranked"] is not None else used["cands"][:TOPK])
            pre_rel += sum(1 for c in pre
                           if grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]) >= REL)
        na = len(answerable_all)
        out(f"| {name} | {shown/len(info):.2f} | {covered/na:.3f} | {nocite/len(info):.1%} | "
            f"{clean/max(shown,1):.3f} | {clean/max(pre_rel,1):.3f} | {noise/max(shown,1):.3f} | "
            f"{top1ok/na:.3f} | {oov_fp}/14 |")
    out()

    # ---- 分题型（两段式 10 vs 15） ----
    out("## 分题型 NDCG@3（两段式窄/宽 + 教科书宽）\n")
    heads = [(n, w, f) for n, w, f in CFGS if "两段式" in n or "教科书" in n]
    out("| 题型 | " + " | ".join(n.split("（")[0] for n, _, _ in heads) + " |")
    out("|---|" + "---|" * len(heads))
    for t, tname in TYPE_NAMES.items():
        row = []
        for _, width, order_fn in heads:
            Ns = [ndcg3([grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"])
                         for c in order_fn(pipes[qid]["raw"][width])], i["ideal"])
                  for qid, i in answerable_main if i["q"]["type"] == t]
            row.append(f"{sum(Ns)/max(len(Ns),1):.3f}" if Ns else "-")
        out(f"| {tname} | " + " | ".join(row) + " |")
    out()

    lat.sort()
    out("## 附：本轮宽抓管线可用性")
    out(f"- rerank(union15≈15~25候选) 延迟 avg {sum(lat)/len(lat):.2f}s / p95 {lat[max(0,int(len(lat)*0.95)-1)]:.2f}s / max {lat[-1]:.2f}s\n")

    with open("eval_width_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("报告已写入 eval_width_report.md")


if __name__ == "__main__":
    asyncio.run(main())
