<script setup lang="ts">
/**
 * 订单风险徽标（Batch 03）：教员投递前最关心的第二件事 —— 这单的钱有风险吗。
 *
 * 三个状态来自后端字段，不是前端推断：
 *   already_applied  → 已投递（recommendation.already_applied）
 *   needs_manual_price → 自带价订单，投递时才知道金额（order.needs_manual_price）
 *   其余             → 定金由平台锁定，试课失败可按公式退款（产品说明 §2.3）
 *
 * 只表达"性质"，不表达金额；金额由 OrderMoneyBar 负责。
 * 视觉走 AppBadge 的语义色族，不新造颜色。
 */
import AppBadge from "@/components/ui/AppBadge.vue";

withDefaults(
  defineProps<{
    needsManualPrice?: boolean;
    alreadyApplied?: boolean;
  }>(),
  { needsManualPrice: false, alreadyApplied: false },
);
</script>

<template>
  <AppBadge v-if="alreadyApplied" tone="neutral" size="sm">已投递</AppBadge>
  <AppBadge v-else-if="needsManualPrice" tone="info" size="sm">需先报价</AppBadge>
  <AppBadge v-else tone="success" size="sm">试课失败可退</AppBadge>
</template>
