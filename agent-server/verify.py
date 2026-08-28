"""
生成后幻觉自检（RAG 面试文档 §9 的后置校验双策略）：
  策略② 输出自校验 —— 回答流结束后，用一次低温 LLM 调用把回答拆成事实性声明，
        逐条对照引用资料标注 supported / beyond / unsupported（宽松三档）；
  策略⑤ 检索-生成对齐 —— answer 与各引用块文本的最大余弦相似度，辅助信号
        （回答是共情文体、资料是科普文体，分数天然中庸，只进 payload 与日志、
        不参与 verdict 判定）。

调用方（main.py /rag/chat）：只在有 citations 且回答 ≥30 字时调用；本模块任何
失败（超时/JSON 解析失败/异常）都返回 None —— 调用方不发 verify 事件、照常 done，
自检绝不拖垮对话主链路（降级链第七层：自检失败 = 无自检）。
"""
import asyncio
import json
import math

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

import config
import rag
from llm import verify_llm

# 三档判定（宽松尺度：陪伴场景下回答几乎必带资料外的温和建议，
# 只有"编造具体事实"才算 fail，避免徽章常年黄着没人信）
VALID_STATUS = {"supported", "beyond", "unsupported"}

VERIFY_SYSTEM_PROMPT = "\n".join([
    "你是心理健康助手的事实核验员。对照参考资料，逐条核对回答中的事实性声明。",
    "只核事实性声明：具体说法、数字、研究结论、名称、明确步骤、因果断言。",
    "共情、鼓励、过渡语、一般性问候不是声明，不要列入。",
    "每条声明标注三档之一：",
    'supported —— 参考资料中有明确依据（含合理改写）；',
    'beyond —— 资料没提到，但属于心理健康领域的一般性常识或温和建议（不含具体数字/研究结论/明确步骤）；',
    'unsupported —— 与参考资料矛盾，或编造了资料中不存在的具体事实。',
    "输出格式：只输出一个 JSON 对象，不要输出任何其他文字、解释或 markdown 代码块。",
    '{"claims": [{"text": "回答中的声明原文摘录（40字内）", "status": "supported|beyond|unsupported"}]}',
])


def _parse_json_loose(raw: str) -> dict | None:
    """模型偶尔裹```json代码块或前后加说明文字：取第一个{到最后一个}之间兜底解析。
    （main.py 有一份同款；不互相 import 是为了保持模块独立、避免 main→verify→main 循环）"""
    text = raw.replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _content_text(content) -> str:
    """模型返回的 content 可能是 str 也可能是分块 list（与 main.py 同款容错）"""
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


async def _alignment(citations: list[dict], answer: str) -> float | None:
    """策略⑤：answer 与各引用块文本的最大余弦。embed_texts 一个批量带全（≤4 条），
    失败返回 None（对齐分可有可无，不影响主判定）。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            vecs = await rag.embed_texts([answer, *[c["text"][:300] for c in citations]], client)
        a, chunks = vecs[0], vecs[1:]
        return round(max(_cosine(a, c) for c in chunks if c), 3) if a else None
    except Exception:  # noqa: BLE001 —— 对齐分是辅助信号，挂了就没有
        return None


async def verify_answer(citations: list[dict], answer: str) -> dict | None:
    """逐条核对回答声明与引用资料。返回 verify 事件 payload：
    {verdict, supported, beyond, unsupported, claims, alignment}；None = 自检不可用。

    verdict 服务端从 claims 重算（不信模型自己给的总结）：有 unsupported→fail，
    有 beyond→warn，全 supported→pass。claims 为空（纯共情回答，没有事实性声明）
    也返回 None —— 没有声明就没有可核的，不展示徽章比亮一个空徽章诚实。"""
    docs = "\n\n".join(
        f"[{i + 1}] 《{c['articleTitle']}》—— {c['heading']}\n{c['text'][:300]}"
        for i, c in enumerate(citations)
    )
    user_content = f"参考资料：\n{docs}\n\n回答：\n{answer}"
    msgs = [SystemMessage(content=VERIFY_SYSTEM_PROMPT), HumanMessage(content=user_content)]

    # LLM 核对与对齐分并发跑，总耗时受 RAG_VERIFY_TIMEOUT 封顶
    async def _claims() -> list[dict]:
        resp = await verify_llm.ainvoke(msgs)
        data = _parse_json_loose(_content_text(resp.content)) or {}
        out = []
        for item in (data.get("claims") or []):
            if not isinstance(item, dict):
                continue
            text, status = str(item.get("text") or "").strip()[:60], str(item.get("status") or "")
            if text and status in VALID_STATUS:
                out.append({"text": text, "status": status})
        return out[:12]  # 300字回答的声明数有限，封顶防模型刷条目撑爆 payload

    try:
        claims, alignment = await asyncio.wait_for(
            asyncio.gather(_claims(), _alignment(citations, answer)),
            timeout=config.RAG_VERIFY_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 —— 自检失败≠对话失败
        # flush=True：uvicorn 重定向到文件时 stdout 是块缓冲，诊断日志必须立即落盘
        print(f"[RAG] 幻觉自检不可用，跳过 verify 事件：{type(e).__name__}: {e}", flush=True)
        return None

    if not claims:
        # 唯一无异常的静默路径（纯共情回答没有事实性声明），也要留痕
        print(f"[RAG] 幻觉自检：模型未返回有效声明，跳过（对齐分 {alignment}）", flush=True)
        return None
    unsupported = [c["text"] for c in claims if c["status"] == "unsupported"]
    beyond = [c["text"] for c in claims if c["status"] == "beyond"]
    verdict = "fail" if unsupported else ("warn" if beyond else "pass")
    print(f"[RAG] 幻觉自检：{verdict}（supported {len(claims) - len(unsupported) - len(beyond)}"
          f" / beyond {len(beyond)} / unsupported {len(unsupported)}，对齐分 {alignment}）", flush=True)
    return {
        "verdict": verdict,
        "supported": len(claims) - len(unsupported) - len(beyond),
        "beyond": len(beyond),
        "unsupported": unsupported,
        "claims": claims,
        "alignment": alignment,
    }
