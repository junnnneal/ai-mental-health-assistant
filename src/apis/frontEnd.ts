import request from "@/utils/request";
import type { EmotionDiaryPayload, KnowledgeArticlePageParams } from "@/types";

//注册接口
export const register = (data: {
  username: string;
  email: string;
  nickname: string;
  phone: string;
  password: string;
  confirmPassword: string;
  gender: number;
  userType: number;
}) => {
  return request<unknown>({
    url: "/user/add",
    method: "post",
    data,
  });
};

//创建新的会话
export const startSession = (data: {
  initialMessage: string;
  sessionTitle: string;
}) => {
  return request<any>({
    url: "/psychological-chat/session/start",
    method: "post",
    data,
  });
};

//历史消息
export const getSessionMessages = (params: any) => {
  return request<any>({
    url: "/psychological-chat/sessions",
    method: "get",
    params,
  });
};

//删除会话
export const deleteSession = (sessionId: any) => {
  return request<any>({
    url: `/psychological-chat/sessions/${sessionId}`,
    method: "delete",
  });
};

//获取历史会话列表
export const getSessionList = (sessionId: any) => {
  return request<any>({
    url: `/psychological-chat/sessions/${sessionId}/messages`,
    method: "get",
  });
};

//获取会话情绪分析结果
export const getSessionEmotion = (sessionId: string | number) => {
  return request<any>({
    url: `/psychological-chat/session/${sessionId}/emotion`,
    method: "get",
  });
};

//创建或更新情绪日记
export const createOrUpdateEmotionDiary = (data: EmotionDiaryPayload) => {
  return request<any>({
    url: "/emotion-diary",
    method: "post",
    data,
  });
};

//查询知识文章列表
export const getKnowledgeArticlePage = (
  params: KnowledgeArticlePageParams,
) => {
  return request<any>({
    url: "/knowledge/article/page",
    method: "get",
    params,
  });
};

//获取知识文章详情
export const getKnowledgeArticleDetail = (id: string | number) => {
  return request<any>({
    url: `/knowledge/article/${id}`,
    method: "get",
  });
};
