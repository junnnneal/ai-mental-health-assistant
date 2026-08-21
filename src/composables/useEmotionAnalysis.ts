import { chatCompletion } from "@/apis/llm";

/**
 * 本地情绪分析：对话走GLM直连后，消息不再经过课程后端，
 * 后端的会话情绪分析没有语料可用（它只存了session/start的首条消息）。
 * 这里用非流式GLM对最近对话产出结构化JSON，字段与后端emotion接口对齐，
 * 直接喂给 Consultation.vue 的 normalizeEmotionGarden 归一化。
 */

const SYSTEM_PROMPT = [
  "你是心理咨询师的情绪分析助手。分析用户与AI助手的对话，判断用户当前的情绪状态。",
  "只输出一个JSON对象，不要输出任何其他文字、解释或markdown代码块，字段如下：",
  "{",
  '  "primaryEmotion": "主要情绪，一到两个词，如：焦虑、低落、平静、开心",',
  '  "emotionScore": 0到100的整数，表示情绪强度（越强烈越高，与正面负面无关）,',
  '  "isNegative": true或false，是否为负面情绪,',
  '  "riskLevel": "low、medium、high三选一，用户心理风险等级",',
  '  "summary": "一句话概括用户当前的情绪状态",',
  '  "suggestion": "一句温和、可操作的情绪调节建议",',
  '  "actionItems": ["三条可以立刻执行的缓解行动，每条不超过15字"]',
  "}",
].join("\n");

//模型偶尔会裹```json代码块或前后加说明文字：取第一个{到最后一个}之间兜底解析
const parseJsonLoose = (raw: string): object | null => {
  const text = raw.replace(/```(?:json)?/g, "").trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end <= start) {
    return null;
  }
  try {
    return JSON.parse(text.slice(start, end + 1));
  } catch {
    return null;
  }
};

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
  //每条截断到500字：分析看的是情绪倾向，不需要全文，控制token与耗时
  const transcript = messages
    .map(
      (m) => `${m.role === "user" ? "用户" : "AI"}：${m.content.slice(0, 500)}`,
    )
    .join("\n");
  //低温采样：要的是稳定的结构化输出，不要发散
  const raw = await chatCompletion(
    [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: `对话记录：\n${transcript}` },
    ],
    { temperature: 0.2 },
  );
  return parseJsonLoose(raw);
};
