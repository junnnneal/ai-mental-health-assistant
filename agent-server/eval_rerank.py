"""
重排效果判定 v2：两段式协议（基于人工标注分级测试集 eval_dataset.json，100 题）。

用法：cd agent-server && python -X utf8 eval_rerank.py
输出：控制台报告 + eval_report.md

Part A 纯排序能力（不加阈值）：直接取 rerank 排序后的 Top 3，评 MRR / NDCG@3 / P@3 / Hit@3，
        与余弦原序 Top 3 对照。阈值无关，回答"reranker 排序本身行不行"。
Part B 阈值扫描：闸门 0 / 0.01 / 0.03 / 0.05 / 0.08 / 0.1（rerank 在场，逐档离线复算），
        另加基线行 rerank-OFF（余弦 top3 + 0.40 闸，生产回退路径）。观测：
        引用覆盖率 / 无引用问题比例 / Precision / Recall / 无关引用率 / top1正确率(答案质量代理) / 平均引用数。
诊断规则：若降低阈值只是"引用条数变多"，而 Part A 的 MRR / NDCG 不升，则不是阈值问题，是排序问题。

标注口径：0 不相关 / 1 部分相关 / 2 相关 / 3 高度相关；块继承文章级，可按小节覆盖；池外未标注=0。
"""
import asyncio
import hashlib
import json
import math
import os
import time

import httpx

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
    return next((1 / (i + 1) for i, g in enumerate(grades) if g >= REL), 0.0)


def ndcg3(grades: list[int], ideal: list[int]) -> float:
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:3]))
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(ideal, reverse=True)[:3]))
    return dcg / idcg if idcg else 0.0


# ---------------- 检索（每题只跑一次，闸门全部离线复算） ----------------

async def run_pipeline(query: str, store, client) -> dict:
    qv = (await rag.embed_texts([query], client))[0]
    cands = store.query(qv, config.RERANK_CANDIDATES)
    t0 = time.perf_counter()
    reranked = await rag._rerank(query, cands)
    dt = time.perf_counter() - t0
    return {"cands": cands, "reranked": reranked, "rerank_ok": reranked is not None, "rerank_latency": dt}


def gate_top3(pipe: dict, t: float) -> list[dict]:
    """离线复刻 rag.retrieve：rerank top3 按 rerank 分数 ≥t 过闸；rerank 失败回退余弦 + RAG_MIN_SCORE"""
    if pipe["reranked"] is not None:
        top = pipe["reranked"][: config.RAG_TOP_K]
        return [c for c, s in top if s >= t]
    top = pipe["cands"][: config.RAG_TOP_K]
    return [c for c in top if c["score"] >= config.RAG_MIN_SCORE]


def gate_top3_cos(pipe: dict, t: float) -> list[dict]:
    """rerank-OFF 基线：余弦 top3 + 余弦闸"""
    return [c for c in pipe["cands"][: config.RAG_TOP_K] if c["score"] >= t]


