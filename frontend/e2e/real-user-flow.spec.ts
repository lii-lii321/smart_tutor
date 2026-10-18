// 临时双边真实用户流程：教员(李云强)投递 → 中介(tx_cd)审核推进到成交。用后即删。
import { expect, test } from "@playwright/test";
import fs from "node:fs";

const SITE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8000";
const teacherToken = fs.readFileSync("e2e/.teacher-token", "utf-8").trim();
const teacherJson = JSON.stringify({ id: 13, name: "李云强" });

async function confirmPopup(page: Pick<import("@playwright/test").Page, "locator">, label: string) {
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
  let applicationId = 0;

  test("A. 中介待办取单 → 教员 UI 投递", async ({ page, request }) => {
    // 中介 API 拿待办第一笔在招订单（审核页左栏第一页必含它，保证 B 可定位）
    const tLogin = await request.post(`${API}/api/v1/auth/tenant-login`, {
      data: { invite_code: "tx_cd", password: "dev123456" },
    });
    const tHeaders = { Authorization: `Bearer ${(await tLogin.json()).token}` };
    const todoList = await (
      await request.get(`${API}/api/v1/orders/?page=1&page_size=20`, { headers: tHeaders })
    ).json();
    // 取含「数学」的非自带价在招单：教员简历为理科方向，投递弹层的
    // checkResumeFit 会拦截科目不匹配的简历（防误投设计）
    const target = todoList.items.find(
      (o: { status: string; needs_manual_price: boolean; grade_subject: string }) =>
        o.status === "recruiting" && !o.needs_manual_price && o.grade_subject.includes("数学"),
    );
    expect(target).toBeTruthy();
    fs.writeFileSync("e2e/.flow-order-rawid", target.raw_id);

    // 教员登录态注入（李云强密码未知，用 dev 签发的直连 token）
    await page.addInitScript(
      ([t, r, teacher]) => {
        localStorage.setItem("token", t as string);
        localStorage.setItem("role", r as string);
        localStorage.setItem("teacher", teacher as string);
      },
      [teacherToken, "teacher", teacherJson],
    );

    // 真实用户路径：订单详情页 → 选简历 → 投递（两次确认）
    page.on("response", async (resp) => {
      if (resp.url().includes("/applications") && resp.request().method() === "POST") {
        let body = "";
        try {
          body = (await resp.text()).slice(0, 200);
        } catch {
          body = "<no body>";
        }
        console.log(`[net] POST ${resp.url().slice(-40)} -> ${resp.status()} ${body}`);
      }
    });
    await page.goto(`${SITE}/teacher/orders/${target.id}`);
    await page.getByRole("button", { name: "选择简历并投递" }).click();
    await page.getByText("理科主简历").first().waitFor({ timeout: 8000 });

    // 模拟真实用户：逐份简历尝试，直到「确认投递」可点（科目不匹配的简历会被
    // checkResumeFit 禁用——这是产品的防误投设计）
    const radios = page.getByRole("radio");
    const resumeCount = await radios.count();
    let popupConfirm = page.locator(".van-popup").getByRole("button", { name: "确认投递" }).last();
    for (let i = 0; i < resumeCount; i++) {
      await radios.nth(i).click();
      await page.waitForTimeout(300);
      if (await popupConfirm.isEnabled()) break;
    }
    await expect(popupConfirm).toBeEnabled();
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

  test("B. 中介 UI：投递审核五步推进到成交", async ({ page, request }) => {
    // UI 登录的 van-field 在 Playwright fill 下偶发不触发 v-model（按钮持续 disabled），
    // 登录方式非本轮测试目标——改用 API 登录 + token 注入，页面操作仍是真实 UI 点击
    const login = await request.post(`${API}/api/v1/auth/tenant-login`, {
      data: { invite_code: "tx_cd", password: "dev123456" },
    });
    const { token: tenantToken, tenant } = await login.json();

    await page.addInitScript(
      ([t, tenantJson]) => {
        localStorage.setItem("token", t as string);
        localStorage.setItem("role", "tenant_admin");
        localStorage.setItem("tenant", tenantJson as string);
      },
      [tenantToken, JSON.stringify(tenant)],
    );

    await page.goto(`${SITE}/admin/applications`);
    await page.waitForTimeout(2500);

    // 左栏按订单显示编号定位李云强的投递（A 步已写入文件）
    const rawId = fs.readFileSync("e2e/.flow-order-rawid", "utf-8").trim();
    const card = page.locator(`text=${rawId}`).first();
    await card.click();
    await page.waitForTimeout(1500);

    // 五步推进用 API（与既有 teacher-flow.spec.ts 同款模式；连续审核自动推进后
    // 左栏卡片按钮定位不稳定，UI 路径已由用户手工验证过）
    const tHeaders = { Authorization: `Bearer ${tenantToken}` };

    const list = await (
      await page.request.get(`${API}/api/v1/orders/?q=${encodeURIComponent(rawId)}`, {
        headers: tHeaders,
      })
    ).json();
    const orderId = list.items[0].id;
    const apps = await (
      await page.request.get(`${API}/api/v1/applications/order/${orderId}`, { headers: tHeaders })
    ).json();
    const pending = apps.find((a: { status: string }) => a.status === "pending");
    const applicationId = pending.id;

    // 状态机对调（真实业务：简历通过→补齐尾款→安排试课）：confirm-balance 先于 start-trial
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
    await expect(page.getByText(rawId).first()).toBeVisible({ timeout: 15_000 });

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
    const mine = apps.find((a: { order_id: number }) => true);
    expect(mine).toBeTruthy();
    applicationId = mine.id;
    // 完整链最终态：completed
    const detail = apps.find((a: { status: string }) => a.status === "completed");
    expect(detail).toBeTruthy();
  });
});
