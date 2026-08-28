"""
RRF 融合离线实验：用 eval_pipes_cache.json（100 题管线缓存）扫 k 值与权重，
对照 纯余弦序 / 纯 rerank 序 的 Part A 排序指标 + Part B 闸门行为。

【归档说明】本脚本停留在两路 RRF 时代（候选池=余弦 top-10，只读缓存的 cands/reranked 键，
v3 缓存仍带这两个键所以还能跑）。BM25 第三路上线后的同池多配置对比见 eval_rerank.py
的 Part A-3（六配置）与 Part B-1（同闸对比）。

用法：cd agent-server && python -X utf8 rrf_experiment.py   （秒级，不打 API）
RRF(d) = w_cos/(k+rank_cos) + w_rr/(k+rank_rr)，候选池=粗排 top-10（两路都给满 10 个排名）
"""
import json

import config
from eval_rerank import REL, grade_of, hit3, load_kb_chunks, mrr, ndcg3, p3

TYPE_NAMES = {"easy": "直答", "synonym": "同义", "keyword": "关键词", "confusable": "易混淆", "crisis": "危机"}


def load_all():
    dataset = {q["id"]: q for q in json.load(open("eval_dataset.json", encoding="utf-8"))["queries"]}
    cache = json.load(open("eval_pipes_cache.json", encoding="utf-8"))["pipes"]
    pipes = {qid: {var: {"cands": pl["cands"],
                         "reranked": [tuple(x) for x in pl["reranked"]] if pl["reranked"] is not None else None}
                   for var, pl in p.items()}
             for qid, p in cache.items()}
    return dataset, pipes


def fuse_order(cands, reranked, k, w_cos=1.0, w_rr=1.0):
    """返回按融合分降序的 chunk 列表 + 每块的 rerank 分（闸门仍用 rerank 绝对分）"""
    rank_cos = {c["id"]: i + 1 for i, c in enumerate(cands)}
    rank_rr = {c["id"]: i + 1 for i, (c, _) in enumerate(reranked)}
    rr_score = {c["id"]: s for c, s in reranked}
    fused = sorted(cands, key=lambda c: -(w_cos / (k + rank_cos[c["id"]])
                                          + w_rr / (k + rank_rr.get(c["id"], 10 ** 6))))
    return fused, rr_score


def order_grades(items, labels, chunk_labels, all_chunks):
    return [grade_of(c["id"], all_chunks[c["id"]], labels, chunk_labels) for c in items]


def get_top3(pipe, mode, labels, chunk_labels, all_chunks, k, w_cos, w_rr):
    """按模式取 top3：cos=余弦原序 / rr=纯rerank序 / rrf=融合序。返回 (chunks, rerank分dict)"""
    cands, reranked = pipe["cands"], pipe["reranked"]
    if mode == "cos" or reranked is None:
        return cands[: config.RAG_TOP_K], ({c["id"]: s for c, s in reranked} if reranked else {})
    if mode == "rr":
        return [c for c, _ in reranked[: config.RAG_TOP_K]], {c["id"]: s for c, s in reranked}
    fused, rr_score = fuse_order(cands, reranked, k, w_cos, w_rr)
    return fused[: config.RAG_TOP_K], rr_score


