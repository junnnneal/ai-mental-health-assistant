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

/**
 * 生成后幻觉自检结果（verify 事件，token 流结束后、done 前到达）。
 * 服务端自检失败（超时/解析失败/无引用/回答过短）时整帧省略——
 * 收不到就是"本轮没有自检"，前端不渲染徽章即天然向后兼容。
 */
export interface AgentVerify {
  //pass 全有依据 / warn 有资料外建议 / fail 有与资料不符的声明（服务端重算）
  verdict: "pass" | "warn" | "fail";
  supported: number;
  beyond: number;
  //与资料不符的声明文本列表（重点列出问题项）
  unsupported: string[];
  claims: { text: string; status: "supported" | "beyond" | "unsupported" }[];
  //回答与引用块的最大余弦相似度（辅助信号，可能缺失）
  alignment?: number | null;
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
    /** verify 帧可选：服务端自检成功才会到，不传也不影响原有调用方 */
    onVerify?: (verify: AgentVerify) => void;
  },
  signal?: AbortSignal,
) => {
  //瞬态网关错误自动重试一次：Render 免费实例冷启动/OOM重启的窗口期，
  //Netlify 会回 502/504（或网络层直接失败）——等 3 秒实例缓过来再发基本就通。
  //只在"响应尚未开始"时重试：流中途断开不重发，避免回复内容重复；
  //4xx 等非瞬态状态码不重试，直接走调用方错误处理。
  const TRANSIENT_STATUS = new Set([502, 503, 504]);
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  let res: Response | undefined;
  let lastError = "";
  for (let attempt = 0; attempt < 2 && !res; attempt++) {
    if (attempt > 0) {
      await sleep(3000);
    }
    try {
      const r = await fetch("/agent/rag/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal,
      });
      if (r.ok && r.body) {
        res = r;
      } else {
        //错误信息带上响应体片段：agent.mjs 的 502 会写明是哪一跳失败，方便定位
        let detail = `HTTP ${r.status}`;
        try {
          const text = await r.text();
          if (text) {
            detail += `：${text.slice(0, 120)}`;
          }
        } catch {
          /* 响应体读不出就只报状态码 */
        }
        lastError = detail;
        if (!TRANSIENT_STATUS.has(r.status)) {
          break;
        }
      }
    } catch (e) {
      if (signal?.aborted) {
        throw e;
      }
      lastError = `网络错误：${(e as Error).message}`;
    }
  }
  if (!res || !res.body) {
    throw new Error(`RAG服务接口异常：${lastError || "无响应"}`);
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
      } else if (data.type === "verify") {
        //幻觉自检结果：必须在 done 分支之前处理（done 直接 return 断流）
        callbacks.onVerify?.(data as unknown as AgentVerify);
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
