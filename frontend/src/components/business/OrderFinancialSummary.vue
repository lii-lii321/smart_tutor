<script setup lang="ts">
import AppCard from "@/components/ui/AppCard.vue";
import type { FinancialRow } from "./order/financialRows";

/**
 * 订单财务摘要（Batch 02 引入，Batch 04 起类型共享至 order/financialRows.ts）：
 * 纯展示组件——金额、状态、时间全部由页面经适配器从 API 字段组装后传入，
 * 组件内**禁止**出现任何金额计算或状态推导（规格书红线：前端不复算财务）。
 */

withDefaults(defineProps<{ rows: FinancialRow[]; title?: string }>(), {
  title: "资金状态",
});

const STATE_TEXT: Record<FinancialRow["state"], string> = {
  paid: "已付",
  pending: "待收",
  refunded: "已退",
  forfeited: "已没收",
};

const STATE_CLASS: Record<FinancialRow["state"], string> = {
  paid: "bg-success-soft text-success",
  pending: "bg-surface-soft text-secondary",
  refunded: "bg-warning-soft text-warning",
  forfeited: "bg-danger-soft text-danger",
};
</script>

<template>
  <AppCard padding="md">
    <h3 class="text-sm font-semibold text-primary">{{ title }}</h3>
    <div class="mt-3 divide-y divide-slate-100">
      <div
        v-for="row in rows"
        :key="row.key"
        class="flex items-center justify-between gap-3 py-2.5"
      >
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm text-secondary">{{ row.label }}</span>
            <span
              class="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
              :class="STATE_CLASS[row.state]"
            >
              {{ STATE_TEXT[row.state] }}
            </span>
          </div>
          <div v-if="row.time" class="mt-0.5 text-[11px] text-muted">{{ row.time }}</div>
        </div>
        <div class="price-highlight shrink-0 text-sm font-bold text-primary">{{ row.amount }}</div>
      </div>
    </div>
  </AppCard>
</template>
