/**
 * 相似订单迷你卡测试：相似度百分比、价格口径（待定价不显 ¥0）、点击契约。
 */
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import type { SimilarOrderItem } from "@/api/ai";
import AiSimilarOrderCard from "@/components/business/ai/AiSimilarOrderCard.vue";

function makeItem(overrides: Partial<SimilarOrderItem> = {}): SimilarOrderItem {
  return {
    id: 7,
    raw_id: "S1",
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
    similarity: 0.8734,
    ...overrides,
  };
}

function mountCard(item: SimilarOrderItem) {
  return mount(AiSimilarOrderCard, { props: { item } });
}

describe("AiSimilarOrderCard", () => {
  it("渲染科目、相似度百分比、地址与价格", () => {
    const wrapper = mountCard(makeItem());
    expect(wrapper.text()).toContain("初三数学");
    expect(wrapper.text()).toContain("相似 87%");
    expect(wrapper.text()).toContain("成都市武侯区");
    expect(wrapper.text()).toContain("¥200/次");
  });

  it("待定价单不显 ¥0", () => {
    const wrapper = mountCard(makeItem({ base_price: 0, needs_manual_price: true }));
    expect(wrapper.text()).toContain("待定价");
    expect(wrapper.text()).not.toContain("¥0");
  });

  it("点击发出 open 事件并携带订单 id", async () => {
    const wrapper = mountCard(makeItem({ id: 42 }));
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("open")?.[0]).toEqual([42]);
  });
});
