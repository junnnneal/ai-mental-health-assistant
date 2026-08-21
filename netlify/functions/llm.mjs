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
 * SSE 流式透传：响应体（ReadableStream）不解析直接返回，流式回复不被缓冲，
 * 打字机体验与开发环境直连一致。
 */

const UPSTREAM = "https://open.bigmodel.cn";

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

  try {
    //请求体一次性读出再转发（本场景是小块JSON，不需要流式上行）
    const hasBody = !["GET", "HEAD"].includes(req.method);
    const { search } = new URL(req.url);
    const upstream = await fetch(`${UPSTREAM}/${sub}${search}`, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": req.headers.get("content-type") || "application/json",
        Accept: req.headers.get("accept") || "application/json",
      },
      body: hasBody ? await req.text() : undefined,
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
