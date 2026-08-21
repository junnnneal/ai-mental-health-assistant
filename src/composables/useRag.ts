import { ref } from "vue";
import { ensureVectorStore, retrieve } from "@/rag/retriever";
import type { RetrievedChunk } from "@/rag/types";

/**
 * RAG检索的组件态封装
 * 检索失败静默降级为空结果（对话照常进行，只是没有引用），不打断用户体验
 */
export const useRag = () => {
  const isRetrieving = ref(false);
  const ragError = ref("");

  const search = async (query: string, topK = 3): Promise<RetrievedChunk[]> => {
    if (!query.trim()) {
      return [];
    }
    isRetrieving.value = true;
    ragError.value = "";
    try {
      return await retrieve(query, topK);
    } catch (error) {
      //降级：知识库/向量接口不可用时，退回无引用的纯LLM回答
      ragError.value = "知识库检索不可用";
      console.warn("[RAG] 检索失败，本次对话降级为无引用模式", error);
      return [];
    } finally {
      isRetrieving.value = false;
    }
  };

  //预热：进页面就后台建/读向量库，把首次建库的冷启动藏进用户浏览的时间里
  const warmup = () => {
    ensureVectorStore().catch((error) => {
      console.warn("[RAG] 预热失败，首次检索时会再试一次", error);
    });
  };

  return { isRetrieving, ragError, search, warmup };
};
