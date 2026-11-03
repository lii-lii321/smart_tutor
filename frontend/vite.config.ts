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
      output: {
        // 框架运行时独立成 vendor chunk：业务页发版后用户无需重新下载框架代码
        // （Vite 8 底层为 Rolldown，manualChunks 仅支持函数形式）
        manualChunks(id: string) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("vant")) {
            return "vant";
          }
          return "vendor";
        },
      },
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
