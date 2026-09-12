import { expect, test } from "@playwright/test";

/**
 * 教员全链 E2E（PLAN P2-3 / A1 扩链）：
 * 中介 API 预置订单 → 教员 UI 注册/建简历/投递 → 中介 API 审核流转到成交 →
 * 教员端状态与脱敏断言。
 *
 * 串行执行（共享模块变量）；端口 8000 直接命中后端（Playwright 已拉起），
 * 页面走 5173 前端（/api 代理到后端）。
 */

const API = "http://127.0.0.1:8000";
const SITE = "http://127.0.0.1:5173";

const testPhone = "139" + String(Date.now()).slice(-8);
const testPassword = "e2ePass123";
const ORDER_RAW_ID = "E2E-" + String(Date.now()).slice(-6);
const PARENT_PHONE = "13900000000";

let tenantToken = "";
let teacherToken = "";
let orderId = 0;
let applicationId = 0;

async function apiLoginTenant(request: import("@playwright/test").APIRequestContext) {
  const res = await request.post(`${API}/api/v1/auth/tenant-login`, {
    data: { invite_code: "tx886", password: "dev123456" },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).token as string;
}

test.describe.serial(() => {
  test("A. 中介 API 预置订单", async ({ request }) => {
    tenantToken = await apiLoginTenant(request);
    const res = await request.post(`${API}/api/v1/orders/batch-import`, {
      headers: { Authorization: `Bearer ${tenantToken}` },
      data: {
        items: [
          {
            raw_id: ORDER_RAW_ID,
            raw_text: `E2E 测试订单 ${ORDER_RAW_ID} 联系家长 ${PARENT_PHONE}`,
            grade_subject: "初一数学",
            requirements: "有耐心",
            price_total: "200/次",
            base_price: 200,
            weekly_frequency: 2,
            exact_address: "天府大道1号101室",
            parent_phone: PARENT_PHONE,
            fuzzy_address: "成都市天府大道",
            lng: 104.06,
            lat: 30.57,
            calculated_info_fee: 200,
            deposit_amount: 100,
            balance_amount: 100,
          },
        ],
      },
    });
    expect(res.status()).toBe(200);
    // 重复运行时 raw_id 已存在，imported 为 0 也算通过（订单由下方查询兜底）
    expect([0, 1]).toContain((await res.json()).imported);

    const list = await request.get(`${API}/api/v1/orders/?q=${ORDER_RAW_ID}`, {
      headers: { Authorization: `Bearer ${tenantToken}` },
    });
    const body = await list.json();
    expect(body.items.length).toBe(1);
    orderId = body.items[0].id;
    expect(orderId).toBeGreaterThan(0);
  });

  test("B. 教员 UI 注册 → 建简历 → 投递", async ({ page }) => {
    // 注册（注册即自动登录）
    await page.goto(`${SITE}/teacher/register`);
    await page.getByPlaceholder("请输入手机号").fill(testPhone);
    await page.getByPlaceholder("请输入中介邀请码").fill("tx886");
    await page.getByPlaceholder("设置登录密码").fill(testPassword);
    await page.getByPlaceholder("请输入真实姓名").fill("E2E教员");
    await page.getByPlaceholder("用于中介联系你").fill("e2e_wx_001");
    await page.getByPlaceholder("毕业/在读院校").fill("测试大学");
    await page.getByPlaceholder("所学专业").fill("数学与应用数学");
    await page.getByRole("button", { name: "完成注册" }).click();
    await expect(page.getByText("注册成功")).toBeVisible();

    // 建一份能匹配「初一数学」订单的简历
    await page.goto(`${SITE}/teacher/profile`);
    await page.getByRole("button", { name: "新增", exact: true }).click();
    await page.getByPlaceholder("如：高中英语主简历").fill("E2E 数学简历");
    await page.getByPlaceholder("如：英语 / 数学").fill("数学");
    await page.getByPlaceholder("如：初中 / 高中 / 高三").fill("初一-初三");
    await page.getByPlaceholder("写清过往家教、提分案例、授课风格").fill("E2E 自动化测试经历");
    await page.getByRole("button", { name: "保存简历" }).click();
    await expect(page.getByText("E2E 数学简历")).toBeVisible();

    // 打开订单详情 → 打开投递弹层 → 选中简历 → 投递 → 确认对话框 → 跳转我的投递
    await page.goto(`${SITE}/teacher/orders/${orderId}`);
    await page.getByRole("button", { name: "选择简历并投递" }).click();
    await page.getByText("E2E 数学简历").click();
    await page.getByRole("button", { name: "确认投递" }).click();
    // vant 确认对话框（提示文案含"投递成功后…"，必须点确认才真正提交）
    await page.getByRole("dialog").getByRole("button", { name: "确认", exact: true }).click();
    await page.waitForURL("**/teacher/applications");
  });

  test("C. 中介审核流转：候选→定金→试课→尾款→成交", async ({ request }) => {
    const headers = { Authorization: `Bearer ${tenantToken}` };

    const apps = await (await request.get(`${API}/api/v1/applications/order/${orderId}`, { headers })).json();
    expect(apps.length).toBe(1);
    applicationId = apps[0].id;
    expect(apps[0].status).toBe("pending");

    const transitions: [string, string][] = [
      ["shortlist", "shortlisted"],
      ["confirm-deposit", "deposit_paid"],
      ["start-trial", "trial_in_progress"],
      ["confirm-balance", "balance_paid"],
      ["complete", "completed"],
    ];
    for (const [action, expected] of transitions) {
      const res = await request.post(`${API}/api/v1/applications/${applicationId}/${action}`, { headers });
      expect(res.status(), `${action} 应成功`).toBe(200);
      expect((await res.json()).status).toBe(expected);
    }
  });

  test("D. 教员视角脱敏（API 断言）", async ({ request }) => {
    const login = await request.post(`${API}/api/v1/auth/teacher-phone-login`, {
      data: { phone: testPhone, invite_code: "tx886", password: testPassword },
    });
    expect(login.ok()).toBeTruthy();
    teacherToken = (await login.json()).token;

    const headers = { Authorization: `Bearer ${teacherToken}` };
    const teacherView = await (await request.get(`${API}/api/v1/orders/${orderId}`, { headers })).json();
    expect(teacherView.parent_phone).toBeNull();
    expect(teacherView.exact_address).toBeNull();
    expect(teacherView.raw_text).not.toContain(PARENT_PHONE);
    expect(teacherView.raw_text).toContain("****");

    const tenantView = await (await request.get(`${API}/api/v1/orders/${orderId}`, {
      headers: { Authorization: `Bearer ${tenantToken}` },
    })).json();
    expect(tenantView.parent_phone).toBe(PARENT_PHONE);
    expect(tenantView.exact_address).toContain("天府大道");
  });

  test("E. 教员端 UI 显示已成交", async ({ page }) => {
    await page.goto(`${SITE}/teacher/login`);
    await page.getByPlaceholder("请输入手机号").fill(testPhone);
    await page.getByPlaceholder("请输入中介邀请码").fill("tx886");
    await page.getByPlaceholder("请输入登录密码").fill(testPassword);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL(/teacher\/(board|applications|profile)/);

    await page.goto(`${SITE}/teacher/applications`);
    await expect(page.getByText("已成交").first()).toBeVisible({ timeout: 15_000 });
  });
});
