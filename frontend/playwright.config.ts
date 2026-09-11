import { defineConfig, devices } from "@playwright/test";

/**
 * E2E 冒烟（PLAN P2-3）：
 * - 自动拉起两个本地服务：后端 uvicorn（DEV_MODE 播种演示数据）+ 前端 vite dev（/api 代理）
 * - `npm run test:e2e` 本地跑；CI 仅 workflow_dispatch 手动触发，不挡 PR
 * - 断言保持宽松（关键 UI 锚点可见），避免地图等三方资源抖动造成误报
 */
const BACKEND_PORT = 8000;
const FRONTEND_PORT = 5173;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `python -m uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: "..",
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DEV_MODE: "true",
        AUTO_CREATE_SCHEMA: "true",
        JWT_SECRET: "e2e-local-secret-0123456789abcdef",
        OWNER_ACCESS_CODE: "e2e-boss-code",
        // 独立库：E2E 始终基于当前 schema 的全新库，不受本地 dev.db 旧 schema 影响
        DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
        // E2E 期间不上报 Sentry
        SENTRY_DSN: "",
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
