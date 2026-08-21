/**
 * AI咨询首字响应基准测试：直连智谱GLM，测流式首token延迟（TTFT）与embedding耗时。
 *
 * 用法：node scripts/bench-first-token.mjs [轮数，默认5]
 * 密钥从 .env.local 的 GLM_API_KEY 读取（仅Node侧使用，不进前端产物）。
 *
 * 页面里的 console 埋点测的是"用户视角首字"（含RAG检索+vite代理），
 * 本脚本测的是"模型裸TTFT"（隔离变量，可反复跑取分位数）——两者对照着看。
 */
import { readFileSync } from "node:fs";

const ROUNDS = Number(process.argv[2]) || 5;
//LLM_BASE=http://localhost:5173/llm/api/paas/v4 可走vite代理对比代理层开销
const BASE = process.env.LLM_BASE ?? "https://open.bigmodel.cn/api/paas/v4";

const env = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
const key = env.match(/^GLM_API_KEY=(.+)$/m)?.[1]?.trim();
if (!key) {
  console.error("请在 .env.local 配置 GLM_API_KEY");
  process.exitCode = 1;
}

const auth = { Authorization: `Bearer ${key}`, "Content-Type": "application/json" };

const stats = (arr) => {
  const s = [...arr].sort((a, b) => a - b);
  const sum = s.reduce((x, y) => x + y, 0);
  return {
    min: s[0],
    p50: s[Math.floor(s.length / 2)],
    max: s[s.length - 1],
    avg: Math.round(sum / s.length),
  };
};

const fmt = (label, st, unit = "ms") =>
  `${label}: min ${st.min}${unit} | p50 ${st.p50}${unit} | avg ${st.avg}${unit} | max ${st.max}${unit}`;

// —— 对话流式：请求发出 → 首个SSE delta 解析出来，即首token ——
const benchChat = async () => {
  const ttfbs = [];
  const totals = [];
  let chars = 0;
  for (let i = 0; i < ROUNDS; i++) {
    const t0 = performance.now();
    const res = await fetch(`${BASE}/chat/completions`, {
      method: "POST",
      headers: auth,
      body: JSON.stringify({
        model: "glm-4-flash",
        stream: true,
        messages: [
          { role: "system", content: "你是一个温暖的心理陪伴助手，回答控制在100字内。" },
          { role: "user", content: "最近工作压力很大，有点睡不着，怎么办？" },
        ],
      }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    //与前端 llm.ts 同款SSE解析：buffer暂存半行，按\n切割
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let firstToken = 0;
    let text = "";
    let done = false;
    while (!done) {
      const { value, done: rdDone } = await reader.read();
      if (rdDone) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const payload = trimmed.slice(5).trim();
        if (payload === "[DONE]") {
          done = true;
          break;
        }
        try {
          const delta = JSON.parse(payload)?.choices?.[0]?.delta?.content ?? "";
          if (delta) {
            if (!firstToken) firstToken = performance.now();
            text += delta;
          }
        } catch {
          //半包JSON下一轮拼接
        }
      }
    }
    const total = performance.now() - t0;
    ttfbs.push(Math.round(firstToken - t0));
    totals.push(Math.round(total));
    chars = text.length;
    console.log(`  第${i + 1}轮：首token ${ttfbs.at(-1)}ms，全文 ${Math.round(total)}ms，${text.length}字`);
  }
  console.log(`\n${fmt("对话首token(TTFT)", stats(ttfbs))}`);
  console.log(fmt("对话全文", stats(totals)));
  console.log(`  （末轮全文 ${chars} 字，折算出字速率 ≈ ${Math.round((chars * 1000) / totals.at(-1))} 字/s）\n`);
};

// —— 向量化：RAG检索里除了本地余弦计算外唯一的一次网络调用 ——
const benchEmbedding = async () => {
  const times = [];
  for (let i = 0; i < ROUNDS; i++) {
    const t0 = performance.now();
    const res = await fetch(`${BASE}/embeddings`, {
      method: "POST",
      headers: auth,
      body: JSON.stringify({ model: "embedding-2", input: ["最近工作压力很大，有点睡不着"] }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await res.json();
    times.push(Math.round(performance.now() - t0));
    console.log(`  第${i + 1}轮：embedding ${times.at(-1)}ms`);
  }
  console.log(`\n${fmt("embedding查询向量化(RAG前置)", stats(times))}\n`);
};

console.log(`=== GLM-4-Flash 首字响应基准（${ROUNDS}轮）===\n`);
console.log("① 对话流式：");
await benchChat();
console.log("② embedding（RAG检索的网络开销）：");
await benchEmbedding();
