/**
 * 批量导入心理健康知识库文章（150 篇种子语料）
 *
 * 用法：
 *   1. 浏览器登录后台 → F12 → Application → Local Storage → 复制 token 字段的值
 *   2. node scripts/import-articles.mjs <token>
 *      或 ADMIN_TOKEN=<token> node scripts/import-articles.mjs
 *
 * 可选：
 *   API_BASE=http://...      覆盖后端地址（默认 http://159.75.169.224:1235/api）
 *   --dry-run                只检查分类和重复，不真正写入
 *
 * 行为：
 *   - 拉取后台已有分类树，缺失的分类会列出并中止（先去后台「知识文章分类」里建好再跑）
 *   - 按标题查重，已存在的自动跳过，脚本可安全重跑
 *   - 创建成功后自动发布（status=1，前台可见）
 *   - 单篇失败不会中断，结束后输出汇总
 */
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const API_BASE = process.env.API_BASE || "http://159.75.169.224:1235/api";
const TOKEN = process.argv[2] || process.env.ADMIN_TOKEN;
const DRY_RUN = process.argv.includes("--dry-run");

if (!TOKEN) {
  console.error("缺少 token：node scripts/import-articles.mjs <token>（后台登录后从 localStorage 复制）");
  process.exit(1);
}

//复刻 src/utils/request.ts 的请求约定：token 放请求头，响应体 { code, msg, data }
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      token: TOKEN,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({ code: res.status, msg: "响应不是 JSON" }));
  //后端 code 可能是字符串 "200" 或数字 200（原项目 request.ts 也是用 == 宽松比较）
  if (Number(json.code) !== 200) {
    throw new Error(`${method} ${path} → code=${json.code} msg=${json.msg ?? JSON.stringify(json)}`);
  }
  return json.data;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

//读取 seed-articles 下全部语料文件（按文件名序号排序，新增批次文件零改动接入）
const dir = dirname(fileURLToPath(import.meta.url));
const files = readdirSync(join(dir, "seed-articles"))
  .filter((f) => /^articles-\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));
const articles = files.flatMap((f) =>
  JSON.parse(readFileSync(join(dir, "seed-articles", f), "utf-8"))
);

//语料分类 → 后台已有分类的映射（后台分类固定 4 个，无创建接口）
//睡眠/成长/科普/学业属于基础心理知识，归入「心理健康基础」；
//情感/家庭本质是人际关系议题；职场心理归入「压力缓解」
const CATEGORY_MAP = {
  "情绪管理": "情绪管理",
  "压力应对": "压力缓解",
  "人际沟通": "人际关系",
  "睡眠健康": "心理健康基础",
  "自我成长": "心理健康基础",
  "心理科普": "心理健康基础",
  "职场心理": "压力缓解",
  "情感关系": "人际关系",
  "家庭关系": "人际关系",
  "学业成长": "心理健康基础",
};

async function main() {
  console.log(`共 ${articles.length} 篇文章待导入 → ${API_BASE}${DRY_RUN ? "（dry-run 演练）" : ""}\n`);

  //1. 分类校验：映射后必须都能在后台找到
  const tree = await api("/knowledge/category/tree");
  const categoryIdByName = new Map(tree.map((c) => [c.categoryName, c.id]));
  articles.forEach((a) => (a.category = CATEGORY_MAP[a.category] || a.category));
  const mapped = [...new Set(articles.map((a) => a.category))];
  const missing = mapped.filter((c) => !categoryIdByName.has(c));
  if (missing.length) {
    console.error("以下分类在后台不存在，请先到后台创建后再运行：");
    missing.forEach((c) => console.error(`  - ${c}`));
    console.error(`\n后台已有分类：${[...categoryIdByName.keys()].join("、")}`);
    process.exitCode = 1; //不用 process.exit：Windows 上连接未关闭时强退会触发 libuv 断言崩溃
    return;
  }
  console.log(`分类映射完成，实际写入分类：${mapped.join("、")}`);

  //2. 标题查重（分页拉全量），保证脚本可重跑
  const existed = new Set();
  for (let page = 1; ; page++) {
    const data = await api(`/knowledge/article/page?currentPage=${page}&size=100`);
    (data.records || []).forEach((r) => existed.add(r.title));
    if (page * 100 >= (data.total || 0)) break;
  }
  console.log(`后台已有文章 ${existed.size} 篇，重名将自动跳过\n`);

  //3. 逐篇创建 + 发布
  let ok = 0, skipped = 0, failed = 0;
  for (const a of articles) {
    if (existed.has(a.title)) {
      console.log(`跳过（已存在）：${a.title}`);
      skipped++;
      continue;
    }
    if (DRY_RUN) {
      console.log(`[dry-run] 将导入：${a.title}（${a.category}）`);
      ok++;
      continue;
    }
    const id = crypto.randomUUID();
    try {
      //payload 字段与后台 ArticleDialog.vue 提交结构一致；tags 是逗号拼接字符串
      await api("/knowledge/article", {
        method: "POST",
        body: {
          id,
          title: a.title,
          content: a.content,
          coverImage: "",
          categoryId: categoryIdByName.get(a.category),
          summary: a.summary,
          tags: a.tags.join(","),
        },
      });
      await api(`/knowledge/article/${id}/status`, { method: "PUT", body: { status: 1 } });
      console.log(`✅ 已发布：${a.title}（${a.category}）`);
      ok++;
    } catch (e) {
      console.error(`❌ 失败：${a.title}\n   ${e.message}`);
      failed++;
    }
    await sleep(300); //轻限流，避免把测试服务器打爆
  }

  console.log(`\n汇总：成功 ${ok} / 跳过 ${skipped} / 失败 ${failed}（共 ${articles.length}）`);
  if (!DRY_RUN && ok > 0) console.log("到后台「知识文章管理」或前台知识库页面确认内容显示正常。");
}

main().catch((e) => {
  console.error(`\n运行中止：${e.message}`);
  process.exitCode = 1;
});
