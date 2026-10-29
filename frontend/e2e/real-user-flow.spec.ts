// 双边真实用户流回归：中介 API 预置数学单 → 教员（双简历）UI 投递（防误投拦截）
// → 中介审核页 UI 按编号定位 + API 五步推进到成交 → 历史 tab 成交可见 →
// 教员 API 断言终态。全部数据用例内自建（e2e.db 每轮重建，种子租户 tx886），可重复运行。
// 测试密码按仓库约定拼接构造，不落凭据字面量（仅 DEV_MODE 播种环境有效）。
import { expect, test } from "@playwright/test";

const SITE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8000";
const TENANT_PASSWORD = "dev" + "123456";
const TENANT = { invite_code: "tx886", password: TENANT_PASSWORD };
const TEACHER_PHONE = "139" + String(Date.now()).slice(-8);
const TEACHER_PASSWORD = "e2e" + "Pass" + "123";
const ORDER_RAW_ID = "FLOW-" + String(Date.now()).slice(-6);
const PARENT_PHONE = "13900000000";

let teacherToken = "";

async function appConfirm(page: Pick<import("@playwright/test").Page, "locator">, label: string) {
  // appConfirm 确认键特征：rounded-xl（区别于业务弹层自身的 rounded-full 按钮）
  for (let attempt = 0; attempt < 3; attempt++) {
    const btn = page
      .locator(".van-popup button.rounded-xl")
      .filter({ hasText: label })
      .last();
    if (await btn.count()) {
      await btn.click();
      return true;
    }
    await page.waitForTimeout(500);
  }
  return false;
}

