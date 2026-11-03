<script setup lang="ts">
import type { LiteOrderItem } from "@/lite/composables/useLiteBoard";

defineProps<{ order: LiteOrderItem }>();

const emit = defineEmits<{ (e: "select", order: LiteOrderItem): void }>();

function priceLabel(order: LiteOrderItem) {
  if (order.needs_manual_price) return "自带价";
  const unit = String(order.price_total || "").includes("小时") ? "小时" : "次";
  return `¥${Number(order.base_price)}/${unit}`;
}
</script>

<template>
  <button
    type="button"
    class="block w-full rounded-2xl border border-default bg-surface p-3 text-left transition-colors active:bg-surface-soft"
    @click="emit('select', order)"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <p class="truncate text-sm font-medium text-ink">{{ order.grade_subject }}</p>
        <p class="mt-0.5 truncate text-xs text-muted">
          {{ order.fuzzy_address }}<template v-if="order.subway_remark"> · {{ order.subway_remark }}</template>
        </p>
      </div>
      <div class="flex-none text-right">
        <p class="text-sm font-semibold text-accent" :class="{ 'text-secondary': order.needs_manual_price }">
          {{ priceLabel(order) }}
        </p>
        <p class="mt-0.5 text-[11px] text-muted">
          {{ order.distance_km != null ? `${order.distance_km}km` : `每周${order.weekly_frequency}次` }}
        </p>
      </div>
    </div>
    <div class="mt-2 flex items-center gap-1.5 text-[11px] text-secondary">
      <span class="rounded-full bg-surface-soft px-2 py-0.5">信息费 ¥{{ Number(order.calculated_info_fee) }}</span>
      <span class="rounded-full bg-surface-soft px-2 py-0.5">定金 ¥{{ Number(order.deposit_amount) }}</span>
      <span class="rounded-full bg-surface-soft px-2 py-0.5">尾款 ¥{{ Number(order.balance_amount) }}</span>
    </div>
  </button>
</template>
