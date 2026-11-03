import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import AutoImport from "unplugin-auto-import/vite";
import { VantResolver } from "@vant/auto-import-resolver";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [VantResolver()],
    }),
    Components({
      resolvers: [VantResolver()],
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      // MPA 双入口：index.html（完整版 SPA）+ lite.html（轻薄版橱窗，独立免登录单页）
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        lite: fileURLToPath(new URL("./lite.html", import.meta.url)),
      },
      // ⚠️ 不要手动 manualChunks 硬拆 vendor/vant：单入口时代的老配置，双入口下会把
      // node_modules 强行合并进共享 chunk，破坏模块初始化顺序——2026-11-03 线上实测
      // 两个入口同时白屏（vendor 内部 "t is not a function"，老页面一并打崩）。
      // Rolldown 按模块图自动分包，框架代码同样落在稳定命名的共享 chunk，缓存收益相当。
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
