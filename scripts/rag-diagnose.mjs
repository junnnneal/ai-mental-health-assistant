// RAG语料诊断：复刻浏览器端 fetchAllArticles + chunkArticle 的取数路径，
// 打印列表 total/条数 与 每篇文章详情正文的可分块性，定位"8篇→0块"的根因
const BASE = "http://159.75.169.224:1235/api";
const TOKEN = process.argv[2];

if (!TOKEN) {
  console.error("用法: node scripts/rag-diagnose.mjs <token>");
  process.exit(1);
}

const headers = { token: TOKEN };

const listRes = await fetch(
  `${BASE}/knowledge/article/page?currentPage=1&size=50&sortField=readCount&sortDirection=desc`,
  { headers },
);
console.log(`列表接口 HTTP ${listRes.status}`);
const listJson = await listRes.json().catch(() => null);
if (!listJson) {
  console.error("列表响应不是JSON，结束");
  process.exit(1);
}
const data = listJson.data ?? {};
const records = data.records ?? [];
console.log(`code=${listJson.code} total=${data.total} 本页返回=${records.length} 篇`);
console.log(`字段样例: ${JSON.stringify(Object.keys(records[0] ?? {}))}`);

let emptyContent = 0;
for (const a of records) {
  const detRes = await fetch(`${BASE}/knowledge/article/${a.id}`, { headers });
  const detJson = await detRes.json().catch(() => null);
  const content = detJson?.data?.content ?? "";
  const chunks = content
    .split(/(?=<h3>)/)
    .map((s) => s.replace(/<[^>]+>/g, "").trim())
    .filter((t) => t.length >= 20).length;
  if (!content.trim()) emptyContent++;
  console.log(
    `《${a.title}》HTTP${detRes.status} content=${content.length}字 可分块=${chunks} 含h3=${content.includes("<h3>")}`,
  );
}
console.log(`\n小结：${records.length}篇中正文为空 ${emptyContent} 篇`);
