<script setup lang="ts">
import { computed } from "vue";
import type { OrderStatus } from "@/api/types";
import { ORDER_STATUS_COLORS, ORDER_STATUS_LABELS } from "@/constants/orderStatus";

const props = defineProps<{ status: OrderStatus }>();

const label = computed(() => ORDER_STATUS_LABELS[props.status]);
const colorClass = computed(() => ORDER_STATUS_COLORS[props.status]);
</script>

<template>
  <!-- 订单状态徽标的唯一视觉口径：颜色/文案只从 orderStatus.ts 读取，
       各页面禁止再各自手写状态配色 -->
  <span
    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1"
    :class="colorClass"
  >
    {{ label }}
  </span>
</template>
