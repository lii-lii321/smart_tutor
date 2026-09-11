import { createApp } from "vue";
import { createPinia } from "pinia";
import { showToast } from "vant";
import * as Sentry from "@sentry/vue";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);

// Sentry 错误上报（P1-9）：DSN 未配置时完全不初始化（本地/CI 零感知）。
// captureException 仅在初始化后调用，避免无 client 时产生 SDK 告警
const sentryReady = initSentry();

// 全局错误边界：单组件渲染/事件异常不再整页白屏；toast 节流防止错误风暴刷屏
let lastErrorToastAt = 0;
app.config.errorHandler = (err, instance, info) => {
  console.error("[vue] 未处理异常:", err, "\n组件:", instance, "\n阶段:", info);
  if (sentryReady) {
    Sentry.captureException(err, { extra: { vueStage: info } });
  }
  const now = Date.now();
  if (now - lastErrorToastAt > 3000) {
    lastErrorToastAt = now;
    showToast("页面出现异常，请刷新重试");
  }
};

app.mount("#app");

function initSentry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) {
    return false;
  }
  Sentry.init({
    app,
    dsn,
    environment: import.meta.env.DEV ? "development" : "production",
    // 路由切换作为性能事务上报，采样 10%（与后端一致）
    integrations: [Sentry.browserTracingIntegration({ router })],
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
  return true;
}
