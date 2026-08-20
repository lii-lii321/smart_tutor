import axios from "axios";
import { showToast } from "vant";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api/v1",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截器：自动注入 JWT
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;

    if (status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      showToast("登录已过期，请重新登录");
    } else if (status === 403) {
      showToast(detail || "权限不足");
    } else if (status === 404) {
      showToast(detail || "资源不存在");
    } else if (status === 409) {
      showToast(detail || "操作冲突");
    } else if (status === 422) {
      showToast(detail || "请检查输入数据");
    } else if (status && status >= 500) {
      showToast("服务器错误，请稍后重试");
    }

    return Promise.reject(error);
  }
);

export default client;
