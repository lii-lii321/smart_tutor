<script setup lang="ts">
/**
 * 订单资金条（Batch 03）：把"能赚多少 / 要垫多少 / 有没有风险"提到视觉主位。
 *
 *  此前这块信息是正文里的一个行内 span，后面紧跟括号里的小字注释，
 *  和标签混在同一行，扫一眼根本抓不到 —— 而它恰恰是教员投递与否的唯一决策点。
 *  现在：信息费大字 → 定金/尾款拆分 → 风险徽标，三级递进。
 *
 *  数据全部来自后端字段（calculated_info_fee / deposit_amount / balance_amount /
 *  needs_manual_price），不自算、不估算。
 */
import { computed } from "vue";
import OrderRiskBadge from "@/components/business/OrderRiskBadge.vue";

const props = withDefaults(
  defineProps<{
    infoFee: number;
    deposit: number;
    balance: number;
    /** 自带价订单：服务端金额置零，投递时由教员报价才精算 */
    needsManualPrice?: boolean;
    alreadyApplied?: boolean;
    /** 已投递态整体弱化，金额不再是当前决策点 */
    muted?: boolean;
  }>(),
  { needsManualPrice: false, alreadyApplied: false, muted: false },
);

/** 自带价或服务端金额异常时不给一个醒目的 ¥0，避免误读成"这单不赚钱" */
const hasFee = computed(() => !props.needsManualPrice && Number(props.infoFee) > 0);
</script>

<template>
  <div class="mt-3 border-t border-default pt-3" :class="muted ? 'opacity-70' : ''">
    <div class="flex items-end justify-between gap-3">
      <div class="min-w-0">
        <div class="text-[11px] leading-4 text-muted">信息费</div>
        <div
          class="price-highlight font-bold leading-tight tracking-tight text-primary"
          :class="hasFee ? 'text-[22px]' : 'text-[15px]'"
        >
          <template v-if="hasFee">¥{{ infoFee }}</template>
          <template v-else-if="needsManualPrice">报价后计算</template>
          <template v-else>以投递时报价为准</template>
        </div>
      </div>
      <div class="shrink-0">
        <slot name="action" />
      </div>
    </div>

    <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[11px] leading-4 text-muted">
      <template v-if="hasFee">
        <span>定金 ¥{{ deposit }}</span>
        <span aria-hidden="true">+</span>
        <span>尾款 ¥{{ balance }}</span>
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
