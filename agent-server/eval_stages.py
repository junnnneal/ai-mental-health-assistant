"""
分阶段评估（rerank 有效性的规范拆法）：
  阶段1 召回：Chroma / BM25 / union / RRF合并池 各路单独的 R@N 与 Hit@N
    —— rerank 只能重排已召回的候选，救不回没进池的块（附不可挽回 miss 数）
  阶段2 精排：同一 keep10 候选池上只变排序——合并RRF序（无rerank，生产降级路径）
    vs rerank序 vs RRF(cos,rr)融合序（生产定案），MRR/NDCG/P@3/Hit@3 + R@3
  阶段3 端到端：未做 LLM A/B（诚实标注），见报告尾注

数据源：eval_width_cache.json（宽抓缓存，rerank 分逐对独立，离线复算零 API）。
用法：cd agent-server && python -X utf8 eval_stages.py
输出：控制台 + eval_stages_report.md
"""
import asyncio
import hashlib
import json
import os

from eval_rerank import REL, grade_of, load_kb_chunks, hit3, mrr, ndcg3, p3
from eval_width import build_pipe, make_two_stage, merged_order
from knowledge_base import ensure_built

WIDTH, KEEP = 15, 10


def _union(pipe: dict, n: int) -> list[dict]:
    seen = {c["id"] for c in pipe["cands"][:n]}
    out = list(pipe["cands"][:n])
    for c, _ in pipe["bm25"][:n]:
        if c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out


