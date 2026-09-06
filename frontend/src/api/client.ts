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

function redirectToLogin() {
  // 按当前所在端选择登录页，并带上回跳地址
  const onAdmin = window.location.pathname.startsWith("/admin")
    || window.location.pathname.startsWith("/owner");
  const loginPath = onAdmin ? "/admin/login" : "/teacher/login";
  const redirect = encodeURIComponent(
    window.location.pathname + window.location.search
  );
  window.location.href = `${loginPath}?redirect=${redirect}`;
}

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;

    if (status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      localStorage.removeItem("teacher");
      localStorage.removeItem("tenant");
      showToast("登录已过期，请重新登录");
      const onLoginPage = window.location.pathname.endsWith("/login");
      if (!onLoginPage) {
        redirectToLogin();
      }
    } else if (status === 403) {
      showToast(detail || "权限不足");
    } else if (status === 409) {
      showToast(detail || "操作冲突");
    } else if (status === 422) {
      showToast(detail || "请检查输入数据");
    } else if (error.response) {
      if (status && status >= 500) {
        showToast("服务器错误，请稍后重试");
      }
    } else {
      // 无 response：断网 / 超时
      showToast("网络异常，请检查网络后重试");
    }

    return Promise.reject(error);
  }
);

export default client;
