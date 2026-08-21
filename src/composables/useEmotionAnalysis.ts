import { analyzeEmotionRemote } from "@/apis/agent";

/**
 * 情绪分析：对话走服务端RAG后，消息不在课程后端，后端会话分析没有语料。
 * 调 agent-server 的 /agent/analyze（非流式），服务端产出结构化JSON并已
 * 做过宽松解析，字段与后端emotion接口对齐，直接喂给 normalizeEmotionGarden。
 * system prompt、500字截断、兜底解析都在服务端 main.py（逐字迁移自本文件）。
 */

export interface EmotionAnalysisInput {
  role: "user" | "assistant";
  content: string;
}

export const analyzeEmotion = async (
  messages: EmotionAnalysisInput[],
): Promise<object | null> => {
  //没有用户发言无从分析（只有AI欢迎语的空会话等场景）
  if (!messages.some((m) => m.role === "user" && m.content.trim())) {
    return null;
  }
  return analyzeEmotionRemote(messages);
};
