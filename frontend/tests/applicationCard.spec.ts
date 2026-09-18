/**
 * ApplicationCard 挂载测试：按投递状态渲染动作按钮的矩阵契约。
 * 此前该矩阵只在页面里"眼见为实"，状态→按钮→事件的映射回归靠人工；
 * 本文件锁定：每个状态出现哪些动作按钮、点击发出哪个事件（携带 app.id）。
 */
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ApplicationCard from "@/components/admin/ApplicationCard.vue";
import type { ApplicationItem, ApplicationStatus } from "@/api/types";

function makeApp(status: ApplicationStatus, overrides: Partial<ApplicationItem> = {}): ApplicationItem {
  return {
    id: 7,
    order_id: 42,
    raw_order_id: "E2E-001",
    teacher_id: 3,
    tenant_id: 1,
    tenant_name: "测试中介",
    order_grade_subject: "初中数学",
    order_price_total: "200/次",
    order_fuzzy_address: "成都·武侯区",
    resume_id: 5,
    teacher: null,
    status,
    proposed_price: null,
    applied_at: "2026-09-18T10:00:00",
    shortlisted_at: null,
    deposit_paid_at: null,
    balance_paid_at: null,
    rejected_at: null,
    refunded_at: null,
    ...overrides,
  };
}

function mountCard(status: ApplicationStatus, canRestore = false, overrides: Partial<ApplicationItem> = {}) {
  const app = makeApp(status, overrides);
  return mount(ApplicationCard, {
    props: { app, canRestore },
  });
}

const BUTTON_CASES: {
  status: ApplicationStatus;
  text: string;
  event: string;
}[] = [
  { status: "pending", text: "加入候选队列", event: "shortlist" },
  { status: "pending", text: "拒绝", event: "reject" },
  { status: "shortlisted", text: "确认定金", event: "confirm-deposit" },
  { status: "shortlisted", text: "拒绝", event: "reject" },
  { status: "deposit_paid", text: "开始试课", event: "start-trial" },
  { status: "trial_in_progress", text: "试课失败", event: "trial-failed" },
  { status: "trial_in_progress", text: "确认尾款", event: "confirm-balance" },
  { status: "balance_paid", text: "确认完成", event: "complete" },
];

describe("ApplicationCard 状态→动作按钮矩阵", () => {
  it.each(BUTTON_CASES)("$status 显示「$text」并发出 $event", ({ status, text, event }) => {
    const wrapper = mountCard(status);
    const button = wrapper.findAll("button").find((b) => b.text() === text);
    expect(button, `状态 ${status} 应有按钮「${text}」`).toBeTruthy();
    return button!.trigger("click").then(() => {
      expect(wrapper.emitted(event)).toEqual([[7]]);
    });
  });

  it("pending 不显示确认定金等后续动作", () => {
    const wrapper = mountCard("pending");
    const texts = wrapper.findAll("button").map((b) => b.text());
    expect(texts).not.toContain("确认定金");
    expect(texts).not.toContain("开始试课");
    expect(texts).not.toContain("确认完成");
  });

  it("rejected 在订单仍招聘中时显示恢复入口", () => {
    const wrapper = mountCard("rejected", true);
    const button = wrapper.findAll("button").find((b) => b.text().includes("恢复待审核"));
    expect(button).toBeTruthy();
  });

  it("rejected 在终态订单上不显示恢复入口", () => {
    const wrapper = mountCard("rejected", false);
    expect(wrapper.findAll("button").find((b) => b.text().includes("恢复待审核"))).toBeUndefined();
  });

  it("completed 的评价按钮区分首评/改评", () => {
    const first = mountCard("completed");
    expect(first.findAll("button").find((b) => b.text() === "评价教员")).toBeTruthy();

    const rated = mountCard("completed", false, {
      teacher: {
        id: 3, name: "张老师", gender: "female", school: "测试大学",
        is_985_211: true, is_985: true, is_211: false, is_double_first_class: false,
        major: null, grade: null, highlights: null,
        completed_count: 2, violation_count: 0, avg_rating: 4.5,
      },
    } as Partial<ApplicationItem>);
    expect(rated.findAll("button").find((b) => b.text() === "修改评价")).toBeTruthy();
  });

  it("状态徽标使用唯一口径文案", () => {
    const wrapper = mountCard("pending");
    expect(wrapper.text()).toContain("待审核");
  });
});
