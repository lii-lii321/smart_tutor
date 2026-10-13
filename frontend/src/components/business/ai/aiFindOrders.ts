/**
 * AI 找单 · 展示口径单点：条件回显 chips、价格/距离文案。
 * 纯函数抽出便于单测锁定；视图层不得各自拼条件文案。
 */
import type { AiOrderItem, FindOrderConditions } from "@/api/ai";

/** 条件回显 → chips 文本，只列实际生效的键（后端已剔除未识别/未生效项）。
 *  anchor 双形态：带 radius_km 是距离锚点；不带是区域条件（本身就是一个 chip）。 */
export function conditionsChips(c: FindOrderConditions): string[] {
  const chips: string[] = [];
  if (c.subject) chips.push(c.subject);
  if (c.grade) chips.push(c.grade);
  if (c.min_base_price != null && c.max_base_price != null) {
    chips.push(`¥${c.min_base_price}~${c.max_base_price}/次`);
  } else if (c.min_base_price != null) {
    chips.push(`¥${c.min_base_price} 以上/次`);
  } else if (c.max_base_price != null) {
    chips.push(`¥${c.max_base_price} 以内/次`);
  }
  if (c.weekly_frequency != null) {
    chips.push(`每周 ${c.weekly_frequency} 次`);
  }
  if (c.anchor != null) {
    chips.push(c.radius_km != null ? `距「${c.anchor}」${c.radius_km}km` : c.anchor);
  } else if (c.radius_km != null) {
    chips.push(`${c.radius_km}km 内`);
  }
  return chips;
}

export function priceLabel(item: Pick<AiOrderItem, "base_price" | "needs_manual_price">): string {
  if (item.needs_manual_price) return "待定价";
  return `¥${item.base_price}/次`;
}

export function formatDistance(km: number | null | undefined): string | null {
  return km == null ? null : `${km} km`;
}
