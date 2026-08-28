"""
加权 RRF 对照实验 v1（回答两个追问，全部离线复算、零 API 调用）：

1. RRF 的位置：
   - 教科书式：RRF(cos, BM25) 在混合检索处合并两路召回 → 选 top-10 送精排 → rerank 序即最终序；
   - 生产式：  余弦10 ∪ BM2510 并集送精排 → RRF(cos序, rerank序) 在精排后融合定序；
   - 两段式：  合并处 RRF(cos,BM25) 选池 + 定序处 RRF(cos,rerank)——两个位置都保留。
2. 权重分配：w_bm（BM25 票权，cos 恒为 1）从 0 扫到 ∞——教科书族扫"合并处权重"，
   连续票权族扫"生产架构下给 BM25 的第三票权重 γ"。

数据源：eval_pipes_cache.json（eval_rerank.py 跑管线时缓存的每题余弦序/BM25序/rerank分）。
rerank 是逐对独立打分（批量只是传输形式），并集池上的缓存分 = 任意子池送精排会得到的分，
因此教科书族的"合并选池 → 精排定序"可以离线精确复算。

用法：cd agent-server && python -X utf8 eval_weighted.py
输出：控制台 + eval_weighted_report.md
"""
import asyncio
import hashlib
import json

import config
from eval_rerank import (  # 复用 v3 协议的指标与口径，保证两份报告可直接对照
    REL, TYPE_NAMES, fuse_top, grade_of, hit3, load_kb_chunks, mrr, ndcg3, p3,
)
from knowledge_base import ensure_built

K = config.RRF_K
CAND = config.RERANK_CANDIDATES
TOPK = config.RAG_TOP_K
GATE = config.RERANK_MIN_SCORE


def ranks_of(pipe: dict) -> dict[str, dict]:
    """三路的排名表：cos=余弦top10原序，rr=rerank序，bm=BM25序（1起）"""
    return {
        "cos": {c["id"]: i + 1 for i, c in enumerate(pipe["cands"])},
        "rr": {c["id"]: i + 1 for i, (c, _) in enumerate(pipe["reranked"])} if pipe["reranked"] else {},
        "bm": {c["id"]: i + 1 for i, (c, _) in enumerate(pipe["bm25"])} if pipe.get("bm25") else {},
    }


def wrrf_score(cid: str, rk: dict, weights: dict[str, float]) -> float:
    """加权 RRF：Σ w_leg/(k+rank_leg)，缺席的路不贡献、不补零排名"""
    s = 0.0
    for leg, w in weights.items():
        r = rk[leg].get(cid)
        if w and r is not None:
            s += w / (K + r)
    return s


def make_order(mode: str, weights: dict[str, float]):
    """返回 order_fn(pipe) → 完整最终序（list[chunk dict]）。

    mode:
      textbook  合并处加权 RRF(cos,bm) 选 top-CAND → rerank 分定序（教科书最终序）
      two_stage 合并处加权 RRF(cos,bm) 选 top-CAND → 池内 RRF(cos序,rerank序) 定序
      fused     全并集池上多路加权 RRF 定序（生产架构，weights 含 bm 即给 BM25 票权）
    rerank 失败一律回退合并序/余弦序（生产回退路径）。"""

    def merged_pool(pipe: dict) -> list[dict]:
        rk = ranks_of(pipe)
        ids = sorted((c["id"] for c in pipe["pool"]),
                     key=lambda c: -wrrf_score(c, rk, weights))
        keep = set(ids[:CAND])
        return [c for c in pipe["pool"] if c["id"] in keep]

    def order(pipe: dict) -> list[dict]:
        rk = ranks_of(pipe)
        if mode in ("textbook", "two_stage"):
            pool = merged_pool(pipe)
            if not pipe["reranked"]:
                return pool  # 精排不可用：回退合并序
            rs = rr_scores(pipe)
            if mode == "textbook":
                # rerank 序即最终序（教科书定序方式）；无分的候选垫底
                return sorted(pool, key=lambda c: -rs.get(c["id"], float("-inf")))
            # two_stage：池内余弦序（含 bm 独有候选的真实余弦分）+ rerank 序等权融合
            rank_cos = {c["id"]: i + 1 for i, c in enumerate(sorted(pool, key=lambda c: -c["score"]))}
            rank_rr = {c["id"]: i + 1 for i, c in enumerate(
                sorted(pool, key=lambda c: -rs.get(c["id"], float("-inf"))))}
            return sorted(pool, key=lambda c: -(
                1.0 / (K + rank_cos[c["id"]]) + (1.0 / (K + rank_rr[c["id"]])
                                                 if c["id"] in rank_rr else 0.0)))
        # fused：全并集池多路加权
        return sorted(pipe["pool"], key=lambda c: -wrrf_score(c["id"], rk, weights))

    return order


