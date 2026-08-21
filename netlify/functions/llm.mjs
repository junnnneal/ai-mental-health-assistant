/**
 * /llm → 智谱GLM 的生产环境代理（Netlify Function v2）
 *
 * 开发环境由 vite.config.ts 的 /llm 代理注入密钥；生产环境没有 vite，
 * 由这个函数承担同样职责：注入 Authorization、原样转发。
 * 密钥配在 Netlify 站点环境变量 GLM_API_KEY，只存在服务端，不进前端 bundle。
 *
 * 路由用函数内 config.path 声明（URLPattern 语法，:path* 跨段捕获）：
 * /llm/api/paas/v4/chat/completions → context.params.path = "api/paas/v4/chat/completions"
 * 注意：入口文件必须平铺在 functions 目录（或叫 index.mjs/与目录同名），
 * 子目录里叫别的名字（如曾经的 [[path]].mjs）会被打包器无视，函数压根不部署。
 * 设了自定义 path 后函数只在 /llm/* 可用，netlify.toml 里不能再配 /llm 重定向。
 *
 * 防滥用护栏（接口公网可达，密钥能调智谱全系模型，必须挡住付费模型盗刷）：
 * 1) 模型白名单——真防线：本站只用两个固定模型，白名单外的（含付费模型）一律403
 * 2) Origin校验——浏览器禁止网页伪造Origin头，挡住其他网站的网页级盗刷；
 *    无Origin的非浏览器客户端（curl/脚本）交由白名单兜底
 * 3) 体积与输出上限：超大请求体拒绝，max_tokens超限钳制，防超长prompt与无限生成
 *
 * SSE 流式透传：响应体（ReadableStream）不解析直接返回，流式回复不被缓冲，
 * 打字机体验与开发环境直连一致。
 */

const UPSTREAM = "https://open.bigmodel.cn";

const ALLOWED_MODELS = new Set(["glm-4-flash-250414", "embedding-2"]);
const ALLOWED_PREFIX = "api/paas/v4/";
const MAX_BODY_BYTES = 256 * 1024;
const MAX_OUTPUT_TOKENS = 2048;

const jsonError = (status, message) =>
  new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });

export default async (req, context) => {
  const apiKey = process.env.GLM_API_KEY;
  if (!apiKey) {
    return jsonError(500, "GLM_API_KEY 未配置：请在 Netlify 站点环境变量中设置");
  }

  //子路径优先取 URLPattern 命名捕获组；兼容数组形态（重定向 :splat 传参）；
  //都没有时兜底从原始请求 URL 剥 /llm 前缀解析，三种来源保证取到子路径
  const raw = context?.params?.path;
  const fromParams = Array.isArray(raw)
    ? raw.filter(Boolean).join("/")
    : typeof raw === "string"
      ? raw
      : "";
  const sub =
    fromParams ||
    new URL(req.url).pathname.replace(/^\/llm\/?/, "").replace(/\/+$/, "");
  if (!sub) {
    return jsonError(400, "缺少子路径，预期 /llm/api/paas/v4/*");
  }
  //子路径收窄到智谱官方API前缀，防止代理被当任意URL跳板
  if (!sub.startsWith(ALLOWED_PREFIX)) {
    return jsonError(400, `不支持的子路径，仅允许 /${ALLOWED_PREFIX}*`);
  }

  try {
    //Origin只在存在时校验：浏览器POST必带且不可伪造；缺失视为非浏览器客户端，白名单兜底
    const origin = req.headers.get("origin");
    const ownOrigins = [process.env.URL, process.env.DEPLOY_PRIME_URL].filter(Boolean);
    if (origin && ownOrigins.length > 0 && !ownOrigins.includes(origin)) {
      return jsonError(403, "跨站调用被拒绝");
    }

    //请求体一次性读出再转发（本场景是小块JSON，不需要流式上行），
    //读出后顺便做护栏校验：大小 → JSON合法性 → 模型白名单 → max_tokens钳制
    const hasBody = !["GET", "HEAD"].includes(req.method);
    let bodyText;
    if (hasBody) {
      bodyText = await req.text();
      if (bodyText.length > MAX_BODY_BYTES) {
        return jsonError(413, `请求体过大（上限 ${MAX_BODY_BYTES / 1024}KB）`);
      }
      let parsed;
      try {
        parsed = JSON.parse(bodyText);
      } catch {
        return jsonError(400, "请求体不是合法JSON");
      }
      if (!ALLOWED_MODELS.has(String(parsed.model ?? ""))) {
        return jsonError(
          403,
          `模型不在白名单，仅允许：${[...ALLOWED_MODELS].join(" / ")}`,
        );
      }
      if (
        typeof parsed.max_tokens === "number" &&
        parsed.max_tokens > MAX_OUTPUT_TOKENS
      ) {
        parsed.max_tokens = MAX_OUTPUT_TOKENS;
        bodyText = JSON.stringify(parsed);
      }
    }

    const { search } = new URL(req.url);
    const upstream = await fetch(`${UPSTREAM}/${sub}${search}`, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": req.headers.get("content-type") || "application/json",
        Accept: req.headers.get("accept") || "application/json",
      },
      body: bodyText,
    });

    //状态码与content-type透传（json与text/event-stream都适用），流不落地
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    return jsonError(502, `上游请求失败：${error?.message ?? error}`);
  }
};

export const config = { path: "/llm/:path*" };
