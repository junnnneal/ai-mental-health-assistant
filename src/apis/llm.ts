/**
 * 智谱GLM统一客户端：流式对话 + 非流式对话 + embedding向量化
 * 全部走vite代理 /llm → https://open.bigmodel.cn（key由Node侧注入，前端不暴露）
 */

export interface LlmMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

const CHAT_URL = "/llm/api/paas/v4/chat/completions";
const EMBED_URL = "/llm/api/paas/v4/embeddings";
//用固定版本号而非glm-4-flash别名：实测别名排队抖动大（TTFT 0.4~1.8s），
//固定版本稳定在200ms级（2026-08实测）
const CHAT_MODEL = "glm-4-flash-250414";
const EMBED_MODEL = "embedding-2";

/**
 * 非流式对话：一次拿全量回复
 * （RAG外的单轮任务用；流式打字机场景用下面的 chatCompletionStream）
 */
export const chatCompletion = async (
  messages: LlmMessage[],
  options?: { temperature?: number },
) => {
  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: CHAT_MODEL,
      messages,
      temperature: options?.temperature,
    }),
  });
  if (!res.ok) {
    throw new Error(`LLM接口异常：${res.status}`);
  }
  const json = await res.json();
  return String(json?.choices?.[0]?.message?.content ?? "");
};

/**
 * 流式对话：SSE逐段回调delta，供打字机渲染
 * 用原生fetch+ReadableStream解析，不依赖fetchEventSource
 */
export const chatCompletionStream = async (
  messages: LlmMessage[],
  callbacks: {
    onDelta: (text: string) => void;
    onDone: () => void;
  },
  signal?: AbortSignal,
) => {
  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      model: CHAT_MODEL,
      stream: true,
      messages,
    }),
    signal,
  });
  const contentType = res.headers.get("content-type") || "";
  if (!res.ok || !contentType.includes("event-stream")) {
    throw new Error(`LLM流式接口异常：${res.status} ${res.statusText}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  //SSE事件可能被网络分片切断：半行留在buffer等下一批数据拼完
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const data = line.replace(/^data:/, "").trim();
      if (!data) {
        continue;
      }
      //OpenAI兼容流式以[DONE]标记结束
      if (data === "[DONE]") {
        callbacks.onDone();
        return;
      }
      try {
        const payload = JSON.parse(data);
        const delta = payload?.choices?.[0]?.delta?.content;
        if (delta) {
          callbacks.onDelta(delta);
        }
      } catch {
        //不完整的JSON行：跳过，等buffer拼齐
      }
    }
  }
  //服务端没发[DONE]就关流：按正常结束处理
  callbacks.onDone();
};

/**
 * 向量化：文本数组 → 等长向量数组（RAG检索用）
 * 返回按index还原顺序，不依赖接口返回顺序
 */
export const embedding = async (input: string[]): Promise<number[][]> => {
  const res = await fetch(EMBED_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: EMBED_MODEL, input }),
  });
  if (!res.ok) {
    throw new Error(`embedding接口异常：${res.status}`);
  }
  const json = await res.json();
  const list = (json?.data || []) as { index: number; embedding: number[] }[];
  const out: number[][] = new Array(input.length);
  list.forEach((d) => {
    out[d.index] = d.embedding;
  });
  return out;
};
