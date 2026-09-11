import { expect, test } from "@playwright/test";

/**
 * E2E 冒烟链（PLAN P2-3 首批，全走真实后端 + DEV_MODE 播种数据）：
 * 1. 健康检查
 * 2. 教员橱窗页渲染（未登录）
 * 3. 中介登录 → 工作台
 */

test("健康检查 /health", async ({ request }) => {
  const res = await request.get("http://127.0.0.1:8000/health");
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.status).toBe("ok");
  expect(body.database).toBe(true);
});

test("教员橱窗页渲染（未登录）", async ({ page }) => {
  await page.goto("/teacher/board/tx886");

  // 推荐抽屉是静态结构，地图/AI 资源失败也不影响该锚点
  await expect(page.getByRole("heading", { name: "为你推荐" })).toBeVisible();
  // 地图容器在模板中始终存在
  await expect(page.locator("#map-container")).toBeAttached();
  // 底部教员 Tabbar 存在（橱窗/投递/个人中心入口）
  await expect(page.locator(".van-tabbar")).toBeAttached();
});

test("中介登录 → 工作台", async ({ page }) => {
  await page.goto("/admin/login");

  // /admin/login 会重定向到统一登录页的中介标签
  await expect(page).toHaveURL(/\/teacher\/login/);
  await page.getByPlaceholder("请输入中介邀请码").fill("tx886");
  await page.getByPlaceholder("请输入后台密码").fill("dev123456");
  await page.getByRole("button", { name: "进入中介后台" }).click();

  await page.waitForURL("**/admin/dashboard");
  await expect(page.getByText("本月为你")).toBeVisible();
});
