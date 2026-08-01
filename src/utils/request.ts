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
    return Promise.reject(error);
  },
);

/** 泛型请求函数，拦截器已解包 data.data，直接返回业务数据 */
const request = <T = any>(config: AxiosRequestConfig): Promise<T> => {
  return instance(config) as Promise<T>;
};

export default request;
