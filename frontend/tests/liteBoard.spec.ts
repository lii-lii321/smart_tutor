import { beforeEach, describe, expect, it } from "vitest";
import type { PublicOrderBrief } from "@/api/types";
import { nationwideRegions } from "@/data/regions";
import { clusterPriceRange } from "@/utils/amap";
import {
  decorateWithDistance,
  hasValidLocation,
  liteSortOptions,
  persistFilters,
  readPersistedFilters,
} from "@/lite/composables/useLiteBoard";

function briefOrder(id: number, lng: number, lat: number): PublicOrderBrief {
  return {
    id,
    raw_id: `LT-${id}`,
    grade_subject: "初三数学",
    price_total: "200/次",
    base_price: 200,
    calculated_info_fee: 400,
    deposit_amount: 100,
    balance_amount: 300,
    needs_manual_price: false,
    fuzzy_address: "成都市天府大道",
    subway_remark: null,
    lng,
    lat,
    weekly_frequency: 2,
    is_summer_vacation: false,
    expired_at: null,
    created_at: "2026-11-01T00:00:00",
  };
}

describe("decorateWithDistance", () => {
  it("参照点缺失时全部置 null（距离排序沉底，不报错）", () => {
    const result = decorateWithDistance([briefOrder(1, 104.06, 30.65)], null);
    expect(result).toHaveLength(1);
    expect(result[0].distance_km).toBeNull();
  });

  it("给出参照点时按 haversine 算距离并保留一位小数", () => {
    // 成都天府广场附近两点，直线距离约 1.1km（104.065,30.657 → 104.075,30.661）
    const [item] = decorateWithDistance([briefOrder(1, 104.065, 30.657)], [104.075, 30.661]);
    expect(item.distance_km).toBeGreaterThan(0.5);
    expect(item.distance_km).toBeLessThan(2.5);
    expect(Number.isInteger(item.distance_km * 10)).toBe(true);
  });

  it("非法坐标（0,0）置 null，不影响其他订单", () => {
    const result = decorateWithDistance(
      [briefOrder(1, 0, 0), briefOrder(2, 104.065, 30.657)],
      [104.075, 30.661],
    );
    expect(result[0].distance_km).toBeNull();
    expect(result[1].distance_km).not.toBeNull();
  });
});

describe("filter preference persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("无存储时返回 null", () => {
    expect(readPersistedFilters()).toBeNull();
  });

  it("合法 JSON 正常回读", () => {
    persistFilters({ stage: "junior", subjects: ["数学"], city: "成都市", sort: "distance" });
    expect(readPersistedFilters()).toEqual({
      stage: "junior",
      subjects: ["数学"],
      city: "成都市",
      sort: "distance",
    });
  });

  it("坏 JSON 丢弃回 null，不抛错", () => {
    localStorage.setItem("lite_filters_v1", "{broken json!");
    expect(readPersistedFilters()).toBeNull();
  });
});

describe("liteSortOptions", () => {
  it("免登录无「智能推荐」档（依赖登录推荐分）", () => {
    expect(liteSortOptions.map((o) => o.value)).toEqual(["distance", "price", "newest"]);
  });
});

describe("省市级联（先省份后市）", () => {
  it("静态省表覆盖 34 个省级行政区，每省城市非空", () => {
    expect(nationwideRegions.length).toBe(34);
    expect(nationwideRegions.every((r) => r.cities.length > 0)).toBe(true);
  });

  it("城市可反推所属省份（持久化恢复用）", () => {
    const find = (city: string) => nationwideRegions.find((r) => r.cities.includes(city))?.name;
    expect(find("成都市")).toBe("四川省");
    expect(find("北京市")).toBe("北京市"); // 直辖市自身即省级
    expect(find("不属于任何省的城市")).toBeUndefined();
  });
});

describe("clusterPriceRange（聚合气泡价格区间）", () => {
  it("空集/全自带价 → 自带价", () => {
    expect(clusterPriceRange([])).toBe("自带价");
    expect(clusterPriceRange([null, null])).toBe("自带价");
  });

  it("单价相同 → 单值", () => {
    expect(clusterPriceRange([200, 200, 200])).toBe("¥200");
  });

  it("区间 → 最低–最高", () => {
    expect(clusterPriceRange([80, 200, 150])).toBe("¥80–200");
  });

  it("自带价单不拉低区间", () => {
    expect(clusterPriceRange([null, 100, 300])).toBe("¥100–300");
  });
});

describe("hasValidLocation（地图上图钉口径）", () => {
  it("成都市区有效坐标通过", () => {
    expect(hasValidLocation(briefOrder(1, 104.065, 30.657))).toBe(true);
  });

  it("(0,0) 兜底值无效", () => {
    expect(hasValidLocation(briefOrder(2, 0, 0))).toBe(false);
  });

  it("境外/远海坐标无效（拖飞视野或掉海里）", () => {
    expect(hasValidLocation(briefOrder(3, 2.35, 48.85))).toBe(false); // 巴黎
    expect(hasValidLocation(briefOrder(4, 151.2, -33.87))).toBe(false); // 悉尼（纬度越界）
  });

  it("NaN/Infinity 无效", () => {
    expect(hasValidLocation(briefOrder(5, Number.NaN, 30.65))).toBe(false);
    expect(hasValidLocation(briefOrder(6, 104.06, Number.POSITIVE_INFINITY))).toBe(false);
  });
});