def rr_scores(pipe: dict) -> dict:
    return {c["id"]: s for c, s in (pipe["reranked"] or [])}


def sim_chat(q, pipes, order_fn):
    """离线复刻 main.py /rag/chat 检索段（与 eval_rerank.sim_chat 同口径，
    仅把融合序参数化为 order_fn）：闸恒为 rerank≥GATE，含指代重试。"""
    def g(pipe):
        if pipe["reranked"] is None:
            return [c for c in pipe["cands"][:TOPK] if c["score"] >= config.RAG_MIN_SCORE]
        rs = rr_scores(pipe)
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
    await ensure_built()
    with open("eval_dataset.json", encoding="utf-8") as f:
        dataset = {q["id"]: q for q in json.load(f)["queries"]}

    # 缓存指纹校验（与 eval_rerank.py 同款）：不匹配说明管线结构变了，先重建缓存
    fp = hashlib.sha1("v3-bm25|".encode() + json.dumps(
        {qid: {"query": q["query"], "context": q.get("context")} for qid, q in dataset.items()},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    cache = json.load(open("eval_pipes_cache.json", encoding="utf-8"))
    if cache.get("fingerprint") != fp:
        raise SystemExit("eval_pipes_cache.json 指纹不匹配：先跑 eval_rerank.py 重建缓存")
    pipes = {qid: {var: {"cands": pl["cands"], "pool": pl["pool"],
                          "bm25": [[dict(c), s] for c, s in pl["bm25"]],
                          "reranked": [tuple(x) for x in pl["reranked"]] if pl["reranked"] is not None else None}
                    for var, pl in p.items()}
             for qid, p in cache["pipes"].items()}

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
                     "answerable": any(g >= REL for g in ideal)}
    main_q = [(qid, i) for qid, i in info.items() if i["q"]["type"] not in ("anaphora", "oov")]
    answerable_main = [(qid, i) for qid, i in main_q if i["answerable"]]

    lines: list[str] = []
    def out(s=""):
        print(s)
        lines.append(s)

    # ---- 配置矩阵 ----
    # 教科书族：RRF(cos,bm) 合并选池 → rerank 定序，w_bm 从 ∞ 扫到 0
    # （w_bm=1 即 rag_interview.md 的 rrf_merge 原版；w_bm=0 退化为余弦池 rerank 独裁）
    CFGS = [
        ("教科书 合并RRF w_bm=∞(纯BM25选池)", make_order("textbook", {"cos": 0.0, "bm": 1.0})),
        ("教科书 合并RRF w_bm=2", make_order("textbook", {"cos": 1.0, "bm": 2.0})),
        ("教科书 合并RRF w_bm=1（文档原版）", make_order("textbook", {"cos": 1.0, "bm": 1.0})),
        ("教科书 合并RRF w_bm=0.5", make_order("textbook", {"cos": 1.0, "bm": 0.5})),
        ("教科书 合并RRF w_bm=0.25", make_order("textbook", {"cos": 1.0, "bm": 0.25})),
        ("教科书 合并RRF w_bm=0(余弦选池)", make_order("textbook", {"cos": 1.0, "bm": 0.0})),
        ("两段式 w_bm=1 + RRF(cos,rr)定序", make_order("two_stage", {"cos": 1.0, "bm": 1.0})),
        ("两段式 w_bm=0.5 + RRF(cos,rr)定序", make_order("two_stage", {"cos": 1.0, "bm": 0.5})),
        ("生产 并集池 RRF(cos,rr)【基线】", lambda p: fuse_top(p, ("cos", "rr"))),
        ("连续票权 γ=0.25 并集三路加权", make_order("fused", {"cos": 1.0, "rr": 1.0, "bm": 0.25})),
        ("连续票权 γ=0.5 并集三路加权", make_order("fused", {"cos": 1.0, "rr": 1.0, "bm": 0.5})),
        ("连续票权 γ=1 并集三路等权", make_order("fused", {"cos": 1.0, "rr": 1.0, "bm": 1.0})),
        ("连续票权 γ=2 并集三路加权", make_order("fused", {"cos": 1.0, "rr": 1.0, "bm": 2.0})),
    ]

    # ================= Part A：纯排序（不加阈值，answerable 主表题） =================
    out("# 加权 RRF 对照实验（离线复算自 eval_pipes_cache.json，零 API 调用）\n")
    out(f"问题 1 RRF 位置：教科书（合并处 RRF(cos,BM25) → rerank 定序） vs 生产（并集池 → RRF(cos,rerank) 定序）"
        f" vs 两段式（两处都保留）。问题 2 权重：w_bm 扫 {0, 0.25, 0.5, 1, 2, '∞'}；"
        f"γ = 生产架构下给 BM25 的第三票权。相关口径 grade≥{REL}，k={K}，{len(answerable_main)} 题有标准答案。\n")
    out("## Part A 纯排序四指标（不加阈值）\n")
    out("| 配置 | MRR | NDCG@3 | P@3 | Hit@3 |")
    out("|---|---|---|---|---|")
    part_a: dict[str, tuple[float, float, float, float]] = {}
    for name, order_fn in CFGS:
        Ms, Ns, Ps, Hs = [], [], [], []
        for qid, i in answerable_main:
            g = [grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"])
                 for c in order_fn(pipes[qid]["raw"])]
            Ms.append(mrr(g)); Ns.append(ndcg3(g, i["ideal"])); Ps.append(p3(g)); Hs.append(hit3(g))
        n = len(answerable_main)
        part_a[name] = (sum(Ms) / n, sum(Ns) / n, sum(Ps) / n, sum(Hs) / n)
        out(f"| {name} | {part_a[name][0]:.3f} | {part_a[name][1]:.3f} | {part_a[name][2]:.3f} | {part_a[name][3]:.3f} |")
    out()

    # ================= Part B：闸后全链路（@0.01，含指代重试，100 题） =================
    out(f"## Part B 闸后全链路（闸=rerank≥{GATE}，含指代重试；与 eval_report B-1 同口径）\n")
    out("| 配置 | 平均引用数 | 引用覆盖率 | 无引用比例 | Precision | Recall | 无关引用率 | top1正确率 | OOV误引用 |")
    out("|---|---|---|---|---|---|---|---|---|")
    answerable_all = {qid for qid, i in info.items() if i["answerable"]}
    part_b: dict[str, dict] = {}
    for name, order_fn in CFGS:
        shown = clean = noise = pre_rel = covered = top1ok = nocite = oov_fp = 0
        for qid, i in info.items():
            cites, used = sim_chat(i["q"], pipes[qid], order_fn)
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
            pre = (order_fn(used)[:TOPK] if used["reranked"] is not None
                   else used["cands"][:TOPK])
            pre_rel += sum(1 for c in pre
                           if grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]) >= REL)
        na = len(answerable_all)
        part_b[name] = {"cov": covered / na, "nocite": nocite / len(info), "prec": clean / max(shown, 1),
                        "rec": clean / max(pre_rel, 1), "noise": noise / max(shown, 1),
                        "top1": top1ok / na, "oov_fp": oov_fp, "avg": shown / len(info)}
        r = part_b[name]
        out(f"| {name} | {r['avg']:.2f} | {r['cov']:.3f} | {r['nocite']:.1%} | {r['prec']:.3f} | "
            f"{r['rec']:.3f} | {r['noise']:.3f} | {r['top1']:.3f} | {r['oov_fp']}/14 |")
    out()

    # ================= 分题型：三强对照 =================
    out("## 分题型对照（Part A 口径，三强配置）\n")
    heads = [name for name, _ in CFGS if "生产" in name or "文档原版" in name]
    best_tb = max((n for n, _ in CFGS if n.startswith("教科书")),
                  key=lambda n: part_a[n][1])
    heads.append(best_tb)
    out("| 题型 | " + " | ".join(h.split("【")[0] for h in heads) + " (NDCG@3) |")
    out("|---|" + "---|" * len(heads))
    for t, tname in TYPE_NAMES.items():
        row = []
        for h in heads:
            order_fn = dict(CFGS)[h]
            Ns = [ndcg3([grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"])
                         for c in order_fn(pipes[qid]["raw"])], i["ideal"])
                  for qid, i in answerable_main if i["q"]["type"] == t]
            row.append(f"{sum(Ns)/max(len(Ns),1):.3f}" if Ns else "-")
        out(f"| {tname} | " + " | ".join(row) + " |")
    out()

    # ================= 结论 =================
    out("## 结论\n")
    prod = "生产 并集池 RRF(cos,rr)【基线】"
    best_all = max(part_a, key=lambda n: part_a[n][1])
    tb = [n for n in part_a if n.startswith("教科书") or n.startswith("两段式")]
    best_hybrid_shape = max(tb, key=lambda n: part_a[n][1])
    out(f"1. 全表 NDCG@3 最优：**{best_all}**（{part_a[best_all][1]:.3f}）；生产基线 {part_a[prod][1]:.3f}。")
    out(f"2. 教科书族/两段式族 最优：**{best_hybrid_shape}**（{part_a[best_hybrid_shape][1]:.3f}），"
        f"相对生产基线 {part_a[best_hybrid_shape][1]-part_a[prod][1]:+.3f}。")
    best_w = max((n for n in part_a if n.startswith("教科书") and "w_bm=" in n and "∞" not in n),
                 key=lambda n: part_a[n][1])
    out(f"3. 合并处权重扫描（教科书族）：最优 {best_w}（NDCG {part_a[best_w][1]:.3f}）；"
        f"w_bm=1 文档原版 {part_a['教科书 合并RRF w_bm=1（文档原版）'][1]:.3f}；"
        f"w_bm=0 余弦选池 {part_a['教科书 合并RRF w_bm=0(余弦选池)'][1]:.3f}。")
    g_best = max((n for n in part_a if n.startswith("连续票权")), key=lambda n: part_a[n][1])
    out(f"4. 生产架构下给 BM25 第三票（γ 扫描）：最优 {g_best}（NDCG {part_a[g_best][1]:.3f}）vs "
        f"γ=0 即生产基线 {part_a[prod][1]:.3f}——{'票权有净收益' if part_a[g_best][1] > part_a[prod][1] + 0.002 else '任何票权都不如不给'}。")
    out(f"5. 闸后（Part B）：top1 正确率 生产 {part_b[prod]['top1']:.3f} vs 教科书族最优 "
        f"{part_b[best_w]['top1']:.3f}；无关引用率 {part_b[prod]['noise']:.3f} vs {part_b[best_w]['noise']:.3f}。\n")

    with open("eval_weighted_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("报告已写入 eval_weighted_report.md")


if __name__ == "__main__":
    asyncio.run(main())
