/**
 * /agent → Render 上 agent-server（Python FastAPI，RAG/Agent 服务端）的生产转发。
 *
 * 与 llm.mjs 同一模式：函数内 config.path 声明路由（URLPattern 语法），
 * 入口文件平铺在 functions 目录，netlify.toml 不需要也不能再配 /agent 重定向。
 * 开发环境由 vite 的 /agent 代理转发到 localhost:8000，前端代码同一个 /agent 路径。
 *
 * 目标地址在站点环境变量 AGENT_URL（形如 https://ai-mental-agent.onrender.com，
 * 不带尾斜杠），密钥类配置（GLM_API_KEY 等）在 Render 侧，本函数只做转发。
 *
 * 转发的请求头白名单：content-type/accept 之外，透传三类身份头——
 *   token / authorization   健康管家按用户身份调课程后端
 *   x-admin-token           /kb/rebuild 管理令牌
 *
 * 防滥用护栏：Origin校验（同 llm.mjs：浏览器不可伪造，无Origin的客户端放行由
 * 服务端自身的鉴权兜底）+ 请求体上限。模型白名单不适用（转发的是自家服务，
 * 不是开放API），Render 侧出向调用 GLM 才带密钥。
 *
 * SSE 流式透传：响应体不解析直接返回，咨询页打字机与健康管家思考卡片
 * 的流式体验与本地一致。注意 Netlify 流式函数上限 60s——/rag/chat 回复
 * 5~15s 安全，/chat（ReAct 多轮工具）最坏贴近上限，超时表现为流提前结束。
 */

const ALLOWED_HEADERS = ["content-type", "accept", "token", "authorization", "x-admin-token"];
const MAX_BODY_BYTES = 256 * 1024;

const jsonError = (status, message) =>
  new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });

export default async (req) => {
  const upstreamBase = process.env.AGENT_URL;
  if (!upstreamBase) {
    return jsonError(500, "AGENT_URL 未配置：请在 Netlify 站点环境变量中设置（Render 服务地址，不带尾斜杠）");
  }

  //子路径：URLPattern命名捕获组 → 数组形态兼容 → 原始URL剥前缀兜底
  const raw = req.url.match(/^https?:\/\/[^/]+\/agent\/?(.*)/);
  const fromUrl = raw ? raw[1].replace(/\/+$/, "") : "";
  //context.params 在 v2 签名 (req, context) 里才有；这里从 URL 兜底解析已够用
  const sub = fromUrl;
  if (!sub) {
    return jsonError(400, "缺少子路径，预期 /agent/rag/chat、/agent/chat、/agent/analyze 等");
  }

  try {
    //Origin只在存在时校验：浏览器请求必带且不可伪造；非浏览器客户端由服务端鉴权兜底
    const origin = req.headers.get("origin");
    const ownOrigins = [process.env.URL, process.env.DEPLOY_PRIME_URL].filter(Boolean);
    if (origin && ownOrigins.length > 0 && !ownOrigins.includes(origin)) {
      return jsonError(403, "跨站调用被拒绝");
    }

    const hasBody = !["GET", "HEAD"].includes(req.method);
    let bodyText;
    if (hasBody) {
      bodyText = await req.text();
      if (bodyText.length > MAX_BODY_BYTES) {
        return jsonError(413, `请求体过大（上限 ${MAX_BODY_BYTES / 1024}KB）`);
      }
    }

    const headers = {};
    for (const name of ALLOWED_HEADERS) {
      const v = req.headers.get(name);
      if (v) headers[name] = v;
    }

    const { search } = new URL(req.url);
    const upstream = await fetch(`${upstreamBase}/${sub}${search}`, {
      method: req.method,
      headers,
      body: bodyText,
    });

    //状态码与content-type透传（json与text/event-stream都适用），流不落地
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") || "application/json",
        "cache-control": "no-cache",
      },
    });
  } catch (error) {
    return jsonError(502, `上游请求失败：${error?.message ?? error}`);
  }
};

export const config = { path: "/agent/:path*" };