def sim_chat(q, pipes, t, mode="rerank"):
    """离线复刻 main.py /rag/chat 检索段：首轮(闸t) → 弱命中(<RAG_RETRY_BELOW)拼上轮重试(闸t) → 分高才换。
    返回 (放行引用, 实际采用的管线)——重试换池后 Recall 分母要跟实际池走。"""
    g = gate_top3 if mode == "rerank" else gate_top3_cos
    used = pipes["raw"]
    cites = g(used, t)
    if q["context"]:
        top_score = max((c["score"] for c in cites), default=0.0)
        if top_score < config.RAG_RETRY_BELOW:
            retry = g(pipes["concat"], t)
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
    CACHE = "eval_pipes_cache.json"
    fp = hashlib.sha1(json.dumps({qid: {"query": q["query"], "context": q.get("context")}
                                  for qid, q in dataset.items()},
                                 ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    pipes: dict[str, dict] = {}
    latencies = []
    if os.path.exists(CACHE) and json.load(open(CACHE, encoding="utf-8")).get("fingerprint") == fp:
        cached = json.load(open(CACHE, encoding="utf-8"))["pipes"]
        for qid, p in cached.items():
            pipes[qid] = {var: {"cands": pl["cands"],
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
        ser = {qid: {var: {"cands": pl["cands"],
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
    out(f"候选池 top-{config.RERANK_CANDIDATES} → rerank（{config.RERANK_MODEL}）→ Top3。"
        f"相关口径 grade≥{REL}，NDCG 增益 2^grade-1。指代题/OOV 不进主表。\n")

    main_q = [(qid, i) for qid, i in info.items() if i["q"]["type"] not in ("anaphora", "oov")]
    answerable_main = [(qid, i) for qid, i in main_q if i["answerable"]]
    out(f"## Part A 纯排序能力（不加阈值，rerank Top3 直接评分；主表 {len(answerable_main)} 题有标准答案）\n")
    out("诊断意义：MRR/NDCG@3 与阈值无关——若 rerank 后不升反降，问题在排序不在阈值。\n")
    out("| 问题 | 类型 | R@10 | MRR 粗→精 | NDCG@3 粗→精 | P@3 粗→精 | Hit@3 粗→精 |")
    out("|---|---|---|---|---|---|---|")
    agg = {k: [] for k in ("recall10", "cos_mrr", "rr_mrr", "cos_n", "rr_n", "cos_p3", "rr_p3", "cos_h3", "rr_h3")}
    by_type: dict[str, dict] = {}
    for qid, i in answerable_main:
        c_g, r_g, ideal = i["cos_g"], i["rr_g"], i["ideal"]
        recall10 = (len({all_chunks[c['id']]['articleId'] for c in pipes[qid]['raw']['cands']} & i["rel_articles"])
                    / len(i["rel_articles"]))
        vals = {"recall10": recall10,
                "cos_mrr": mrr(c_g), "rr_mrr": mrr(r_g),
                "cos_n": ndcg3(c_g, ideal), "rr_n": ndcg3(r_g, ideal),
                "cos_p3": p3(c_g), "rr_p3": p3(r_g),
                "cos_h3": hit3(c_g), "rr_h3": hit3(r_g)}
        for k, v in vals.items():
            agg[k].append(v)
            by_type.setdefault(i["q"]["type"], {}).setdefault(k, []).append(v)
        out(f"| {i['q']['query'][:22]} | {i['q']['type']} | {recall10:.2f} | "
            f"{vals['cos_mrr']:.2f}→{vals['rr_mrr']:.2f} | {vals['cos_n']:.3f}→{vals['rr_n']:.3f} | "
            f"{vals['cos_p3']:.2f}→{vals['rr_p3']:.2f} | {vals['cos_h3']}→{vals['rr_h3']} |")
    A = lambda k: sum(agg[k]) / max(len(agg[k]), 1)  # noqa: E731
    out(f"| **平均（{len(answerable_main)}题）** | | **{A('recall10'):.3f}** | "
        f"**{A('cos_mrr'):.3f}→{A('rr_mrr'):.3f}** | **{A('cos_n'):.3f}→{A('rr_n'):.3f}** | "
        f"**{A('cos_p3'):.3f}→{A('rr_p3'):.3f}** | **{A('cos_h3'):.3f}→{A('rr_h3'):.3f}** |\n")

    out("### 按题型分桶（Part A）\n")
    out("| 题型 | 题数 | R@10 | MRR 粗→精 | NDCG@3 粗→精 | P@3 粗→精 | Hit@3 粗→精 |")
    out("|---|---|---|---|---|---|---|")
    for t, name in TYPE_NAMES.items():
        if t not in by_type:
            continue
        b = by_type[t]
        m = lambda k: sum(b[k]) / max(len(b[k]), 1)  # noqa: E731
        out(f"| {name} | {len(b['cos_mrr'])} | {m('recall10'):.3f} | {m('cos_mrr'):.3f}→{m('rr_mrr'):.3f} | "
            f"{m('cos_n'):.3f}→{m('rr_n'):.3f} | {m('cos_p3'):.3f}→{m('rr_p3'):.3f} | {m('cos_h3'):.3f}→{m('rr_h3'):.3f} |")
    out()
    # 主表无标准答案的题（Hit 恒 0，单列说明）
    noans = [(qid, i) for qid, i in main_q if not i["answerable"]]
    if noans:
        out(f"注：{len(noans)} 题标注最高仅 1 分（无 grade≥2 目标），不进 Part A 排序评测："
            + "、".join(qid for qid, _ in noans) + "\n")

    # ---- 指代题排序（raw / concat 两变体，仍不加阈值） ----
    out("## Part A-2 多轮指代题（12 题）：裸问 vs 拼上下文，rerank Top3 不加阈值\n")
    out("| 问题(上下文) | 变体 | MRR | NDCG@3 | P@3 | Hit@3 | top1等级 |")
    out("|---|---|---|---|---|---|---|")
    ana_stats = {"raw": [], "concat": []}
    for qid, i in [(k, v) for k, v in info.items() if v["q"]["type"] == "anaphora"]:
        for var in ("raw", "concat"):
            g = grades_of(pipes[qid][var]["reranked"] or pipes[qid][var]["cands"], i["labels"], i["chunk_labels"])
            ana_stats[var].append((mrr(g), ndcg3(g, i["ideal"]), p3(g), hit3(g)))
            out(f"| {i['q']['query'][:12]}（{i['q']['context'][:10]}…） | {var} | {mrr(g):.2f} | {ndcg3(g, i['ideal']):.3f} | {p3(g):.2f} | {hit3(g)} | {g[0] if g else '-'} |")
    for var, cn in (("raw", "裸问"), ("concat", "拼接")):
        s = ana_stats[var]
        out(f"| **平均({cn})** | | **{sum(x[0] for x in s)/len(s):.3f}** | **{sum(x[1] for x in s)/len(s):.3f}** | "
            f"**{sum(x[2] for x in s)/len(s):.3f}** | **{sum(x[3] for x in s)/len(s):.3f}** | |")
    out()

    # ================= Part B：阈值扫描 =================
    out("## Part B 阈值扫描（rerank 在场，闸门作用于 rerank 分数；基线行=rerank OFF 余弦闸 0.40）\n")
    out("每题检索只跑一次，六档闸门离线复算（与生产 rag.retrieve/main.py 逻辑逐行一致，含指代重试）。\n")
    out("指标定义：")
    out("- 引用覆盖率 = 有标准答案的题中，至少 1 条 grade≥2 引用被放行的比例")
    out("- 无引用比例 = 全部 100 题中出 0 条引用的比例（OOV 零引用是正确行为，14 题全部拦下时下限 14%）")
    out("- Precision = 放行块中 grade≥2 的比例；无关引用率 = 放行块中 grade0 的比例")
    out("- Recall = 放行的 grade≥2 块 / 闸前 rerank Top3 中的 grade≥2 块（闸门对排序结果的破坏度）")
    out("- top1正确率 = 有答案题中 top1 引用 grade≥2 的比例（最终答案质量代理——真实答案质量需 LLM 评审，另计）\n")

    answerable_all = {qid: i for qid, i in info.items() if i["answerable"]}
    configs = [("OFF(余弦0.40)", "cos", config.RAG_MIN_SCORE)] + [(f"ON@{t}", "rerank", t) for t in GATES]
    out("| 配置 | 平均引用数 | 引用覆盖率 | 无引用比例 | Precision | Recall | 无关引用率 | top1正确率 | OOV误引用 |")
    out("|---|---|---|---|---|---|---|---|---|")
    sweep = {}
    for name, mode, t in configs:
        shown_total = clean_total = noise_total = 0
        pool_rel_total = 0  # 闸前 top3 中 grade≥2 块数
        covered = top1_ok = nocite = oov_fp = 0
        for qid, i in info.items():
            cites, used = sim_chat(i["q"], pipes[qid], t, mode)
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
            # 闸前 top3 的相关块：跟实际采用的池走（重试换池后分母同步换），rerank 失败回退余弦序
            pre = used["reranked"][: config.RAG_TOP_K] if (mode == "rerank" and used["reranked"] is not None) \
                else used["cands"][: config.RAG_TOP_K]
            pre_items = [c for c, _ in pre] if (pre and isinstance(pre[0], tuple)) else pre
            pool_rel_total += sum(1 for c in pre_items
                                  if grade_of(c["id"], all_chunks[c["id"]], i["labels"], i["chunk_labels"]) >= REL)
        na = len(answerable_all)
        sweep[name] = {"cov": covered / na, "nocite": nocite / len(info), "prec": clean_total / max(shown_total, 1),
                       "rec": clean_total / max(pool_rel_total, 1), "noise": noise_total / max(shown_total, 1),
                       "top1": top1_ok / na, "oov_fp": oov_fp, "avg": shown_total / len(info)}
        out(f"| {name} | {sweep[name]['avg']:.2f} | {sweep[name]['cov']:.3f} | {sweep[name]['nocite']:.1%} | "
            f"{sweep[name]['prec']:.3f} | {sweep[name]['rec']:.3f} | {sweep[name]['noise']:.3f} | "
            f"{sweep[name]['top1']:.3f} | {oov_fp}/14 |")
    out()

    # ---- 分数带佐证（排序问题 vs 阈值问题的直接证据） ----
    out("## 佐证：rerank 分数按标注等级的分布（是否可分 = 是否存在『完美阈值』）\n")
    main_samples = []
    for qid, i in info.items():
        if i["q"]["type"] in ("anaphora", "oov"):
            continue
        rs = {c["id"]: s for c, s in (pipes[qid]["raw"]["reranked"] or [])}
        for c in pipes[qid]["raw"]["cands"]:
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
    out("| 问题 | 余弦最高分 | rerank最高分 |")
    out("|---|---|---|")
    for qid, i in [(k, v) for k, v in info.items() if v["q"]["type"] == "oov"]:
        max_cos = max((c["score"] for c in pipes[qid]["raw"]["cands"]), default=0)
        max_rr = max((s for _, s in (pipes[qid]["raw"]["reranked"] or [])), default=0)
        out(f"| {i['q']['query'][:24]} | {max_cos:.3f} | {max_rr:.4f} |")
    out()

    # ---- 可用性 ----
    lat = sorted(latencies)
    out("## 附：rerank 可用性\n")
    out(f"- 调用成功率 {len(lat)}/{sum(len(p) for p in pipes.values())}，延迟 avg {sum(lat)/len(lat):.2f}s / "
        f"p95 {lat[max(0, int(len(lat)*0.95)-1)]:.2f}s / max {lat[-1]:.2f}s")
    out(f"- 生产 2s 超时线：{sum(1 for x in lat if x > 2.0)}/{len(lat)} 次会被打掉\n")

    # ---- 自动诊断结论 ----
    out("## 诊断结论（按『降阈值引用变多但 MRR/NDCG 不升 = 排序问题』规则）\n")
    d_mrr = A("rr_mrr") - A("cos_mrr")
    d_ndcg = A("rr_n") - A("cos_n")
    cov_loose, cov_tight = sweep["ON@0"]["cov"], sweep["ON@0.1"]["cov"]
    out(f"1. Part A（阈值无关）：rerank 使 MRR {A('cos_mrr'):.3f}→{A('rr_mrr'):.3f}（{d_mrr:+.3f}），"
        f"NDCG@3 {A('cos_n'):.3f}→{A('rr_n'):.3f}（{d_ndcg:+.3f}）——reranker 对本题库排序"
        f"{'提升' if d_ndcg > 0.005 else ('持平' if d_ndcg > -0.005 else '净损伤')}。")
    out(f"2. Part B：闸门 0.1→0 放松，平均引用数 {sweep['ON@0.1']['avg']:.2f}→{sweep['ON@0']['avg']:.2f}（引用条数变多），"
        f"覆盖率 {cov_tight:.3f}→{cov_loose:.3f}，代价是无关引用率 {sweep['ON@0.1']['noise']:.3f}→{sweep['ON@0']['noise']:.3f}、"
        f"OOV 误引用 {sweep['ON@0.1']['oov_fp']}/14→{sweep['ON@0']['oov_fp']}/14；"
        f"而 Part A 的排序质量与阈值无关，全程不动。")
    if d_ndcg <= 0.005 and cov_loose > cov_tight:
        out(f"3. 判定：降低阈值只带来『引用条数变多』，MRR / NDCG 并未因此改善（rerank 排序本身净"
            f"{'持平' if d_ndcg > -0.005 else '损伤'}）→ **主要矛盾是排序问题，不是阈值问题**。"
            "继续调阈值只能在覆盖率与噪声之间挪动，无法提升答案质量上限；优化要动排序侧。")
    else:
        out("3. 判定：排序侧有正向收益，阈值与排序值得同步调优，按上表选覆盖/噪声平衡点。")
    base = sweep["OFF(余弦0.40)"]
    best_on = max(GATES, key=lambda t: sweep[f"ON@{t}"]["cov"] - sweep[f"ON@{t}"]["noise"])
    out(f"4. 基线对照：rerank-OFF@0.40 覆盖 {base['cov']:.3f} / 无关 {base['noise']:.3f}；"
        f"rerank 在场时覆盖-噪声平衡最好的档位是 ON@{best_on}（覆盖 {sweep[f'ON@{best_on}']['cov']:.3f} / "
        f"无关 {sweep[f'ON@{best_on}']['noise']:.3f}）——rerank 必须保留的前提下，"
        f"闸门建议从当前 {config.RERANK_MIN_SCORE} 移至 {best_on} 附近，并把优化力气花在排序侧"
        f"（混合余弦分、查询改写、扩大候选池）而非继续收紧/放宽绝对阈值。\n")

    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("报告已写入 eval_report.md")


if __name__ == "__main__":
    asyncio.run(main())
