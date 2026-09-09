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

// 响应拦截器：只处理会话失效（401）。
// 业务错误（400/403/409/422/5xx）由调用方通过 getApiErrorMessage 就地展示，
// 避免拦截器与视图 catch 各弹一条重复 toast。
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;

    // 登录接口自身的 401/400/404 属于凭证错误，由登录页就地展示并引导，
    // 不走"登录已过期"的会话失效逻辑（否则密码输错会被误报为登录过期）
    const requestUrl: string = error.config?.url || "";
    const isLoginRequest = /\/auth\/[a-z-]+-login$/.test(requestUrl);

    if (status === 401 && !isLoginRequest) {
      // 动态引入避免 client ↔ store 的模块循环依赖
      try {
        const { useAuthStore } = await import("@/stores/auth");
        useAuthStore().logout();
      } catch {
        // Pinia 尚未初始化的极端场景：退回手工清理，保证会话一定失效
        localStorage.removeItem("token");
        localStorage.removeItem("role");
        localStorage.removeItem("teacher");
        localStorage.removeItem("tenant");
      }
      showToast("登录已过期，请重新登录");
      const onLoginPage = window.location.pathname.endsWith("/login");
      if (!onLoginPage) {
        redirectToLogin();
      }
    }

    return Promise.reject(error);
  }
);

export default client;
