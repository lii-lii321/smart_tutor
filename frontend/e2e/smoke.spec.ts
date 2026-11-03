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

  // 未登录态首屏锚点：UI 2.0 大标题的游客分支（「为你推荐」仅登录+有推荐时出现）
  await expect(page.getByRole("heading", { name: "找到适合你的家教订单" })).toBeVisible();
  // 地图容器在模板中始终存在
  await expect(page.locator("#map-container")).toBeAttached();
  // 底部教员 Tabbar 存在（橱窗/投递/个人中心入口）
  await expect(page.locator(".teacher-tabbar")).toBeAttached();
});

test("轻薄版橱窗全链（免登录：预置单→卡片→详情掩码→复制微信）", async ({ page, request }) => {
  // API 预置一张带家长电话的招聘中订单（自给自足，不依赖播种数据；参考 real-user-flow 模式）
  const login = await request.post("http://127.0.0.1:8000/api/v1/auth/tenant-login", {
    data: { invite_code: "tx886", password: "dev123456" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).token as string;
  const rawId = `LITE-${Date.now()}`;
  const imported = await request.post("http://127.0.0.1:8000/api/v1/orders/batch-import", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      items: [
        {
          raw_id: rawId,
          raw_text: `【${rawId}】初三数学，家长电话 13800001111`,
          grade_subject: "初三数学",
          price_total: "200/次",
          base_price: 200,
          weekly_frequency: 2,
          fuzzy_address: "成都市天府大道",
          lng: 104.066,
          lat: 30.658,
          calculated_info_fee: 400,
          deposit_amount: 100,
          balance_amount: 300,
        },
      ],
    },
  });
  expect(imported.ok()).toBeTruthy();

  await page.goto("/lite.html#/tx886");

  // 骨架：筛选按钮与地图容器始终存在
  await expect(page.getByRole("button", { name: "筛选" })).toBeVisible();
  await expect(page.locator("#lite-map-container")).toBeAttached();

  // 地图视图：预置单以图钉或聚合气泡出现在地图上（聚合把堆叠单变成可见数量）
  await page.waitForTimeout(3000);
  const mapPin = page
    .locator("#lite-map-container .order-marker, #lite-map-container .lite-cluster-bubble")
    .first();
  await expect(mapPin).toBeAttached({ timeout: 15000 });

  // 列表视图：预置单卡片可见
  await page.getByRole("button", { name: "列表" }).click();
  const card = page.getByRole("button", { name: /初三数学/ }).first();
  await expect(card).toBeVisible({ timeout: 15000 });

  // 详情弹层：家长电话必须已掩码（完整号码不得出现在页面任何位置）
  await card.click();
  await expect(page.getByText("138****1111")).toBeVisible();
  const pageContent = await page.content();
  expect(pageContent).not.toContain("13800001111");
  expect(pageContent).not.toContain("parent_phone");
  // 转化动作：复制微信按钮（轻薄版唯一的 CTA，文案携带微信号）
  await expect(page.getByRole("button", { name: /复制微信/ })).toBeVisible();
});

test("中介登录 → 工作台", async ({ page }) => {
  await page.goto("/admin/login");

  // 中介与教员各有独立登录路由（?tab= 已永久迁移），停留在 /admin/login 本页
  await expect(page).toHaveURL(/\/admin\/login/);
  await page.getByPlaceholder("请输入中介邀请码").fill("tx886");
  await page.getByPlaceholder("请输入后台密码").fill("dev123456");
  await page.getByRole("button", { name: "进入中介后台" }).click();

  await page.waitForURL("**/admin/dashboard");
  await expect(page.getByRole("heading", { name: "本月经营" })).toBeVisible();
});
