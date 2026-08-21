/**
 * /llm → 智谱GLM 的生产环境代理（Netlify Function v2）
 *
 * 开发环境由 vite.config.ts 的 /llm 代理注入密钥；生产环境没有 vite，
 * 由这个函数承担同样职责：注入 Authorization、原样转发。
 * 密钥配在 Netlify 站点环境变量 GLM_API_KEY，只存在服务端，不进前端 bundle。
 *
 * 路由：netlify.toml 把 /llm/* 重写到 /.netlify/functions/llm/:splat，
 * [[path]] 可选捕获段拿到剩余子路径（前端路径自带 /api/paas/v4 前缀）。
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

  //[[path]] 捕获 /llm 后的全部子路径，如 api/paas/v4/chat/completions
  const sub = (context?.params?.path ?? []).map(String).join("/");
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
