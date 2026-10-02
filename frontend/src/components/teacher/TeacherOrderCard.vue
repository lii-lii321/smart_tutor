<script setup lang="ts">
import { computed, ref } from "vue";
import type { PublicOrderBrief, TeacherOrderRecommendationItem } from "@/api/types";
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

// 右上角新鲜度（UI 2.0 订单卡首行）：created_at 为唯一数据源，缺失不显示
const updatedLabel = computed(() => {
  const created = props.order.created_at;
  if (!created) return "";
  const t = new Date(created);
  if (Number.isNaN(t.getTime())) return "";
  const minutes = Math.floor((Date.now() - t.getTime()) / 60_000);
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `${minutes} 分钟前更新`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前更新`;
  const days = Math.floor(hours / 24);
  if (days <= 7) return `${days} 天前更新`;
  return `${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")} 更新`;
});
</script>

<template>
  <!-- 教员端订单卡唯一口径：推荐卡（带匹配装饰）与橱窗公共卡共用一套视觉。
       UI 2.0 重排：首行学科 chip + 推荐标 + 新鲜度，标题=频次，资金条仍居底部主位 -->
  <AppCard interactive padding="md" @click="$emit('open', order)">
    <div class="flex min-w-0 items-center gap-1.5">
      <span class="min-w-0 truncate rounded-full bg-info-soft px-2 py-0.5 text-[11px] font-semibold leading-4 text-info-deep">
        {{ order.grade_subject }}
      </span>
      <span v-if="rec" class="shrink-0 rounded-full bg-accent px-2 py-0.5 text-[11px] font-bold leading-4 text-ink">
        为你推荐
      </span>
      <span v-if="updatedLabel" class="ml-auto shrink-0 truncate text-[11px] text-muted">
        <span v-if="order.raw_id" class="mono mr-1">#{{ order.raw_id }}</span>{{ updatedLabel }}
      </span>
    </div>

    <h3 v-if="frequencyText" class="mt-1.5 truncate text-base font-semibold leading-5 text-primary">
      {{ frequencyText }}
    </h3>

    <div class="mt-1.5 flex items-center gap-1 text-xs text-muted">
      <van-icon name="location-o" size="12" />
      <span class="min-w-0 truncate">{{ order.fuzzy_address }}</span>
      <!-- 距离是仅次于信息费的决策因子，数值加粗从灰底行里提出来 -->
      <span v-if="rec?.distance_km != null" class="shrink-0">· 距你约 <span class="font-semibold text-secondary">{{ rec.distance_km }}km</span></span>
    </div>

    <div
      v-if="order.is_summer_vacation || order.subway_remark"
      class="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]"
    >
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

    <!-- 资金条：单价（课酬）主位、信息费次行——教员先看赚多少，再权衡付多少。
         推荐卡与公共卡共用一套金额与风险表达，差别只在右侧动作。 -->
    <OrderMoneyBar
      :unit-price="order.price_total"
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
          class="rounded-full px-3.5 py-1.5 text-[11px] font-semibold"
          :class="
            rec.already_applied
              ? 'border border-default bg-surface-soft text-muted'
              : 'bg-ink text-white'
          "
          :disabled="rec.already_applied"
          @click.stop="$emit('apply', rec)"
        >
          {{ rec.already_applied ? "已投递" : rec.needs_manual_price ? "去报价" : "去投递" }}
        </button>
        <span v-else class="text-xs font-medium text-ink">
          查看详情
          <van-icon name="arrow" size="12" class="ml-0.5" />
        </span>
      </template>
    </OrderMoneyBar>
  </AppCard>
</template>
