"""
评测集建池工具：把 TESTSET 每题的粗排 top-10 候选池 dump 成 eval_pool.json，
供人工标注相关等级用（TREC pooling：只标系统实际暴露的候选，语料 150 篇全标不现实）。

用法：cd agent-server && python -X utf8 build_eval_pool.py
输出：eval_pool.json —— {query, type, context, candidates:[{articleId, title, heading, cosine, rerank}]}
标注时按 articleId 对应的文章打分（块继承文章级标注）。
"""
import asyncio
import json

import httpx

import config
import rag
from knowledge_base import ensure_built
from vector_store import get_vector_store

# 与 eval_dataset.json 的题型对齐：synonym 同义表达 / keyword 精确关键词 /
# anaphora 多轮指代 / oov 知识库外 / confusable 易混淆 / crisis 心理危机
QUERIES = [
    ("synonym", "什么都不想干，提不起劲", None),
    ("synonym", "心里堵得慌，脑子里两个小人天天打架", None),
    ("synonym", "一点小事就想发火，发完又后悔", None),
    ("synonym", "总觉得身边人都比我优秀", None),
    ("keyword", "惊恐发作是什么感觉", None),
    ("keyword", "长期失眠怎么办", None),
    ("keyword", "有强迫思维，反复检查门锁", None),
    ("keyword", "PTSD是什么", None),
    ("anaphora", "第二种方法是什么", "睡前焦虑睡不着有什么自救的办法"),
    ("anaphora", "第二个准备步骤展开讲讲", "怎么跟领导开口谈加薪"),
    ("anaphora", "时间线里第三个阶段是什么", "失恋了要多久才能走出来"),
    ("oov", "最近股票亏了好多钱，怎么回本", None),
    ("oov", "感冒发烧吃什么药好得快", None),
    ("oov", "帮我写一段Python爬虫代码", None),
    ("oov", "推荐几个适合五一去的旅游目的地", None),
    ("confusable", "焦虑症和抑郁症怎么区分", None),
    ("confusable", "我是内向还是社交焦虑", None),
    ("confusable", "职业倦怠和抑郁症是一回事吗", None),
    ("crisis", "我不想活了，活着没什么意义", None),
    ("crisis", "朋友说想自杀，我该怎么办", None),
]


async def main():
    config.RERANK_TIMEOUT = 10.0
    await ensure_built()
    store = get_vector_store()
    pool = []
    async with httpx.AsyncClient(timeout=30) as client:
        for typ, q, ctx in QUERIES:
            # 指代题按生产重试逻辑拼上下文检索；同时留单问检索对照（标注池取两者并集）
            variants = [q] + ([f"{ctx[:80]}\n{q}"] if ctx else [])
            seen, cands = set(), []
            for text in variants:
                qv = (await rag.embed_texts([text], client))[0]
                for c in store.query(qv, config.RERANK_CANDIDATES):
                    if c["id"] not in seen:
                        seen.add(c["id"])
                        cands.append(c)
            reranked = await rag._rerank(q, cands)  # 池内重排只为看分数带，排序仍以单问为准
            rscore = {c["id"]: round(s, 4) for c, s in (reranked or [])}
            pool.append({
                "type": typ, "query": q, "context": ctx,
                "candidates": [
                    {
                        "articleId": c["articleId"], "title": c["articleTitle"],
                        "heading": c["heading"], "cosine": c["score"],
                        "rerank": rscore.get(c["id"]),
                    }
                    for c in cands
                ],
            })
            print(f"pool ok: [{typ}] {q}（{len(cands)} 候选）")
    with open("eval_pool.json", "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=1)
    print(f"\n共 {len(pool)} 题 → eval_pool.json")


if __name__ == "__main__":
    asyncio.run(main())
