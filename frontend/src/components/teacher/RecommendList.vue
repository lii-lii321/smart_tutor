<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { TeacherOrderRecommendationItem } from "@/api/types";
import AppButton from "@/components/ui/AppButton.vue";
import RecommendationExplainCard from "@/components/business/RecommendationExplainCard.vue";
import { buildRecommendationExplanation } from "@/components/business/recommendation";

/**
 * 为你推荐抽屉（自 Board.vue 拆出，P1-1）：
 * 展开/收起、窗口轮换（首条固定 + 换一批）、未登录/拉黑/空态各分支。
 * 地图定位（focus）与投递跳转（go-order）交回父级处理。
 */
const props = defineProps<{
  items: TeacherOrderRecommendationItem[];
  loading: boolean;
  blocked: boolean;
  blockReason: string;
  loggedIn: boolean;
  expanded: boolean;
}>();

const emit = defineEmits<{
  (e: "update:expanded", value: boolean): void;
  (e: "focus", order: TeacherOrderRecommendationItem): void;
  (e: "go-order", order: TeacherOrderRecommendationItem): void;
  (e: "login"): void;
}>();

// 推荐窗口：常驻展示前 3 个最高匹配；「换一批」固定第 1 名，仅轮换后两位
const RECOMMENDATION_WINDOW = 3;
const recOffset = ref(0);

// 新一批推荐载入/清空时归零轮换偏移
watch(
  () => props.items,
  () => {
    recOffset.value = 0;
  }
);

const visibleRecommendations = computed(() => {
  const pool = props.items;
  if (pool.length === 0) return [];
  const [first, ...rest] = pool;
  if (rest.length === 0) return [first];
  const picks: TeacherOrderRecommendationItem[] = [];
  const span = Math.min(RECOMMENDATION_WINDOW - 1, rest.length);
  for (let i = 0; i < span; i++) {
    picks.push(rest[(recOffset.value + i) % rest.length]);
  }
  return [first, ...picks];
});

function shuffleRecommendations() {
  const restCount = props.items.length - 1;
  if (restCount <= RECOMMENDATION_WINDOW - 1) return;
  recOffset.value = (recOffset.value + RECOMMENDATION_WINDOW - 1) % restCount;
}

function toggleExpanded() {
  emit("update:expanded", !props.expanded);
}

// 推荐解释（H1）：score_breakdown/reasons 经适配器映射，缺失返回 null（不渲染入口）。
// 展开态按订单 id 记录；整卡可点，入口按钮需 stop 防误触 focus
const explainedIds = ref<Set<number>>(new Set());

function explanationOf(item: TeacherOrderRecommendationItem) {
  return buildRecommendationExplanation(item);
}

