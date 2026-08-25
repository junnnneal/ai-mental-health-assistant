/**
 * 种子语料校验：格式、查重、块数统计。
 * 用法：node scripts/verify-seed-corpus.mjs
 * 可在任何时候重跑——改了语料之后跑一遍，防止带病入库（坏JSON/重复标题会让检索质量悄悄劣化）。
 */
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const CATEGORIES = new Set([
  "情绪管理", "睡眠健康", "压力应对", "人际沟通", "自我成长", "心理科普",
  "职场心理", "情感关系", "家庭关系", "学业成长",
]);

const dir = join(dirname(fileURLToPath(import.meta.url)), "seed-articles");
const files = readdirSync(dir)
  .filter((f) => /^articles-\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));

const errors = [];
const warnings = [];
const titles = new Map(); // title -> file
const byCategory = {};
let total = 0;
let totalChunks = 0;

const stripTags = (html) => html.replace(/<[^>]+>/g, "");

for (const file of files) {
  let items;
  try {
    items = JSON.parse(readFileSync(join(dir, file), "utf-8"));
  } catch (e) {
    errors.push(`${file}：JSON 解析失败 → ${e.message}`);
    continue;
  }
  if (!Array.isArray(items) || items.length === 0) {
    errors.push(`${file}：不是非空数组`);
    continue;
  }
  for (let i = 0; i < items.length; i++) {
    const a = items[i];
    const where = `${file}[${i}]「${a.title ?? "?"}」`;

    for (const field of ["title", "category", "summary", "content"]) {
      if (typeof a[field] !== "string" || !a[field].trim()) {
        errors.push(`${where}：字段 ${field} 缺失或为空`);
      }
    }
    if (!Array.isArray(a.tags) || a.tags.length !== 3 || a.tags.some((t) => typeof t !== "string")) {
      errors.push(`${where}：tags 必须是 3 个字符串`);
    }
    if (a.category && !CATEGORIES.has(a.category)) {
      errors.push(`${where}：未知类目「${a.category}」`);
    }

    if (typeof a.title === "string") {
      if (titles.has(a.title)) {
        errors.push(`重复标题：「${a.title}」（${titles.get(a.title)} 与 ${file}）`);
      } else {
        titles.set(a.title, file);
      }
    }

    if (typeof a.content === "string") {
      if (a.content.includes("\n")) {
        errors.push(`${where}：content 含换行（必须单行）`);
      }
      const h3Count = (a.content.match(/<h3>/g) || []).length;
      if (h3Count < 3 || h3Count > 5) {
        errors.push(`${where}：h3 小节数 ${h3Count}，超出 3~5`);
      }
      // 小节结构：<h3>后必须紧跟<p>（切片依赖这个结构）
      const badStructure = a.content.match(/<\/h3>(?!<p>)/);
      if (badStructure) {
        errors.push(`${where}：存在 h3 后未紧跟 p 的结构`);
      }
      const textLen = stripTags(a.content).length;
      if (textLen < 500 || textLen > 1100) {
        warnings.push(`${where}：正文 ${textLen} 字（期望 600~1000 附近）`);
      }
      // 残留小节丢切阈值以下的段落（<20字的p会被_chunk_article丢弃，等于空块）
      const shortPs = (a.content.match(/<p>[^<]{0,19}<\/p>/g) || []).length;
      if (shortPs > 0) {
        warnings.push(`${where}：${shortPs} 个段落不足 20 字，入库时会被丢弃`);
      }
      //"来源："单独太容易误伤正文（如"焦虑的来源：……"），只查引用式表述
      if (/https?:\/\/|本文来自|原文链接|资料来源|文章来源|（来源[:：]/.test(a.content)) {
        errors.push(`${where}：content 疑似残留来源痕迹/链接`);
      }
      totalChunks += h3Count;
    }

    byCategory[a.category] = (byCategory[a.category] ?? 0) + 1;
    total++;
  }
}

console.log(`文件 ${files.length} 个，文章 ${total} 篇，预计入库块数 ~${totalChunks}\n`);
console.log("分类分布：");
for (const [c, n] of Object.entries(byCategory).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${c}：${n} 篇`);
}

if (warnings.length) {
  console.log(`\n警告 ${warnings.length} 条（不阻断）：`);
  warnings.forEach((w) => console.log(`  ⚠ ${w}`));
}
if (errors.length) {
  console.error(`\n错误 ${errors.length} 条（必须修复）：`);
  errors.forEach((e) => console.error(`  ✗ ${e}`));
  process.exitCode = 1;
} else {
  console.log("\n✅ 全部通过");
}
