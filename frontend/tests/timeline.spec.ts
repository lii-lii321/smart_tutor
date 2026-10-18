/**
 * 投递时间线映射测试：锁定 buildApplicationLifecycleSteps 对全量
 * ApplicationStatus（9 态）的展示口径——重点回归 deposit_paid
 * （2026-10-18 实测该状态被遗漏，时间线只亮到"已提交"，与"定金已确认"提示矛盾）。
 */
import { describe, expect, it } from "vitest";

import type { ApplicationItem, ApplicationStatus } from "@/api/types";
import { buildApplicationLifecycleSteps } from "@/components/business/timeline";

function makeApp(status: ApplicationStatus, overrides: Partial<ApplicationItem> = {}): ApplicationItem {
  return {
    id: 1,
    order_id: 1,
    raw_order_id: "S1",
    teacher_id: 1,
    tenant_id: 1,
    tenant_name: "测试中介",
    order_grade_subject: "初三数学",
    order_price_total: "200/次",
    order_fuzzy_address: "成都市武侯区",
    resume_id: null,
    teacher: null,
    status,
    proposed_price: null,
    applied_at: "2026-10-18T10:00:00",
    shortlisted_at: "2026-10-18T11:00:00",
    deposit_paid_at: "2026-10-18T12:00:00",
    balance_paid_at: null,
    rejected_at: null,
    refunded_at: null,
    ...overrides,
  };
}

function states(status: ApplicationStatus): string[] {
  return buildApplicationLifecycleSteps(makeApp(status)).map((s) => s.state);
}

describe("buildApplicationLifecycleSteps 状态→时间线映射", () => {
  it("deposit_paid：提交/审核/定金三步 done，试课为当前待办", () => {
    expect(states("deposit_paid")).toEqual([
      "done", // 已提交投递
      "done", // 中介审核
      "done", // 定金
      "todo", // 试课（等待安排）
      "todo", // 尾款
      "todo", // 成交
    ]);
  });

  it("balance_paid：尾款 done", () => {
    expect(states("balance_paid")).toEqual([
      "done",
      "done",
      "done",
      "done",
      "done",
      "todo",
    ]);
  });

  it("completed：全部 done", () => {
    expect(states("completed").every((s) => s === "done")).toBe(true);
  });

  it("rejected：审核 skipped，其余如实保留", () => {
    const steps = buildApplicationLifecycleSteps(makeApp("rejected"));
    expect(steps[1].state).toBe("skipped");
    expect(steps[0].state).toBe("done");
  });
});
