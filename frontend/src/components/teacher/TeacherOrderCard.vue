<script setup lang="ts">
import { computed } from "vue";
import type { PublicOrderBrief, TeacherOrderRecommendationItem } from "@/api/types";
import AppBadge from "@/components/ui/AppBadge.vue";
import AppCard from "@/components/ui/AppCard.vue";

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

const frequencyText = computed(() => {
  const count = Number(props.order.weekly_frequency || 0);
  return count > 0 ? `每周 ${count} 次` : "";
});
</script>

<template>
  <!-- 教员端订单卡唯一口径：推荐卡（带匹配装饰）与橱窗公共卡共用一套视觉 -->
  <AppCard interactive padding="md" @click="$emit('open', order)">
    <div class="flex items-start justify-between gap-2">
      <h3 class="min-w-0 truncate text-[15px] font-bold text-ink">
        {{ order.grade_subject }}
      </h3>
      <AppBadge v-if="rec" tone="ai" size="sm" dot>匹配 {{ rec.total_score }}%</AppBadge>
      <span
        v-else
        class="price-highlight shrink-0 text-sm font-bold text-brand-800"
      >{{ order.price_total }}</span>
    </div>

    <div class="mt-1.5 flex items-center gap-1 text-xs text-muted">
      <van-icon name="location-o" size="12" />
      <span class="min-w-0 truncate">{{ order.fuzzy_address }}</span>
      <span v-if="rec?.distance_km != null" class="shrink-0">· 距你约 {{ rec.distance_km }}km</span>
    </div>

    <div
      v-if="frequencyText || order.is_summer_vacation || order.subway_remark || rec?.reasons?.length"
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
      <span v-if="rec?.reasons?.length" class="min-w-0 truncate text-muted">
        {{ rec.reasons.slice(0, 2).join(" · ") }}
      </span>
    </div>

    <!-- 推荐卡：信息费 + 投递动作 -->
    <div v-if="rec" class="relative mt-3 min-h-12 border-t border-default pt-3">
      <div class="pr-24 text-sm leading-5 text-secondary">
        <template v-if="rec.needs_manual_price">自带价 · 报价后可算</template>
        <template v-else>
          信息费
          <span class="price-highlight font-bold text-brand-800">¥{{ rec.calculated_info_fee }}</span>
          <span class="text-xs text-muted">（定金¥{{ rec.deposit_amount }} + 尾款¥{{ rec.balance_amount }}）</span>
        </template>
      </div>
      <button
        class="absolute bottom-0 right-0 rounded-lg px-3 py-1.5 text-[11px] font-semibold"
        :class="rec.already_applied ? 'bg-slate-100 text-slate-400' : 'bg-brand-800 text-white'"
        :disabled="rec.already_applied"
        @click.stop="$emit('apply', rec)"
      >
        {{ rec.already_applied ? "已投递" : "去投递" }}
      </button>
    </div>

    <!-- 公共卡：查看详情 -->
    <div v-else class="mt-3 flex items-center justify-end border-t border-default pt-2.5 text-xs font-medium text-brand-800">
      查看详情
      <van-icon name="arrow" size="12" class="ml-0.5" />
    </div>
  </AppCard>
</template>