def main():
    dataset, pipes = load_all()
    all_chunks = load_kb_chunks()
    ids_by_article: dict[str, list[str]] = {}
    for cid, m in all_chunks.items():
        ids_by_article.setdefault(m["articleId"], []).append(cid)

    def ideal_of(q):
        out = []
        for aid in q["labels"]:
            for cid in ids_by_article.get(aid, []):
                ov = q.get("chunk_labels", {}).get(f"{all_chunks[cid]['articleId']}|{all_chunks[cid]['heading']}")
                out.append(ov if ov is not None else q["labels"].get(aid, 0))
        return out

    def grade_of_(cid, labels, chunk_labels):
        return grade_of(cid, all_chunks[cid], labels, chunk_labels)

    main_q = [(qid, q) for qid, q in dataset.items() if q["type"] not in ("anaphora", "oov")]
    answerable = [(qid, q) for qid, q in main_q if any(g >= REL for g in ideal_of(q))]

    configs = [("cos", 0, 1, 1), ("rr", 0, 1, 1)] + \
              [(f"rrf k={k}", k, 1.0, 1.0) for k in (1, 3, 5, 10, 20, 60)] + \
              [("rrf k=10 cos×0.7", 10, 0.7, 1.0), ("rrf k=10 rr×0.7", 10, 1.0, 0.7),
               ("rrf k=5 cos×0.7", 5, 0.7, 1.0), ("rrf k=5 rr×0.7", 5, 1.0, 0.7)]

    print(f"===== Part A 排序指标（{len(answerable)} 题有标准答案，阈值无关）=====")
    print(f"{'配置':<18} MRR    NDCG@3 P@3    Hit@3")
    results = {}
    for name, k, wc, wr in configs:
        mode = name.split()[0]
        Ms, Ns, Ps, Hs = [], [], [], []
        for qid, q in answerable:
            top3, _ = get_top3(pipes[qid]["raw"], mode, q["labels"], q.get("chunk_labels", {}),
                               all_chunks, k, wc, wr)
            g = order_grades(top3, q["labels"], q.get("chunk_labels", {}), all_chunks)
            ideal = ideal_of(q)
            Ms.append(mrr(g)); Ns.append(ndcg3(g, ideal)); Ps.append(p3(g)); Hs.append(hit3(g))
        n = len(answerable)
        results[name] = (sum(Ms)/n, sum(Ns)/n, sum(Ps)/n, sum(Hs)/n)
        print(f"{name:<18} {sum(Ms)/n:.3f}  {sum(Ns)/n:.3f}  {sum(Ps)/n:.3f}  {sum(Hs)/n:.3f}")

    # 胜者的分桶 + 指代题 + Part B
    best = max([n for n, *_ in configs if n.startswith("rrf")], key=lambda n: results[n][1])
    print(f"\n===== 胜者：{best} =====")
    k = int(best.split("k=")[1].split()[0]) if "k=" in best else 10
    wc = 0.7 if "cos×0.7" in best else 1.0
    wr = 0.7 if "rr×0.7" in best else 1.0
    print("分桶（MRR 粗/精rrf | NDCG 粗/精rrf）：")
    by_type: dict[str, list] = {}
    for qid, q in answerable:
        top3c, _ = get_top3(pipes[qid]["raw"], "cos", q["labels"], q.get("chunk_labels", {}), all_chunks, k, wc, wr)
        top3f, _ = get_top3(pipes[qid]["raw"], "rrf", q["labels"], q.get("chunk_labels", {}), all_chunks, k, wc, wr)
        gc = order_grades(top3c, q["labels"], q.get("chunk_labels", {}), all_chunks)
        gf = order_grades(top3f, q["labels"], q.get("chunk_labels", {}), all_chunks)
        ideal = ideal_of(q)
        by_type.setdefault(q["type"], []).append((mrr(gc), mrr(gf), ndcg3(gc, ideal), ndcg3(gf, ideal)))
    for t, name in TYPE_NAMES.items():
        if t not in by_type:
            continue
        rows = by_type[t]
        print(f"  {name}: MRR {sum(r[0] for r in rows)/len(rows):.3f}→{sum(r[1] for r in rows)/len(rows):.3f} | "
              f"NDCG {sum(r[2] for r in rows)/len(rows):.3f}→{sum(r[3] for r in rows)/len(rows):.3f}")

    print("\n指代题（12 题，raw / concat 各自融合序）：")
    for var in ("raw", "concat"):
        Ms, Ns = [], []
        for qid, q in [(i, d) for i, d in dataset.items() if d["type"] == "anaphora"]:
            top3, _ = get_top3(pipes[qid][var], "rrf", q["labels"], q.get("chunk_labels", {}), all_chunks, k, wc, wr)
            g = order_grades(top3, q["labels"], q.get("chunk_labels", {}), all_chunks)
            Ms.append(mrr(g)); Ns.append(ndcg3(g, ideal_of(q)))
        print(f"  {var}: MRR {sum(Ms)/12:.3f} NDCG {sum(Ns)/12:.3f}")

    # Part B：融合序 top3 + rerank 0.01 闸（含指代重试），对照纯 rerank 序
    print(f"\n===== Part B（闸=rerank≥{config.RERANK_MIN_SCORE}，含指代重试）=====")
    print(f"{'排序':<10} {'平均引用':<6} {'覆盖率':<7} {'无引用':<6} {'P':<6} {'无关率':<6} {'top1':<6} OOV误引")
    answerable_ids = {qid for qid, q in dataset.items() if any(g >= REL for g in ideal_of(q))}
    for mode in ("rr", "rrf"):
        shown = clean = noise = nocite = cov = top1 = oov_fp = 0
        for qid, q in dataset.items():
            # 重试逻辑：首轮 raw，弱命中换 concat（与 sim_chat 一致，闸内联）
            def gated(pipe):
                top3, rs = get_top3(pipe, mode, q["labels"], q.get("chunk_labels", {}), all_chunks, k, wc, wr)
                return [c for c in top3 if rs.get(c["id"], 1.0) >= config.RERANK_MIN_SCORE]
            cites = gated(pipes[qid]["raw"])
            if q["context"]:
                ts = max((c["score"] for c in cites), default=0.0)
                if ts < config.RAG_RETRY_BELOW:
                    retry = gated(pipes[qid]["concat"])
                    if retry and max(c["score"] for c in retry) > ts:
                        cites = retry
            g = [grade_of_(c["id"], q["labels"], q.get("chunk_labels", {})) for c in cites]
            shown += len(g)
            clean += sum(1 for x in g if x >= REL)
            noise += sum(1 for x in g if x == 0)
            nocite += int(not g)
            if qid in answerable_ids:
                cov += int(any(x >= REL for x in g))
                top1 += int(bool(g) and g[0] >= REL)
            oov_fp += int(q["type"] == "oov" and bool(g))
        na = len(answerable_ids)
        print(f"{mode:<10} {shown/100:<6.2f} {cov/na:<7.3f} {nocite/100:<6.1%} {clean/max(shown,1):<6.3f} "
              f"{noise/max(shown,1):<6.3f} {top1/na:<6.3f} {oov_fp}/14")


if __name__ == "__main__":
    main()
