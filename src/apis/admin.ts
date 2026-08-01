import request from "@/utils/request";
import type { LoginResult } from "@/types";

//登录接口
export const login = (data: { username: string; password: string }) => {
  return request<LoginResult>({
    url: "/user/login",
    method: "post",
    data,
  });
};

//知识文章分类树
export const categoryTree = () => {
  return request<any>({
    url: "/knowledge/category/tree",
    method: "get",
  });
};

//知识文章列表
export const articlePage = (data: any) => {
  return request<any>({
    url: "/knowledge/article/page",
    method: "get",
    params: data,
  });
};

//上传文件接口
export const uploadFile = (file: File, businessInfo: { id: string }) => {
  const formData = new FormData();
  //往formData中添加文件和业务信息参数
  formData.append("file", file);
  formData.append("businessType", "ARTICLE");
  formData.append("businessId", businessInfo.id);
  formData.append("businessField", "cover");

  return request<any>({
    // 上传文件时，需要设置请求头Content-Type为multipart/form-data
    headers: {
      "Content-Type": "multipart/form-data",
    },
    url: "/file/upload",
    method: "post",
    data: formData,
  });
};

//新增文章接口
export const createArticle = (data: any) => {
  return request<any>({
    url: "/knowledge/article",
    method: "post",
    data,
  });
};

//获取详情接口
export const getArticleDetail = (id: string) => {
  return request<any>({
    url: `/knowledge/article/${id}`,
    method: "get",
  });
};

//更新文章接口
export const updateArticle = (id: string, data: any) => {
  return request<any>({
    url: `/knowledge/article/${id}`,
    method: "put",
    data,
  });
};

//发布文章接口
export const publishArticle = (id: string, data: any) => {
  return request<any>({
    url: `/knowledge/article/${id}/status`,
    method: "put",
    data,
  });
};

//删除文章接口
export const deleteArticle = (id: string) => {
  return request<any>({
    url: `/knowledge/article/${id}`,
    method: "delete",
  });
};

//咨询记录列表
export const consultationPage = (data: any) => {
  return request<any>({
    url: "/psychological-chat/sessions",
    method: "get",
    params: data,
  });
};

//获取会话消息列表
export const sessionMessages = (id: string) => {
  return request<any>({
    url: `/psychological-chat/sessions/${id}/messages`,
    method: "get",
  });
};

//情绪日志列表
export const moodLogPage = (data: any) => {
  return request<any>({
    url: "/emotion-diary/admin/page",
    method: "get",
    params: data,
  });
};

//删除情绪日志接口
export const deleteMoodLog = (id: string) => {
  return request<any>({
    url: `/emotion-diary/admin/${id}`,
    method: "delete",
  });
};

//获取综合数据分析
export const getDashboardData = () => {
  return request<any>({
    url: "/data-analytics/overview",
    method: "get",
  });
};

//退出登录接口
export const logout = () => {
  return request<any>({
    url: "/user/logout",
    method: "post",
  });
};
