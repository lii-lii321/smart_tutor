/**
 * 生产构建产物冒烟（白屏事故 2026-11-03 的流程固化）：
 * e2e 跑在 vite dev server，测不到生产构建特有问题（manualChunks 双入口坑）——
 * 发版前必须以 dist 产物验证页面可渲染。本脚本：起 vite preview → 无头访问
 * 老版完整页/轻薄版/登录页 → 断言无 pageerror 且 #app 有真实内容。
 *
 * 用法：先 `npm run build`，再 `npm run test:preview`。
 */
import { spawn } from "node:child_process";
import { chromium } from "@playwright/test";

const PORT = 4179;
const BASE = `http://127.0.0.1:${PORT}`;
const PAGES = [
  ["老版完整页 Board", `${BASE}/teacher/board/tx886`],
  ["轻薄版 lite", `${BASE}/lite.html#/tx886`],
  ["老版登录页", `${BASE}/admin/login`],
];

const preview = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], {
  cwd: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  shell: true,
  stdio: "ignore",
});

async function waitForServer(timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/lite.html`);
      if (res.ok) return;
    } catch {
      /* 未就绪继续等 */
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("vite preview 未能在超时内就绪");
}

let failed = false;
try {
  await waitForServer();
  const browser = await chromium.launch();
  for (const [label, url] of PAGES) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push((e.stack || e.message).slice(0, 300)));
    await page.goto(url, { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(3500);
    const appLen = await page.evaluate(() => document.querySelector("#app")?.innerHTML.length ?? -1);
    const ok = appLen > 50 && errors.length === 0;
    if (!ok) failed = true;
    console.log(`${ok ? "OK  " : "FAIL"} ${label} — #app innerHTML=${appLen}${errors.length ? `, errors=${errors.length}` : ""}`);
    for (const err of errors) console.log("     ERROR:", err);
    await page.close();
  }
  await browser.close();
} finally {
  preview.kill();
}

if (failed) {
  console.error("preview 冒烟未全过：禁止发版");
  process.exit(1);
}
console.log("preview 冒烟全过");
