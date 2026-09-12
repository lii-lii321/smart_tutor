<script setup lang="ts">
import { computed, ref, watch } from "vue";

/**
 * 为你推荐抽屉（自 Board.vue 拆出，P1-1）：
 * 展开/收起、窗口轮换（首条固定 + 换一批）、未登录/拉黑/空态各分支。
 * 地图定位（focus）与投递跳转（go-order）交回父级处理。
 */
const props = defineProps<{
  items: any[];
  loading: boolean;
  blocked: boolean;
  blockReason: string;
  loggedIn: boolean;
  expanded: boolean;
}>();

const emit = defineEmits<{
  (e: "update:expanded", value: boolean): void;
  (e: "focus", order: any): void;
  (e: "go-order", order: any): void;
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
  const picks: any[] = [];
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
</script>

<template>
  <section class="recommendation-drawer fixed bottom-[72px] left-0 right-0 z-20 px-2">
    <div class="recommendation-handle mb-1 flex items-center justify-between rounded-xl bg-white/95 px-3 py-1 shadow-lg backdrop-blur" @click="toggleExpanded">
      <button class="flex min-w-0 items-center gap-2 text-left" aria-label="展开或收起推荐订单">
        <van-icon :name="expanded ? 'arrow-down' : 'arrow-up'" size="16" color="#1e3558" />
        <h2 class="text-[15px] font-bold text-slate-900">为你推荐</h2>
        <span v-if="items.length" class="text-[11px] text-slate-400">前 {{ visibleRecommendations.length }} 条 · 共 {{ items.length }} 条匹配</span>
      </button>
      <button
        v-if="items.length > RECOMMENDATION_WINDOW"
        class="flex items-center gap-1 text-[11px] text-primary-600"
        @click.stop="shuffleRecommendations"
      >
        <van-icon name="replay" size="13" />
        换一批
      </button>
    </div>

    <div v-if="expanded && !loggedIn" class="rounded-2xl bg-white p-5 text-center shadow-sm">
      <p class="text-sm text-slate-400">登录后按你的画像（科目/年级/距离/院校）智能推荐订单</p>
      <button
        class="mt-3 rounded-xl bg-blue-600 px-6 py-2 text-sm font-semibold text-white"
        @click="emit('login')"
      >
        登录查看推荐
      </button>
    </div>

    <div v-else-if="expanded && loading" class="rounded-2xl bg-white p-4 shadow-sm">
      <van-skeleton title :row="2" title-width="55%" row-width="85%" />
    </div>

    <div
      v-else-if="expanded && blocked"
      class="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-center text-sm text-amber-700 shadow-sm"
    >
      <van-icon name="warning-o" class="mb-1" size="20" />
      <div>{{ blockReason }}</div>
      <div class="mt-1 text-xs text-amber-600/80">如有疑问请联系对应中介沟通。</div>
    </div>

    <div v-else-if="expanded && items.length === 0" class="rounded-2xl bg-white p-5 text-center text-sm text-slate-400 shadow-sm">
      暂无推荐订单，去地图上看看
    </div>

    <div v-else-if="expanded" class="recommendation-list max-h-[54vh] space-y-3 overflow-y-auto pb-2">
      <div
        v-for="item in visibleRecommendations"
        :key="item.id"
        class="cursor-pointer rounded-2xl bg-white p-4 shadow-sm"
        @click="emit('focus', item)"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="min-w-0">
            <span class="font-semibold text-slate-900">{{ item.grade_subject }}</span>
            <span class="ml-2 text-xs font-medium text-primary-600">{{ item.price_total }}</span>
          </div>
          <span class="shrink-0 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-600">
            匹配 {{ item.total_score }}%
          </span>
        </div>

        <div class="mt-2 space-y-1 text-xs text-slate-500">
          <div>
            {{ item.fuzzy_address }}
            <template v-if="item.distance_km != null"> · 距你约 {{ item.distance_km }}km</template>
          </div>
          <div v-if="item.reasons?.length" class="text-slate-400">
            {{ item.reasons.slice(0, 2).join(" · ") }}
          </div>
          <div v-if="item.score_breakdown" class="text-[11px] text-slate-400">
            科目 {{ item.score_breakdown.subject }} · 年级 {{ item.score_breakdown.grade }} · 距离 {{ item.score_breakdown.distance }}
          </div>
        </div>

        <div class="relative mt-3 min-h-12 border-t border-slate-100 pt-3">
          <div class="pr-20 text-sm leading-5 text-slate-500">
            <template v-if="item.needs_manual_price">自带价 · 报价后可算</template>
            <template v-else>
              信息费
              <span class="font-bold text-primary-600">¥{{ item.calculated_info_fee }}</span>
              <span class="text-xs text-slate-400">
                （定金¥{{ item.deposit_amount }} + 尾款¥{{ item.balance_amount }}）
              </span>
            </template>
          </div>
          <button
            class="absolute bottom-0 right-0 rounded-lg px-3 py-1.5 text-[11px] font-semibold"
            :class="item.already_applied ? 'bg-gray-100 text-gray-400' : 'header-gradient text-white'"
            :disabled="item.already_applied"
            @click.stop="emit('go-order', item)"
          >
            {{ item.already_applied ? "已投递" : "去投递" }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
