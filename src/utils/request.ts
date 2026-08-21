import axios, { type AxiosRequestConfig } from "axios";
import router from "@/router";
import { ElMessage } from "element-plus";

const instance = axios.create({
  baseURL: "/api",
  timeout: 5000,
});

//请求拦截器
instance.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers["token"] = token;
  }
  return config;
});

//响应拦截器
instance.interceptors.response.use(
  (response) => {
    const { data, config } = response;
    if (data.code == 200) {
      return data.data;
    }
    if (data.code == -1) {
      if (!config.url?.includes("/login")) {
        ElMessage.error(data.msg || "登录过期，请重新登录");
        localStorage.removeItem("token");
        localStorage.removeItem("userInfo");
        router.push("/auth/login");
      }
      return Promise.reject(data.msg || "登录过期");
    }
    ElMessage.error(data.msg || "网络请求失败...");
    return Promise.reject(data.msg || "网络请求失败...");
  },
  (error) => {
    //HTTP层错误（403空响应/超时/断网）也要给用户可见反馈，
    //否则后端挂掉时页面毫无感知（业务code错误上面已处理）
    const status = error.response?.status;
    if (status === 401 || status === 403) {
      //注意：不清token不跳登录——403可能是后端鉴权服务异常而非登录过期，静默降级等恢复
      ElMessage.error("服务暂不可用或无权限（" + status + "），请稍后重试");
    } else if (error.code === "ECONNABORTED" || error.message?.includes("timeout")) {
      ElMessage.error("请求超时，请稍后重试");
    } else {
      ElMessage.error("网络异常，请检查网络后重试");
    }
    return Promise.reject(error);
  },
);

/** 泛型请求函数，拦截器已解包 data.data，直接返回业务数据 */
const request = <T = any>(config: AxiosRequestConfig): Promise<T> => {
  return instance(config) as Promise<T>;
};

export default request;