async def main():
    await ensure_built()
    with open("eval_dataset.json", encoding="utf-8") as f:
        dataset = {q["id"]: q for q in json.load(f)["queries"]}

    fp = hashlib.sha1("v1-width15|".encode() + json.dumps(
        {qid: {"query": q["query"], "context": q.get("context")} for qid, q in dataset.items()},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    cache_file = "eval_width_cache.json"
    if not os.path.exists(cache_file) or json.load(open(cache_file, encoding="utf-8")).get("fingerprint") != fp:
        raise SystemExit("eval_width_cache.json 指纹不匹配：先跑 eval_width.py 重建缓存")
    wide = json.load(open(cache_file, encoding="utf-8"))["wide"]
    pipes = {qid: {var: build_pipe(pl, WIDTH) for var, pl in p.items()} for qid, p in wide.items()}

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
    answerable = [(qid, i) for qid, i in main_q if i["answerable"]]

    def g_of(c, i):
        return grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"])

    def art_recall(cands, i):
        return (len({all_chunks[c["id"]]["articleId"] for c in cands} & i["rel_articles_set"])
                / len(i["rel_articles_set"]))

    lines: list[str] = []
    def out(s=""):
        print(s)
        lines.append(s)

    out("# 分阶段评估：召回 → 精排（rerank 有效性检验；离线复算自 eval_width_cache）\n")

    # ---------- 阶段1：召回 ----------
    out(f"## 阶段1 召回（{len(answerable)} 题；R@N=文章级全召回率，Hit@N=块级至少一个相关）\n")
    out("| 召回路 | R@10 | R@15 | Hit@10 | Hit@15 |")
    out("|---|---|---|---|---|")
    legs = [
        ("Chroma 余弦", lambda p, n: p["cands"][:n]),
        ("BM25 词法", lambda p, n: [c for c, _ in p["bm25"][:n]]),
        ("并集 union", _union),
    ]
    for name, leg in legs:
        r10 = r15 = h10 = h15 = 0.0
        for qid, i in answerable:
            p = pipes[qid]["raw"]
            r10 += art_recall(leg(p, 10), i); r15 += art_recall(leg(p, 15), i)
            h10 += int(any(g_of(c, i) >= REL for c in leg(p, 10)))
            h15 += int(any(g_of(c, i) >= REL for c in leg(p, 15)))
        n = len(answerable)
        out(f"| {name} | {r10/n:.3f} | {r15/n:.3f} | {h10/n:.3f} | {h15/n:.3f} |")
    # RRF 合并池（实际送精排的 keep10）
    rp = hp = 0.0
    for qid, i in answerable:
        pool = merged_order(pipes[qid]["raw"], KEEP)
        rp += art_recall(pool, i)
        hp += int(any(g_of(c, i) >= REL for c in pool))
    n = len(answerable)
    out(f"| RRF(cos,bm) 合并 keep{KEEP}（送精排池） | - | {rp/n:.3f}* | - | {hp/n:.3f}* |")
    out(f"\n*列标注 15：合并池由 15+15 两路产生、只保留前 {KEEP} 个。\n")
    miss = [qid for qid, i in answerable if art_recall(_union(pipes[qid]["raw"], 15), i) < 1.0]
    out(f"- union15 仍未召回全部相关文章的题：{len(miss)}/{n}（rerank 无法弥补，只能靠扩语料/调召回）\n")

    # ---------- 阶段2：精排（同池只变排序） ----------
    out(f"## 阶段2 精排（同一候选池 = RRF(cos,bm) 合并 keep{KEEP}，不加闸门，只比较排序）\n")
    no_rr = sum(1 for qid, _ in answerable if pipes[qid]["raw"]["reranked"] is None)

    def order_merge(p):  # 无 rerank：合并 RRF 序直接取（生产降级路径）
        return merged_order(p, KEEP)

    def order_rr(p):  # rerank 序独裁
        if p["reranked"] is None:
            return merged_order(p, KEEP)
        rs = {c["id"]: s for c, s in p["reranked"]}
        return sorted(merged_order(p, KEEP), key=lambda c: -rs.get(c["id"], float("-inf")))

    order_fused = make_two_stage(WIDTH, KEEP)  # 生产：RRF(cos序, rr序) 定序
    out("| 排序方式 | MRR | NDCG@3 | P@3 | Hit@3 | R@3(文章级) | top1正确率 |")
    out("|---|---|---|---|---|---|---|")
    for name, order_fn in [
        (f"合并 RRF 序（无 rerank，降级路径）", order_merge),
        (f"rerank 序（独裁）", order_rr),
        (f"RRF(cos,rr) 融合序（生产）", order_fused),
    ]:
        Ms = Ns = Ps = Hs = Rs = T1 = 0.0
        for qid, i in answerable:
            g = [g_of(c, i) for c in order_fn(pipes[qid]["raw"])][:3]
            Ms += mrr(g); Ns += ndcg3(g, i["ideal"]); Ps += p3(g); Hs += hit3(g)
            Rs += art_recall(order_fn(pipes[qid]["raw"])[:3], i)
            T1 += int(bool(g) and g[0] >= REL)
        n = len(answerable)
        out(f"| {name} | {Ms/n:.3f} | {Ns/n:.3f} | {Ps/n:.3f} | {Hs/n:.3f} | {Rs/n:.3f} | {T1/n:.3f} |")
    out(f"\n- rerank 不可用的题：{no_rr}/{len(answerable)}（这些题三种排序退化为同一合并序）")
    out("- rerank 延迟（union15≈15~25 候选）：avg 0.45s / p95 0.60s（宽度报告实测）\n")

    out("## 阶段3 端到端（RRF→top3→LLM vs RRF→rerank→top3→LLM）\n")
    out("- 未做 LLM 回答 A/B（成本与稳定性考虑，诚实标注）；已有替代信号：")
    out("  - 检索质量差 → 回答差的可追溯链路：阶段2 排序指标 + 闸后全链路指标（eval_width_report Part B）")
    out("  - 生成侧幻觉自检（verify 三档）已上线，可观察 unsupported 声明率")
    out("  - 延迟：rerank avg 0.45s 发生在流开始前，不拖首字（知识库 3s 软超时兜底）")
    out("- 待优化项：抽样题人工/LLM 评审回答准确率与 Faithfulness 的 A/B\n")

    with open("eval_stages_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("报告已写入 eval_stages_report.md")


if __name__ == "__main__":
    asyncio.run(main())
