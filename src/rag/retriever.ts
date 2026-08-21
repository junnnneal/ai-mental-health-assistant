import { embedding } from "@/apis/llm";
import { chunkArticles, fetchAllArticles } from "./chunker";
import type { KnowledgeChunk, RetrievedChunk } from "./types";
import { clearChunks, getAllChunks, getMeta, putChunks, setMeta } from "./vectorStore";

/**
 * RAG检索器：确保向量库就绪 → query向量化 → 与全部知识块算余弦相似度 → top-k
 */

//并发去重：构建过程单飞，多个调用共享同一个Promise
let building: Promise<KnowledgeChunk[]> | null = null;

//空语料冷却：知识库被清空/下架时，短时间内不重复重建，避免每条消息都白拉一遍文章详情
const EMPTY_RETRY_MS = 5 * 60 * 1000;
let emptyFp: string | null = null;
let emptyAt = 0;

//内存缓存：库就绪后TTL内直接复用，免去每条消息的"文章列表请求+IndexedDB全量读取"
//（这两步约占检索链路一半耗时；缓存后热路径只剩query向量化一次请求）
const MEM_TTL_MS = 5 * 60 * 1000;
let memChunks: KnowledgeChunk[] | null = null;
let memAt = 0;

//知识库版本指纹：文章集合（id+更新时间+标题）变了就重建缓存
const fingerprint = (articles: any[]) =>
  articles
    .map((a) => `${a.id}:${a.updatedAt ?? a.updateTime ?? ""}:${a.title}`)
    .join("|");

/**
 * 确保向量库就绪：
 * 1. 先只拉文章列表算指纹（1个请求）——命中缓存则零详情请求、零embedding请求
 * 2. 指纹变了才逐篇拉详情分块 → 分批向量化 → 落库
 * 3. 语料为空（文章被删/下架/正文为空）时不落缓存不写指纹，检索退化为无知识库对话，冷却期内不重试
 */
export const ensureVectorStore = async (): Promise<KnowledgeChunk[]> => {
  //内存缓存新鲜：直接复用（即便IndexedDB里有缓存，每条消息重读全量向量也不便宜）
  if (memChunks && Date.now() - memAt < MEM_TTL_MS) {
    return memChunks;
  }
  if (building) {
    return building;
  }
  building = (async () => {
    const articles = await fetchAllArticles();
    const fp = fingerprint(articles);

    const cachedFp = await getMeta("fingerprint");
    if (cachedFp === fp) {
      const cached = await getAllChunks();
      if (cached.length > 0) {
        console.log(`[RAG] 向量缓存命中：${cached.length} 块，跳过向量化`);
        memChunks = cached;
        memAt = Date.now();
        return cached;
      }
    }

    if (fp === emptyFp && Date.now() - emptyAt < EMPTY_RETRY_MS) {
      console.warn(`[RAG] 知识库为空，冷却中（${Math.ceil(EMPTY_RETRY_MS / 60000)}分钟内不重试），本次不带知识库上下文`);
      memChunks = [];
      memAt = Date.now();
      return [];
    }

    console.log(`[RAG] 向量缓存过期/不存在，开始重建`);
    const chunks = await chunkArticles(articles);
    if (chunks.length === 0) {
      emptyFp = fp;
      emptyAt = Date.now();
      console.warn(`[RAG] 知识库为空：${articles.length} 篇文章均无可切分正文，本次退化为无知识库对话`);
      memChunks = [];
      memAt = Date.now();
      return [];
    }

    await clearChunks();
    //embedding接口有批量上限，10条一批留余量
    const BATCH_SIZE = 10;
    for (let i = 0; i < chunks.length; i += BATCH_SIZE) {
      const batch = chunks.slice(i, i + BATCH_SIZE);
      const vectors = await embedding(batch.map((c) => c.embedText));
      batch.forEach((chunk, j) => {
        chunk.embedding = vectors[j];
      });
    }
    await putChunks(chunks);
    await setMeta("fingerprint", fp);
    memChunks = chunks;
    memAt = Date.now();
    console.log(`[RAG] 向量库重建完成并落库`);
    return chunks;
  })();

  try {
    return await building;
  } finally {
    //失败后允许下次重试
    building = null;
  }
};

//余弦相似度：向量夹角衡量语义接近程度
const cosineSimilarity = (a: number[], b: number[]) => {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    const av = a[i] ?? 0;
    const bv = b[i] ?? 0;
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) || 1);
};

/**
 * 检索入口：query → top-k 最相关的知识块
 * 150块×1024维的全量暴力计算在毫秒级，无需ANN索引
 */
export const retrieve = async (
  query: string,
  topK = 3,
): Promise<RetrievedChunk[]> => {
  if (!query.trim()) {
    return [];
  }
  const chunks = await ensureVectorStore();
  if (chunks.length === 0) {
    //知识库为空：跳过query向量化，直接按"无知识库上下文"处理
    return [];
  }
  const [queryVector] = await embedding([query]);
  if (!queryVector) {
    return [];
  }

  const top = chunks
    .filter((chunk) => chunk.embedding)
    .map((chunk) => ({
      ...chunk,
      score: cosineSimilarity(queryVector, chunk.embedding as number[]),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
  //检索必须有痕：否则"检索为空"和"上层把结果丢了"在控制台里无法区分（排查时两眼一抹黑）
  if (top.length) {
    console.log(
      `[RAG] 检索命中${top.length}块，最高分${top[0].score.toFixed(3)}《${top[0].articleTitle}》`,
    );
  }
  return top;
};
