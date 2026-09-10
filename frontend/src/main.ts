import { createApp } from "vue";
import { createPinia } from "pinia";
import { showToast } from "vant";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);

// 全局错误边界：单组件渲染/事件异常不再整页白屏；toast 节流防止错误风暴刷屏
let lastErrorToastAt = 0;
app.config.errorHandler = (err, instance, info) => {
  console.error("[vue] 未处理异常:", err, "\n组件:", instance, "\n阶段:", info);
  const now = Date.now();
  if (now - lastErrorToastAt > 3000) {
    lastErrorToastAt = now;
    showToast("页面出现异常，请刷新重试");
  }
};

app.mount("#app");
