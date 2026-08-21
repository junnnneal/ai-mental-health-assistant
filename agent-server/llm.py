"""
ChatOpenAI 工厂：GLM 走 OpenAI 兼容协议，base_url/model/api_key 统一从 config 取。
此前同样的构造硬编码在 graph.py 一处；/rag/chat 和 /analyze 落地后共三处使用，
收进一个构造点，换模型/换地址只改环境变量。

temperature=None 时不传该参数（GLM 用服务端默认），与前端 chatCompletionStream
直连时的行为完全一致——迁移前后模型输入不变是本次重构的行为基准。
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from config import CHAT_MODEL, GLM_API_KEY, GLM_BASE_URL


def make_llm(temperature: Optional[float] = None, streaming: bool = False) -> ChatOpenAI:
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if streaming:
        # astream_events 拿 token 级事件必须开，否则只有整段消息事件
        kwargs["streaming"] = True
    return ChatOpenAI(
        model=CHAT_MODEL,
        base_url=GLM_BASE_URL,
        api_key=GLM_API_KEY,
        **kwargs,
    )


# 咨询页 /rag/chat：不传温度（对齐前端直连现行为），astream 逐字流出
rag_llm = make_llm()
# /analyze 情绪分析：低温采样，要稳定的结构化 JSON，不要发散
analyze_llm = make_llm(temperature=0.2)
# 健康管家 ReAct：对流式事件敏感，必须开 streaming
agent_llm = make_llm(temperature=0.7, streaming=True)
