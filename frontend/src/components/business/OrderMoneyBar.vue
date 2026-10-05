<script setup lang="ts">
/**
 * 订单资金条：单价（课酬）主位 + 信息费次行。
 *
 *  层级口径（2026-09-29 拍板）：单价是教员赚的钱，是投递决策的第一变量，
 *  占大字主位；信息费是教员付的钱，保留在次行但只用中量强调，
 *  不与课酬争视觉。自带价订单无单价，主位回退"报价后计算"。
 *
 *  数据全部来自后端字段（price_total / calculated_info_fee / deposit_amount /
 *  balance_amount / needs_manual_price），不自算、不估算。
 */
import { computed } from "vue";
import OrderRiskBadge from "@/components/business/OrderRiskBadge.vue";

const props = withDefaults(
  defineProps<{
    /** 单价展示串（price_total 原文，如"80元/小时"）；缺省或自带价时主位回退 */
    unitPrice?: string;
    infoFee: number;
    deposit: number;
    balance: number;
    /** 自带价订单：服务端金额置零，投递时由教员报价才精算 */
    needsManualPrice?: boolean;
    alreadyApplied?: boolean;
    /** 已投递态整体弱化，金额不再是当前决策点 */
    muted?: boolean;
  }>(),
  { unitPrice: "", needsManualPrice: false, alreadyApplied: false, muted: false },
);

/** 自带价或服务端金额异常时不给一个醒目的 ¥0，避免误读成"这单不赚钱" */
const hasFee = computed(() => !props.needsManualPrice && Number(props.infoFee) > 0);
const hasUnit = computed(() => !props.needsManualPrice && !!props.unitPrice?.trim());

/** 超长单价串（解析原文可能带"211/70/小时 985/80/小时"这类多段报价）降一档，避免挤压动作按钮 */
const leadBig = computed(() => (hasUnit.value ? props.unitPrice!.trim().length <= 8 : hasFee.value));

const leadText = computed(() => {
  if (hasUnit.value) return props.unitPrice!.trim();
  if (hasFee.value) return `¥${props.infoFee}`;
  return props.needsManualPrice ? "报价后计算" : "以投递时报价为准";
});
</script>

<template>
  <div class="mt-3 border-t border-default pt-3" :class="muted ? 'opacity-70' : ''">
    <div class="flex items-end justify-between gap-3">
      <div class="min-w-0">
        <div class="text-caption leading-4 text-muted">{{ hasUnit ? "课酬" : "信息费" }}</div>
        <div
          class="price-highlight truncate font-bold leading-tight tracking-tight text-primary"
          :class="leadBig ? 'text-display' : 'text-emphasis'"
        >
          {{ leadText }}
        </div>
      </div>
      <div class="shrink-0">
        <slot name="action" />
      </div>
    </div>

    <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-caption leading-4 text-muted">
      <template v-if="hasFee">
        <span>信息费 <span class="font-semibold text-secondary">¥{{ infoFee }}</span></span>
        <span aria-hidden="true">·</span>
        <span>定金 ¥{{ deposit }} + 尾款 ¥{{ balance }}</span>
      </template>
      <span v-else-if="needsManualPrice">投递时填写你的期望课酬</span>
      <span v-else>中介确认后按平台费率精算</span>
      <OrderRiskBadge
        :needs-manual-price="needsManualPrice"
        :already-applied="alreadyApplied"
      />
    </div>
  </div>
</template>
