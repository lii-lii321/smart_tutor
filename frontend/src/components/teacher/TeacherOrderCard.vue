<script setup lang="ts">
import { computed, ref } from "vue";
import type { PublicOrderBrief, TeacherOrderRecommendationItem } from "@/api/types";
import AppBadge from "@/components/ui/AppBadge.vue";
import AppCard from "@/components/ui/AppCard.vue";
import OrderMoneyBar from "@/components/business/OrderMoneyBar.vue";
import RecommendationExplainCard from "@/components/business/RecommendationExplainCard.vue";
import { buildRecommendationExplanation } from "@/components/business/recommendation";

const props = withDefaults(
  defineProps<{
    order: PublicOrderBrief;
    /** 传入推荐装饰（匹配分/距离/理由/信息费）时按推荐卡渲染，否则按公共订单卡渲染 */
    recommendation?: TeacherOrderRecommendationItem | null;
  }>(),
  { recommendation: null },
);

defineEmits<{
  (e: "open", order: PublicOrderBrief): void;
  (e: "apply", order: TeacherOrderRecommendationItem): void;
}>();

const rec = computed(() => props.recommendation);

// 推荐解释（Batch 02）：score_breakdown/reasons 原文经适配器映射，数据缺失返回 null
const explanation = computed(() => buildRecommendationExplanation(rec.value));
const explainExpanded = ref(false);

const frequencyText = computed(() => {
  const count = Number(props.order.weekly_frequency || 0);
  return count > 0 ? `每周 ${count} 次` : "";
});
</script>

<template>
  <!-- 教员端订单卡唯一口径：推荐卡（带匹配装饰）与橱窗公共卡共用一套视觉 -->
  <AppCard interactive padding="md" @click="$emit('open', order)">
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <h3 class="truncate text-[15px] font-bold text-primary">
          {{ order.grade_subject }}
        </h3>
        <p class="mt-0.5 truncate text-[11px] text-muted">
          <!-- 橱窗公共接口刻意不下发 raw_id（脱敏），只有推荐卡有，条件渲染避免孤立 # -->
          <template v-if="order.raw_id"><span class="mono">#{{ order.raw_id }}</span></template>
          <template v-if="order.raw_id && order.price_total"> · </template>
          <template v-if="order.price_total">{{ order.price_total }}</template>
        </p>
      </div>
      <AppBadge v-if="rec" tone="ai" size="sm" dot>匹配 {{ rec.total_score }}%</AppBadge>
    </div>

    <div class="mt-1.5 flex items-center gap-1 text-xs text-muted">
      <van-icon name="location-o" size="12" />
      <span class="min-w-0 truncate">{{ order.fuzzy_address }}</span>
      <!-- 距离是仅次于信息费的决策因子，数值加粗从灰底行里提出来 -->
      <span v-if="rec?.distance_km != null" class="shrink-0">· 距你约 <span class="font-semibold text-secondary">{{ rec.distance_km }}km</span></span>
    </div>

    <div
      v-if="frequencyText || order.is_summer_vacation || order.subway_remark"
      class="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]"
    >
      <span v-if="frequencyText" class="rounded-full bg-surface-soft px-2 py-0.5 text-secondary">
        {{ frequencyText }}
      </span>
      <span v-if="order.is_summer_vacation" class="rounded-full bg-warning-soft px-2 py-0.5 text-warning">
        暑期
      </span>
      <span v-if="order.subway_remark" class="min-w-0 truncate rounded-full bg-surface-soft px-2 py-0.5 text-secondary">
        {{ order.subway_remark }}
      </span>
    </div>

    <!-- 推荐解释：ai-soft 面板头做入口，默认折叠；数据来自 score_breakdown/reasons，无数据不显示入口 -->
    <div v-if="explanation" class="mt-2.5">
      <button
        class="flex w-full items-center gap-1.5 rounded-lg bg-ai-soft/50 px-2.5 py-1.5 text-[11px] font-medium text-ai-deep"
        @click.stop="explainExpanded = !explainExpanded"
      >
        <van-icon name="bulb-o" size="12" />
        为什么推荐给你？
        <van-icon :name="explainExpanded ? 'arrow-up' : 'arrow-down'" size="11" class="ml-auto" />
      </button>
      <div v-if="explainExpanded" class="mt-2" @click.stop>
        <RecommendationExplainCard :explanation="explanation" compact />
      </div>
    </div>

    <!-- 资金条：信息费是教员投递与否的唯一决策点，提到视觉主位。
         推荐卡与公共卡共用一套金额与风险表达，差别只在右侧动作。 -->
    <OrderMoneyBar
      :info-fee="order.calculated_info_fee"
      :deposit="order.deposit_amount"
      :balance="order.balance_amount"
      :needs-manual-price="order.needs_manual_price"
      :already-applied="rec?.already_applied ?? false"
      :muted="rec?.already_applied ?? false"
    >
      <template #action>
        <button
          v-if="rec"
          class="rounded-lg border px-3 py-1.5 text-[11px] font-semibold"
          :class="
            rec.already_applied
              ? 'border-transparent bg-surface-soft text-muted'
              : 'bg-brand-800 text-white'
          "
          :disabled="rec.already_applied"
          @click.stop="$emit('apply', rec)"
        >
          {{ rec.already_applied ? "已投递" : rec.needs_manual_price ? "去报价" : "去投递" }}
        </button>
        <span v-else class="text-xs font-medium text-brand-800">
          查看详情
          <van-icon name="arrow" size="12" class="ml-0.5" />
        </span>
      </template>
    </OrderMoneyBar>
  </AppCard>
</template>
