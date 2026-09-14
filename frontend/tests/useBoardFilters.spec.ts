import { describe, expect, it } from "vitest";
import { useBoardFilters, stageOptions } from "@/composables/useBoardFilters";
import type { PublicOrderBrief } from "@/api/types";

/** 构造橱窗订单的最小字段集（其余字段筛选逻辑不消费） */
function order(id: number, gradeSubject: string, fuzzyAddress: string, lng = 104.06, lat = 30.65): PublicOrderBrief {
  return {
    id,
    raw_id: `B-${id}`,
    grade_subject: gradeSubject,
    price_total: "200/次",
    base_price: 200,
    calculated_info_fee: 200,
    deposit_amount: 100,
    balance_amount: 100,
    needs_manual_price: false,
    fuzzy_address: fuzzyAddress,
    subway_remark: null,
    lng,
    lat,
    weekly_frequency: 2,
    is_summer_vacation: false,
    expired_at: null,
    created_at: null,
  };
}

function setup(orders: PublicOrderBrief[]) {
  const filters = useBoardFilters({
    boardOrders: () => orders,
    getMap: () => null,
  });
  return filters;
}

describe("useBoardFilters 学段与科目识别", () => {
  it("学段筛选按年级科目归档（初中学段只留初中单）", () => {
    const orders = [
      order(1, "初一数学", "成都市成华区xx"),
      order(2, "高中英语", "成都市武侯区xx"),
      order(3, "小学语文", "成都市青羊区xx"),
    ];
    const f = setup(orders);
    f.selectedStage.value = "junior";
    expect(f.filteredOrders.value.map((o) => o.id)).toEqual([1]);
  });

  it("学段恢复全部后清空科目筛选联动", () => {
    const orders = [order(1, "初一数学", "成都市成华区xx")];
    const f = setup(orders);
    f.selectedStage.value = "junior";
    f.selectedSubjects.value = ["物理"];
    expect(f.filteredOrders.value).toHaveLength(0);

    f.resetFilters();
    expect(f.filteredOrders.value).toHaveLength(1);
    expect(f.hasActiveFilters.value).toBe(false);
  });

  it("activeFilterCount 按三个维度累计", () => {
    const f = setup([]);
    expect(f.activeFilterCount.value).toBe(0);

    f.selectedStage.value = "senior";
    f.selectedSubjects.value = ["英语", "数学"];
    f.selectedCity.value = "成都市";
    expect(f.activeFilterCount.value).toBe(4);
    expect(f.hasActiveFilters.value).toBe(true);
  });

  it("stageOptions 覆盖四个学段加全部", () => {
    expect(stageOptions.map((s) => s.value)).toEqual(["all", "primary", "junior", "senior", "other"]);
  });
});

describe("useBoardFilters 城市识别与过滤", () => {
  it("显式城市前缀的订单按前缀归城市", () => {
    const orders = [
      order(1, "初一数学", "成都市青羊区金沙晴朗居"),
      order(2, "高一物理", "绵阳市涪城区xx"),
    ];
    const f = setup(orders);
    f.selectedCity.value = "成都市";
    expect(f.filteredOrders.value.map((o) => o.id)).toEqual([1]);
  });

  it("直辖市前缀按直辖市归并", () => {
    const orders = [order(1, "初一数学", "北京市朝阳区xx")];
    const f = setup(orders);
    f.selectedCity.value = "北京市";
    expect(f.filteredOrders.value).toHaveLength(1);
  });

  it("无城市地址 + 无城市中心时被排除", () => {
    const orders = [order(1, "初一数学", "民兴南苑")];
    const f = setup(orders);
    f.selectedCity.value = "成都市";
    // fuzzy_address 无任何城市线索 → 未标注城市 → 无中心坐标兜底 → 排除
    expect(f.filteredOrders.value).toHaveLength(0);
  });

  it("无城市地址按坐标半径兜底（中心 50km 内保留）", () => {
    const orders = [order(1, "初一数学", "民兴南苑", 104.1, 30.66)];
    const f = setup(orders);
    f.selectedCity.value = "成都市";
    f.selectedCityCenter.value = [104.06, 30.65];
    expect(f.filteredOrders.value).toHaveLength(1);

    // 远坐标（模拟外地无标注单）超出半径被排除
    const far = setup([order(2, "初一数学", "某小区", 116.4, 39.9)]);
    far.selectedCity.value = "成都市";
    far.selectedCityCenter.value = [104.06, 30.65];
    expect(far.filteredOrders.value).toHaveLength(0);
  });

  it("cityOptions 合并静态表与订单地址中出现的城市", () => {
    const orders = [order(1, "初一数学", "彭州市xx")];
    const f = setup(orders);
    // 彭州市来自订单地址（静态表之外的城市也能进候选）
    expect(f.cityOptions.value).toContain("彭州市");
    expect(f.cityOptions.value).not.toContain("未标注城市");
  });
});
