import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";

// Vant 样式在 unplugin 自动导入时处理
import "vant/lib/index.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
