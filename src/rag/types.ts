/**
 * RAG知识块：一篇文章按<h3>小节切出的最小可检索单元
 */
export interface KnowledgeChunk {
  //块唯一标识：文章id_小节序号
  id: string;
  articleId: number | string;
  articleTitle: string;
  category: string;
  //小节标题（<h3>文本）
  heading: string;
  //纯文本内容（标签已剥离）
  text: string;
  //参与向量化的文本：带"分类+文章标题+小节名"上下文前缀，检索更准
  embedText: string;
  //向量（IndexedDB缓存命中时存在）
  embedding?: number[];
}

/**
 * 检索结果：命中的知识块 + 余弦相似度得分
 */
export interface RetrievedChunk extends KnowledgeChunk {
  score: number;
}
