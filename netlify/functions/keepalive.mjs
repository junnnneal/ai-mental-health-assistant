/**
 * 定时保活：每 15 分钟（分钟位 7/22/37/52 错峰）ping Render /health，防 15 分钟休眠。
 *
 * 为什么加这一层：GitHub Actions 的 cron 高峰期会排队延迟十几分钟，每 13 分钟一拍
 * 的节拍撞上延迟就留出超过 15 分钟的空窗（线上真睡过一次）；Actions 和 Netlify
 * 是两个故障不相关的调度器，双平台错峰后单平台延迟不再能造成休眠。UptimeRobot
 * 免费档自身可靠性不足（会漏 ping），已从保活链里弃用。
 *
 * schedule 平台限制最小间隔 15 分钟，正好卡在休眠线上，所以它的角色是兜底补洞，
 * 主保活是 Actions 的每 5 分钟一拍（仓库 public，分钟数不限）。
 *
 * 目标地址复用 AGENT_URL 站点环境变量（同 agent.mjs，不带尾斜杠）。
 * 函数自身永远 200：保活 ping 失败（如 Render 正在冷启动）不该报函数错误，只打日志。
 * 超时 9s：同步函数上限 10s，留余量；即便 fetch 中途放弃，连接到达 Render 已触发唤醒。
 */

const PING_TIMEOUT_MS = 9000;

export const handler = async () => {
  const base = process.env.AGENT_URL;
  if (!base) {
    console.log("[keepalive] 未配置 AGENT_URL，跳过");
    return { statusCode: 200 };
  }
  let status = "error";
  try {
    const r = await fetch(`${base.replace(/\/+$/, "")}/health`, {
      signal: AbortSignal.timeout(PING_TIMEOUT_MS),
    });
    status = String(r.status);
  } catch (e) {
    console.log(`[keepalive] ping 失败（可能正在冷启动）：${e?.message || e}`);
  }
  console.log(`[keepalive] ${base}/health -> ${status}`);
  return { statusCode: 200 };
};

export const config = {
  schedule: "7,22,37,52 * * * *", // 分钟位与时区无关（UTC 只影响小时）
};