function toggleExplain(id: number) {
  const next = new Set(explainedIds.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  explainedIds.value = next;
}
</script>

<template>
  <section class="recommendation-drawer fixed bottom-[72px] left-0 right-0 z-20 px-2">
    <div class="recommendation-handle mb-1 flex items-center justify-between rounded-xl bg-white px-3 py-1 shadow-lg" @click="toggleExpanded">
      <button class="flex min-w-0 items-center gap-2 text-left" aria-label="展开或收起推荐订单">
        <van-icon :name="expanded ? 'arrow-down' : 'arrow-up'" size="16" color="var(--st-brand-800)" />
        <h2 class="text-emphasis font-bold text-primary">为你推荐</h2>
        <span v-if="items.length" class="text-caption text-muted">前 {{ visibleRecommendations.length }} 条 · 共 {{ items.length }} 条匹配</span>
      </button>
      <button
        v-if="items.length > RECOMMENDATION_WINDOW"
        class="flex items-center gap-1 text-caption text-brand-800"
        @click.stop="shuffleRecommendations"
      >
        <van-icon name="replay" size="13" />
        换一批
      </button>
    </div>

    <div v-if="expanded && !loggedIn" class="st-card p-5 text-center">
      <p class="text-sm text-muted">登录后按你的画像（科目/年级/距离/院校）智能推荐订单</p>
      <AppButton size="md" class="mt-3" @click="emit('login')">
        登录查看推荐
      </AppButton>
    </div>

    <div v-else-if="expanded && loading" class="st-card p-4">
      <van-skeleton title :row="2" title-width="55%" row-width="85%" />
    </div>

    <div
      v-else-if="expanded && blocked"
      class="rounded-2xl border border-warning-mid bg-warning-soft p-5 text-center text-sm text-warning-deep shadow-sm"
    >
      <van-icon name="warning-o" class="mb-1" size="20" />
      <div>{{ blockReason }}</div>
      <div class="mt-1 text-xs text-warning-deep/80">如有疑问请联系对应中介沟通。</div>
    </div>

    <div v-else-if="expanded && items.length === 0" class="st-card p-5 text-center text-sm text-muted">
      暂无推荐订单，可筛选后在地图上直接浏览点位
    </div>

    <div v-else-if="expanded" class="recommendation-list max-h-[54vh] space-y-3 overflow-y-auto pb-2">
      <div
        v-for="item in visibleRecommendations"
        :key="item.id"
        class="st-card st-card--interactive cursor-pointer p-4"
        @click="emit('focus', item)"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="min-w-0">
            <span class="font-semibold text-primary">{{ item.grade_subject }}</span>
            <span class="ml-2 text-xs font-medium text-brand-800">{{ item.price_total }}</span>
          </div>
          <span
            class="shrink-0 rounded-full bg-surface-soft px-2.5 py-1 text-xs font-semibold text-secondary"
            title="匹配分为科目/年级/距离/院校/课酬/历史表现的加权得分"
          >
            匹配 {{ item.total_score }}%
          </span>
        </div>

        <div class="mt-2 space-y-1 text-xs text-secondary">
          <div>
            {{ item.fuzzy_address }}
            <template v-if="item.distance_km != null"> · 距你约 <span class="font-semibold text-primary">{{ item.distance_km }}km</span></template>
          </div>
          <!-- 推荐解释：与 TeacherOrderCard 同一入口范式（折叠 + compact 卡）；
               适配器返回 null（缺 score_breakdown）时回落到原文摘要行 -->
          <template v-if="explanationOf(item)">
            <button
              class="flex w-full items-center gap-1.5 rounded-lg bg-ai-soft/50 px-2.5 py-1.5 text-caption font-medium text-ai-deep"
              @click.stop="toggleExplain(item.id)"
            >
              <van-icon name="bulb-o" size="12" />
              为什么推荐给你？
              <van-icon :name="explainedIds.has(item.id) ? 'arrow-up' : 'arrow-down'" size="11" class="ml-auto" />
            </button>
            <div v-if="explainedIds.has(item.id)" class="mt-2" @click.stop>
              <RecommendationExplainCard :explanation="explanationOf(item)!" compact />
            </div>
          </template>
          <template v-else>
            <div v-if="item.reasons?.length" class="text-muted">
              {{ item.reasons.slice(0, 2).join(" · ") }}
            </div>
            <div v-if="item.score_breakdown" class="text-caption text-muted">
              科目 {{ item.score_breakdown.subject }} · 年级 {{ item.score_breakdown.grade }} · 距离 {{ item.score_breakdown.distance }}
            </div>
          </template>
        </div>

        <div class="relative mt-3 min-h-12 border-t border-default pt-3">
          <div class="pr-20 text-sm leading-5 text-secondary">
            <template v-if="item.needs_manual_price">自带价 · 报价后可算</template>
            <template v-else>
              信息费
              <span class="font-semibold text-secondary">¥{{ item.calculated_info_fee }}</span>
              <span class="text-xs text-muted">
                （定金¥{{ item.deposit_amount }} + 尾款¥{{ item.balance_amount }}）
              </span>
            </template>
          </div>
          <AppButton
            size="sm"
            class="absolute bottom-0 right-0"
            :variant="item.already_applied ? 'secondary' : 'primary'"
            :disabled="item.already_applied"
            @click.stop="emit('go-order', item)"
          >
            {{ item.already_applied ? "已投递" : "去投递" }}
          </AppButton>
        </div>
      </div>
    </div>
  </section>
</template>
