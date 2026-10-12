<script setup lang="ts">
/**
 * AI 找单结果卡片：只展示列表口径字段 + 距离，点击进入订单工作区。
 * 状态文案/配色走 constants/orderStatus 唯一口径，本组件不自造颜色。
 */
import { computed } from "vue";

import type { AiOrderItem } from "@/api/ai";
import type { OrderStatus } from "@/api/types";
import { ORDER_STATUS_COLORS, ORDER_STATUS_LABELS } from "@/constants/orderStatus";
import { formatDistance, priceLabel } from "./aiFindOrders";

const props = defineProps<{ item: AiOrderItem }>();

defineEmits<{ (e: "open", id: number): void }>();

const statusText = computed(
  () => ORDER_STATUS_LABELS[props.item.status as OrderStatus] ?? props.item.status,
);
const statusCls = computed(() => ORDER_STATUS_COLORS[props.item.status as OrderStatus] ?? "");
const distanceText = computed(() => formatDistance(props.item.distance_km));
const createdText = computed(() => (props.item.created_at ?? "").slice(0, 10));
</script>

<template>
  <article
    class="cursor-pointer rounded-xl border border-default bg-white transition-colors hover:bg-surface-soft/60"
    @click="$emit('open', item.id)"
  >
    <div class="flex items-start gap-3 px-4 py-3">
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm font-semibold text-primary">{{ item.grade_subject }}</span>
          <span
            class="rounded-full px-1.5 py-0.5 text-caption font-medium"
            :class="statusCls"
          >
            {{ statusText }}
          </span>
          <span
            v-if="distanceText"
            class="rounded-full bg-ai-soft px-1.5 py-0.5 text-caption font-medium text-ai-deep"
          >
            {{ distanceText }}
          </span>
        </div>
        <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-secondary">
          <span class="truncate">{{ item.fuzzy_address }}</span>
          <span v-if="item.weekly_frequency">每周 {{ item.weekly_frequency }} 次</span>
          <span v-if="createdText">发布于 {{ createdText }}</span>
        </div>
      </div>
      <div class="shrink-0 text-right">
        <div
          class="text-sm font-semibold"
          :class="item.needs_manual_price ? 'text-warning-deep' : 'text-primary'"
        >
          {{ priceLabel(item) }}
        </div>
        <div class="mt-0.5 text-caption text-muted">{{ item.price_total }}</div>
      </div>
    </div>
  </article>
</template>
