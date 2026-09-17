<script setup lang="ts">
/** 收到的评价弹层（自 Profile.vue 拆出）：评分列表 + 均分。 */
import { ref, watch } from "vue";
import { applicationsApi } from "@/api/applications";
import { showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const reviewsLoading = ref(false);
const reviews = ref<{ id: number; order_id: number; rating: number; comment?: string | null; created_at: string }[]>([]);
const reviewsAvg = ref<number | null>(null);

watch(
  show,
  async (visible) => {
    if (!visible) return;
    reviewsLoading.value = true;
    try {
      // 后端已按页返回：循环取完所有页（硬上限 500 条，防御老账号数据膨胀）
      reviews.value = await fetchAllReviews();
      reviewsAvg.value = reviews.value.length
        ? Math.round((reviews.value.reduce((s, r) => s + r.rating, 0) / reviews.value.length) * 10) / 10
        : null;
    } catch {
      showToast("评价加载失败");
    } finally {
      reviewsLoading.value = false;
    }
  },
  { immediate: true }
);

const PAGE_SIZE = 50;
const MAX_REVIEWS = 500;

async function fetchAllReviews(): Promise<typeof reviews.value> {
  const all: typeof reviews.value = [];
  for (let page = 1; all.length < MAX_REVIEWS; page++) {
    const batch = await applicationsApi.myReviews(page, PAGE_SIZE);
    all.push(...batch);
    if (batch.length < PAGE_SIZE) break;
  }
  return all.slice(0, MAX_REVIEWS);
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
    <div class="flex max-h-[75vh] flex-col p-4">
      <div class="mb-3 flex items-center justify-between">
        <div class="text-base font-semibold text-slate-950">收到的评价</div>
        <span v-if="reviewsAvg != null" class="text-sm text-amber-600">
          均分 {{ reviewsAvg }} ★
        </span>
      </div>
      <div class="overflow-y-auto">
        <div v-if="reviewsLoading" class="flex justify-center py-8">
          <van-loading type="spinner" color="#2563eb" />
        </div>
        <div v-else-if="reviews.length === 0" class="py-8 text-center text-sm text-slate-400">
          暂无评价。完成订单后，中介的评价会在这里展示。
        </div>
        <div v-else class="space-y-3 pb-4">
          <article
            v-for="item in reviews"
            :key="item.id"
            class="rounded-lg border border-slate-100 p-3"
          >
            <div class="flex items-center justify-between">
              <van-rate :model-value="item.rating" readonly :size="14" color="#f59e0b" />
              <span class="text-xs text-slate-400">订单 #{{ item.order_id }}</span>
            </div>
            <p v-if="item.comment" class="mt-2 text-sm leading-5 text-slate-600">{{ item.comment }}</p>
            <div class="mt-1 text-xs text-slate-400">
              {{ new Date(item.created_at).toLocaleString("zh-CN") }}
            </div>
          </article>
        </div>
      </div>
    </div>
  </van-popup>
</template>
