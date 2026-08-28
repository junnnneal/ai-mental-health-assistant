"""
闸门重校实验 v1：两段式定案架构（15+15 召回 → RRF 合并 keep10 → rerank → RRF(cos,rr) 定序）
下重扫 rerank 绝对分阈值。旧闸 0.01 是并集池时代（eval_report Part B）校准的，
排序换成两段式后闸-序相互作用改变（OOV 误引用 4/14→5/14），需要在新架构下重扫。

数据源：eval_width_cache.json（宽抓缓存，rerank 分逐对独立，离线复算零 API）。
用法：cd agent-server && python -X utf8 eval_gate.py
输出：控制台 + eval_gate_report.md
"""
import asyncio
import hashlib
import json
import os

import config
from eval_rerank import REL, grade_of, load_kb_chunks
from eval_width import build_pipe, make_two_stage
from knowledge_base import ensure_built

TOPK = config.RAG_TOP_K
WIDTH, KEEP = 15, 10
GATES = [0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1]


def sim_chat(q, pipes, order_fn, gate: float):
    """离线复刻 main.py /rag/chat 检索段（闸参数化，含指代重试）"""
    def g(pipe):
        if pipe["reranked"] is None:
            return [c for c in pipe["cands"][:TOPK] if c["score"] >= config.RAG_MIN_SCORE]
        rs = {c["id"]: s for c, s in pipe["reranked"]}
        return [c for c in order_fn(pipe)[:TOPK] if rs.get(c["id"], 0.0) >= gate]

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

    fp = hashlib.sha1("v1-width15|".encode() + json.dumps(
        {qid: {"query": q["query"], "context": q.get("context")} for qid, q in dataset.items()},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    cache_file = "eval_width_cache.json"
    if not os.path.exists(cache_file) or json.load(open(cache_file, encoding="utf-8")).get("fingerprint") != fp:
        raise SystemExit("eval_width_cache.json 指纹不匹配：先跑 eval_width.py 重建缓存")
    wide = json.load(open(cache_file, encoding="utf-8"))["wide"]

    # 两段式 15+15 keep10 的定序函数与每题管线（只裁宽度 15 一种）
    order_fn = make_two_stage(WIDTH, KEEP)
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
                     "answerable": any(g >= REL for g in ideal)}
    answerable_all = {qid for qid, i in info.items() if i["answerable"]}

    lines: list[str] = []
    def out(s=""):
        print(s)
        lines.append(s)

    out("# 闸门重校实验（两段式 15+15 keep10 定案架构下扫 rerank 阈值；离线复算自 eval_width_cache）\n")
    out(f"排序恒为两段式 RRF；闸门作用于 rerank 绝对分；GATES={GATES}；现行闸 {config.RERANK_MIN_SCORE}\n")
    out("| 闸门 | 平均引用数 | 引用覆盖率 | 无引用比例 | Precision | 无关引用率 | top1正确率 | OOV误引用 |")
    out("|---|---|---|---|---|---|---|---|")
    rows: dict[float, dict] = {}
    for t in GATES:
        shown = clean = noise = covered = top1ok = nocite = oov_fp = 0
        oov_leak = []
        for qid, i in info.items():
            cites, _ = sim_chat(i["q"], pipes[qid], order_fn, t)
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
                oov_leak.append(qid)
        na = len(answerable_all)
        rows[t] = {"cov": covered / na, "nocite": nocite / len(info), "prec": clean / max(shown, 1),
                   "noise": noise / max(shown, 1), "top1": top1ok / na, "oov_fp": oov_fp,
                   "avg": shown / len(info), "leak": oov_leak}
        r = rows[t]
        out(f"| {t} | {r['avg']:.2f} | {r['cov']:.3f} | {r['nocite']:.1%} | {r['prec']:.3f} | "
            f"{r['noise']:.3f} | {r['top1']:.3f} | {r['oov_fp']}/14 |")
    out()

    # OOV 漏网细节：各闸下仍漏的题
    out("## OOV 漏网明细（按闸门档位）\n")
    for t in GATES:
        if rows[t]["leak"]:
            out(f"- 闸 {t}：{len(rows[t]['leak'])} 题漏网：" +
                "、".join(f"{qid}「{info[qid]['q']['query'][:14]}」" for qid in rows[t]["leak"]))
    out()

    # 推荐档：覆盖损失 ≤0.5pt 且 OOV/噪声显著改善的最高闸
    base = rows[0.01]
    out("## 结论\n")
    cands = [t for t in GATES if t >= 0.01 and rows[t]["cov"] >= base["cov"] - 0.005]
    best = max(cands, key=lambda t: (rows[t]["oov_fp"], -rows[t]["noise"]))
    out(f"- 现行 0.01：覆盖 {base['cov']:.3f} / 噪声 {base['noise']:.3f} / OOV {base['oov_fp']}/14 / top1 {base['top1']:.3f}")
    out(f"- 覆盖几乎不损（≤0.5pt）前提下最干净的闸：**{best}**（覆盖 {rows[best]['cov']:.3f} / "
        f"噪声 {rows[best]['noise']:.3f} / OOV {rows[best]['oov_fp']}/14 / top1 {rows[best]['top1']:.3f}）")
    d_cov, d_noise = rows[best]["cov"] - base["cov"], rows[best]["noise"] - base["noise"]
    out(f"- 相对 0.01：覆盖 {d_cov:+.3f}、无关引用率 {d_noise:+.3f}、OOV {rows[best]['oov_fp']-base['oov_fp']:+d}、"
        f"top1 {rows[best]['top1']-base['top1']:+.3f}\n")

    with open("eval_gate_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("报告已写入 eval_gate_report.md")


if __name__ == "__main__":
    asyncio.run(main())
