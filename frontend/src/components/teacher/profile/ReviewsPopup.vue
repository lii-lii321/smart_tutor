<script setup lang="ts">
/** 收到的评价弹层（自 Profile.vue 拆出）：评分列表 + 均分 + 公开成绩单分享入口。 */
import { ref, watch } from "vue";
import { applicationsApi } from "@/api/applications";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const auth = useAuthStore();

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

/** 公开成绩单分享：系统分享优先，退化复制链接（与成绩单页内分享同逻辑）。 */
async function shareScorecard() {
  const teacherId = auth.teacher?.id;
  if (!teacherId) return;
  const url = `${window.location.origin}/public/teacher/${teacherId}/scorecard`;
  if (navigator.share) {
    try {
      await navigator.share({ title: "我的家教成绩单", url });
      return;
    } catch {
      return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    showToast("成绩单链接已复制");
  } catch {
    showToast("复制失败，请手动复制");
  }
}

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
      <button
        v-if="reviews.length > 0"
        class="mb-3 w-full rounded-xl bg-blue-50 py-2 text-sm font-medium text-blue-600"
        @click="shareScorecard"
      >
        生成可转发的成绩单（发给家长看） →
      </button>
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
