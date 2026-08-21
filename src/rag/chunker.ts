import {
  getKnowledgeArticleDetail,
  getKnowledgeArticlePage,
} from "@/apis/frontEnd";
import type { KnowledgeChunk } from "./types";

/**
 * RAG语料分块器：拉取知识库全量文章，按<h3>小节切块
 * （文章正文自带<h3>小节结构，天然就是语义完整的分块边界）
 */

//分页拉取全量已发布文章
export const fetchAllArticles = async () => {
  const all: any[] = [];
  let page = 1;
  for (;;) {
    const res: any = await getKnowledgeArticlePage({
      sortField: "readCount",
      sortDirection: "desc",
      currentPage: page,
      size: 50,
    });
    const records = res?.records || [];
    all.push(...records);
    //累计条数达总量、或某页为空即止，防死循环
    //不能用"页码×size>=total"判断：后端若按自己的默认页大小返回短页，第一页后就会提前断流漏掉后面的文章
    if (records.length === 0 || all.length >= (res?.total ?? 0)) {
      break;
    }
    page++;
  }
  return all;
};

//单篇文章分块：split by <h3>，每块携带文章标题/分类上下文
export const chunkArticle = (article: any): KnowledgeChunk[] => {
  const html = String(article.content || "");
  if (!html.trim()) {
    return [];
  }
  //在前瞻断言处切割，保留<h3>在块内
  const sections = html
    .split(/(?=<h3>)/)
    .map((s) => s.trim())
    .filter(Boolean);

  return sections
    .map((section, i) => {
      const heading =
        (section.match(/<h3>(.*?)<\/h3>/) || [])[1] || article.title;
      //剥离HTML标签得到纯文本
      const text = section.replace(/<[^>]+>/g, "").trim();
      return {
        id: `${article.id}_${i}`,
        articleId: article.id,
        articleTitle: article.title,
        category: article.categoryName || "",
        heading,
        text,
        embedText: `【${article.categoryName || "心理知识"}】${article.title} - ${heading}\n${text}`,
      };
    })
    .filter((chunk) => chunk.text.length >= 20); //过滤太短的碎块
};

//逐篇拉详情并分块：列表接口不返回正文，正文只在详情里
//与拉列表拆开（retriever算指纹只需列表，命中缓存时不必逐篇拉详情）
export const chunkArticles = async (articles: any[]) => {
  const chunks: KnowledgeChunk[] = [];
  for (const item of articles) {
    try {
      const detail: any = await getKnowledgeArticleDetail(item.id);
      chunks.push(...chunkArticle({ ...item, ...detail }));
    } catch (error) {
      //单篇失败不阻断整体构建
      console.warn("文章分块失败", item.id, error);
    }
  }
  console.log(`[RAG] 语料构建完成：${articles.length} 篇文章 → ${chunks.length} 个知识块`);
  return chunks;
};
