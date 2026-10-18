/**
 * 投递时间线映射测试：锁定 buildApplicationLifecycleSteps 对全量
 * ApplicationStatus（9 态）的展示口径。
 * 2026-10-18 两轮校准：
 * - deposit_paid 不再被遗漏（时间线亮到"定金"，与"定金已确认"提示一致）；
 * - 状态机对调（真实业务：简历通过→补齐尾款→安排试课），尾款步在试课之前；
 * - 尾款/试课按事件时间戳兜底，状态机调序前的存量数据也如实展示。
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
    trial_started_at: null,
    completed_at: null,
    rejected_at: null,
    refunded_at: null,
    ...overrides,
  };
}

function states(status: ApplicationStatus, overrides: Partial<ApplicationItem> = {}): string[] {
  return buildApplicationLifecycleSteps(makeApp(status, overrides)).map((s) => s.state);
}

describe("buildApplicationLifecycleSteps 状态→时间线映射", () => {
  it("deposit_paid：提交/审核/定金三步 done，尾款/试课为待办", () => {
    expect(states("deposit_paid")).toEqual([
      "done", // 已提交投递
      "done", // 中介审核
      "done", // 定金
      "todo", // 尾款（待补齐）
      "todo", // 试课（信息费付齐后安排）
      "todo", // 成交
    ]);
  });

  it("balance_paid：尾款 done，试课待安排", () => {
    expect(states("balance_paid")).toEqual([
      "done",
      "done",
      "done",
      "done",
      "todo",
      "todo",
    ]);
  });

  it("trial_in_progress：尾款/试课均 done，成交待办（新机器下试课中必已收齐尾款）", () => {
    expect(
      states("trial_in_progress", { balance_paid_at: "2026-10-18T12:30:00" })
    ).toEqual([
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

  it("存量兜底：trial_in_progress 未收尾款（调序前老数据）按事件如实展示", () => {
    // 老状态机遗留：试课已开始但尾款未收——试课 done、尾款 todo，不伪造
    expect(
      states("trial_in_progress", {
        trial_started_at: "2026-10-18T13:00:00",
        balance_paid_at: null,
      })
    ).toEqual(["done", "done", "done", "todo", "done", "todo"]);
  });

  it("存量兜底：balance_paid 已带试课时间（调序前老数据）试课如实 done", () => {
    expect(
      states("balance_paid", { trial_started_at: "2026-10-18T13:00:00" })
    ).toEqual(["done", "done", "done", "done", "done", "todo"]);
  });
});
