/**
 * agent-server（Python FastAPI，RAG/Agent 服务端）统一客户端。
 * 全部走 /agent/* 路径：开发环境 vite 代理转发到 localhost:8000，
 * 生产环境 Netlify agent.mjs 转发到 Render——前端代码零差异。
 */

export interface AgentCitation {
  index: number;
  articleId: string | number;
  articleTitle: string;
  heading: string;
  score?: number;
}

export interface AgentChatPayload {
  message: string;
  history: { role: "user" | "assistant"; content: string }[];
}

/**
 * 咨询页 RAG 对话（SSE 流式）：
 * 服务端检索完成后先发 citations 事件（引用卡片数据），再逐段发 token，
 * 最后 done；任何异常以 error 事件结束——这里转成 throw 走调用方的错误处理。
 */
export const ragChatStream = async (
  payload: AgentChatPayload,
  callbacks: {
    onCitations: (citations: AgentCitation[]) => void;
    onDelta: (text: string) => void;
    onDone: () => void;
  },
  signal?: AbortSignal,
) => {
  const res = await fetch("/agent/rag/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`RAG服务接口异常：${res.status}`);
  }

  // 原生流式解析SSE（与 HealthButler.vue 同款）：buffer暂存半行，按\n切割逐条处理
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
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
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) {
        continue;
      }
      let data: Record<string, unknown> | null = null;
      try {
        data = JSON.parse(trimmed.slice(5).trim());
      } catch {
        // 不完整的JSON行：跳过，等buffer拼齐（不能把error事件的throw也吞了）
      }
      if (!data) {
        continue;
      }
      if (data.type === "citations") {
        callbacks.onCitations((data.citations as AgentCitation[]) ?? []);
      } else if (data.type === "token") {
        callbacks.onDelta(String(data.text ?? ""));
      } else if (data.type === "done") {
        callbacks.onDone();
        return;
      } else if (data.type === "error") {
        throw new Error(String(data.message ?? "RAG 对话出错"));
      }
    }
  }
  // 服务端没发done就关流：按正常结束处理
  callbacks.onDone();
};

/**
 * 情绪分析（非流式）：服务端已做过宽松JSON解析，
 * 返回 result=null 表示"本轮无结果"（空会话/解析失败/内部异常都不抛5xx）
 */
export const analyzeEmotionRemote = async (
  messages: { role: "user" | "assistant"; content: string }[],
): Promise<object | null> => {
  const res = await fetch("/agent/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    throw new Error(`情绪分析接口异常：${res.status}`);
  }
  const json = await res.json();
  return (json?.result as object | null) ?? null;
};