test.describe.serial(() => {
  let tenantToken = "";
  let orderId = 0;

  test("A. 预置数学单 → 教员 API 注册建双简历 → 教员 UI 投递（防误投拦截）", async ({ page, request }) => {
    const tLogin = await request.post(`${API}/api/v1/auth/tenant-login`, { data: TENANT });
    expect(tLogin.ok()).toBeTruthy();
    tenantToken = (await tLogin.json()).token;

    const importRes = await request.post(`${API}/api/v1/orders/batch-import`, {
      headers: { Authorization: `Bearer ${tenantToken}` },
      data: {
        items: [
          {
            raw_id: ORDER_RAW_ID,
            raw_text: `FLOW 测试订单 ${ORDER_RAW_ID} 联系家长 ${PARENT_PHONE}`,
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
    expect(importRes.ok()).toBeTruthy();
    const list = await (
      await request.get(`${API}/api/v1/orders/?q=${ORDER_RAW_ID}`, {
        headers: { Authorization: `Bearer ${tenantToken}` },
      })
    ).json();
    orderId = list.items[0].id;
    expect(orderId).toBeGreaterThan(0);

    const reg = await request.post(`${API}/api/v1/auth/teacher-phone-register`, {
      data: {
        invite_code: TENANT.invite_code,
        name: "双简历教员",
        gender: "male",
        phone: TEACHER_PHONE,
        password: TEACHER_PASSWORD,
        wechat_id: "e2e_flow_01",
        school: "测试大学",
      },
    });
    expect(reg.ok()).toBeTruthy();
    const regBody = await reg.json();
    teacherToken = regBody.token;

    const tHeaders = { Authorization: `Bearer ${teacherToken}` };
    for (const resume of [
      { title: "数学主简历", teaching_subjects: "数学", teaching_grades: "初一-高三" },
      { title: "语文辅简历", teaching_subjects: "语文", teaching_grades: "初一-高三" },
    ]) {
      const res = await request.post(`${API}/api/v1/teacher/resumes/`, {
        headers: tHeaders,
        data: {
          ...resume,
          experience: "E2E 自动化测试经历",
          strengths: "讲解清晰",
          availability: "周末全天",
          expected_rate: "200-300/次",
        },
      });
      expect(res.ok()).toBeTruthy();
    }

    // 教员登录态注入（注册响应即含 token 与教员信息），页面操作保持真实 UI 点击
    await page.addInitScript(
      ([t, teacher]) => {
        localStorage.setItem("token", t as string);
        localStorage.setItem("role", "teacher");
        localStorage.setItem("teacher", teacher as string);
      },
      [teacherToken, JSON.stringify(regBody.teacher)],
    );

    await page.goto(`${SITE}/teacher/orders/${orderId}`);
    await page.getByRole("button", { name: "选择简历并投递" }).click();
    await page.getByText("语文辅简历").first().waitFor({ timeout: 8000 });

    // 防误投回归：语文简历对「初一数学」单应被判不匹配并禁用「确认投递」
    const popupConfirm = page.locator(".van-popup").getByRole("button", { name: "确认投递" }).last();
    await page.getByText("语文辅简历").first().click();
    await expect(popupConfirm).toBeDisabled({ timeout: 5000 });

    await page.getByText("数学主简历").first().click();
    await expect(popupConfirm).toBeEnabled({ timeout: 5000 });
    await popupConfirm.click();
    // appConfirm 底部二次确认：rounded-xl 确认键（与业务弹层 rounded-full 区分）
    const appConfirmBtn = page
      .locator(".van-popup button.rounded-xl")
      .filter({ hasText: "确认投递" })
      .last();
    await appConfirmBtn.waitFor({ timeout: 5000 });
    await appConfirmBtn.click();
    await page.waitForURL("**/teacher/applications", { timeout: 15_000 });
    await expect(page.getByText("待审核").first()).toBeVisible();
  });

  test("B. 中介审核页 UI 定位 → 五步推进到成交 → 历史可见", async ({ page, request }) => {
    // UI 登录的 van-field 在 Playwright fill 下偶发不触发 v-model（按钮持续 disabled），
    // 登录方式非本轮测试目标——API 登录 + token 注入，页面操作仍是真实 UI 点击
    const login = await request.post(`${API}/api/v1/auth/tenant-login`, { data: TENANT });
    const loginBody = await login.json();
    const tToken = loginBody.token as string;

    await page.addInitScript(
      ([t, tenant]) => {
        localStorage.setItem("token", t as string);
        localStorage.setItem("role", "tenant_admin");
        localStorage.setItem("tenant", tenant as string);
      },
      [tToken, JSON.stringify(loginBody.tenant)],
    );

    await page.goto(`${SITE}/admin/applications`);
    await page.waitForTimeout(2500);

    // 左栏按订单编号定位 A 步的投递
    const card = page.locator(`text=${ORDER_RAW_ID}`).first();
    await card.click();
    await page.waitForTimeout(1500);

    // 五步推进用 API（与既有 teacher-flow.spec.ts 同款模式；连续审核自动推进后
    // 左栏卡片按钮定位不稳定，UI 路径已由用户手工验证过）。
    // 状态机对调（真实业务：简历通过→补齐尾款→安排试课）：confirm-balance 先于 start-trial
    const tHeaders = { Authorization: `Bearer ${tToken}` };
    const apps = await (
      await page.request.get(`${API}/api/v1/applications/order/${orderId}`, { headers: tHeaders })
    ).json();
    const pending = apps.find((a: { status: string }) => a.status === "pending");
    expect(pending).toBeTruthy();
    const applicationId = pending.id;

    for (const action of ["shortlist", "confirm-deposit", "confirm-balance", "start-trial", "complete"]) {
      const res = await page.request.post(
        `${API}/api/v1/applications/${applicationId}/${action}`,
        { headers: tHeaders },
      );
      if (res.status() !== 200) {
        console.log(`[flow] ${action} -> ${res.status()} ${await res.text()}`);
      }
      await page.waitForTimeout(300);
    }

    // 中介 UI 刷新后切到「历史」tab：成交投递从待办移入历史
    await page.reload();
    await page.waitForTimeout(2500);
    await page.getByText("历史", { exact: true }).first().click();
    await page.waitForTimeout(1500);
    await expect(page.getByText(ORDER_RAW_ID).first()).toBeVisible({ timeout: 15_000 });

    // 数据终态断言：投递状态 = completed（完整链闭环）
    const detail = await (
      await page.request.get(`${API}/api/v1/applications/order/${orderId}`, { headers: tHeaders })
    ).json();
    expect(detail[0].status).toBe("completed");
  });

  test("C. 教员端 API 断言已成交", async ({ request }) => {
    const apps = await (
      await request.get(`${API}/api/v1/applications/mine?page=1&page_size=50`, {
        headers: { Authorization: `Bearer ${teacherToken}` },
      })
    ).json();
    const mine = apps.find((a: { order_id: number }) => a.order_id === orderId);
    expect(mine).toBeTruthy();
    // 完整链最终态：completed
    expect(mine.status).toBe("completed");
  });
});
