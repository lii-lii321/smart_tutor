/**
 * AI 找单展示口径测试：条件回显 chips、价格/距离文案、结果卡片渲染与点击契约。
 */
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import type { AiOrderItem, FindOrderConditions } from "@/api/ai";
import AiFindOrderCard from "@/components/business/ai/AiFindOrderCard.vue";
import { conditionsChips, formatDistance, priceLabel } from "@/components/business/ai/aiFindOrders";

function makeItem(overrides: Partial<AiOrderItem> = {}): AiOrderItem {
  return {
    id: 42,
    raw_id: "A1",
    grade_subject: "初三数学",
    price_total: "200/次",
    base_price: 200,
    fuzzy_address: "成都市武侯区",
    status: "recruiting",
    needs_manual_price: false,
    calculated_info_fee: 200,
    deposit_amount: 100,
    balance_amount: 100,
    weekly_frequency: 2,
    lng: 104.06,
    lat: 30.66,
    created_at: "2026-10-12T10:00:00",
    expired_at: "2026-10-20T10:00:00",
    distance_km: null,
    ...overrides,
  };
}

describe("conditionsChips 条件回显", () => {
  it("全部条件生效时逐项成 chip", () => {
    const chips = conditionsChips({
      subject: "数学",
      grade: "初中",
      min_base_price: 160,
      radius_km: 10,
      anchor: "武侯区",
    });
    expect(chips).toEqual(["数学", "初中", "¥160 以上/次", "距「武侯区」10km"]);
  });

  it("价格区间合并展示", () => {
    const chips = conditionsChips({ min_base_price: 100, max_base_price: 200 });
    expect(chips).toEqual(["¥100~200/次"]);
  });

  it("只有上限时展示「以内」", () => {
    expect(conditionsChips({ max_base_price: 200 })).toEqual(["¥200 以内/次"]);
  });

  it("无锚点时半径不带地名", () => {
    expect(conditionsChips({ radius_km: 5 })).toEqual(["5km 内"]);
  });

  it("空条件返回空数组", () => {
    expect(conditionsChips({} as FindOrderConditions)).toEqual([]);
  });

  it("频次与区域（无半径）各自成 chip", () => {
    const chips = conditionsChips({
      subject: "英语",
      grade: "高中",
      max_base_price: 200,
      weekly_frequency: 3,
      anchor: "武侯区",
    });
    expect(chips).toEqual(["英语", "高中", "¥200 以内/次", "每周 3 次", "武侯区"]);
  });
});

describe("价格与距离文案", () => {
  it("待定价单不走 ¥0 展示", () => {
    expect(priceLabel({ base_price: 0, needs_manual_price: true })).toBe("待定价");
    expect(priceLabel({ base_price: 200, needs_manual_price: false })).toBe("¥200/次");
  });

  it("距离为 null 不展示，有值带单位", () => {
    expect(formatDistance(null)).toBeNull();
    expect(formatDistance(1.2)).toBe("1.2 km");
  });
});

describe("AiFindOrderCard", () => {
  it("渲染科目、状态文案、距离 chip 与价格", () => {
    const wrapper = mount(AiFindOrderCard, {
      props: { item: makeItem({ distance_km: 1.2 }) },
    });
    expect(wrapper.text()).toContain("初三数学");
    expect(wrapper.text()).toContain("招聘中");
    expect(wrapper.text()).toContain("1.2 km");
    expect(wrapper.text()).toContain("¥200/次");
  });

  it("待定价单用警示口径展示", () => {
    const wrapper = mount(AiFindOrderCard, {
      props: { item: makeItem({ base_price: 0, needs_manual_price: true }) },
    });
    expect(wrapper.text()).toContain("待定价");
  });

  it("点击卡片发出 open 事件并携带订单 id", async () => {
    const wrapper = mount(AiFindOrderCard, { props: { item: makeItem() } });
    await wrapper.find("article").trigger("click");
    expect(wrapper.emitted("open")?.[0]).toEqual([42]);
  });
});
