import { createApp } from "vue";
import LiteApp from "./LiteApp.vue";
import "@/styles/main.css";

// 轻薄版橱窗：免登录单页（无 pinia/无 router），只调 /public/* 免鉴权接口
createApp(LiteApp).mount("#app");
