<script setup lang="ts">
/** 收到的评价弹层（自 Profile.vue 拆出）：评分列表 + 均分 + 公开成绩单分享入口。 */
import { ref, watch } from "vue";
import { formatDateTime } from "@/utils/format";
import { applicationsApi } from "@/api/applications";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";
import AppButton from "@/components/ui/AppButton.vue";
import AppEmpty from "@/components/ui/AppEmpty.vue";

const show = defineModel<boolean>("show", { default: false });

const auth = useAuthStore();

const reviewsLoading = ref(false);
// 首屏失败必须与"暂无评价"可区分：reviews 初始为 []，错误态分支必须排在空态之前
const reviewsLoadError = ref(false);
const reviews = ref<{ id: number; order_id: number; rating: number; comment?: string | null; created_at: string }[]>([]);
const reviewsAvg = ref<number | null>(null);

// 只负责数据加载：重试按钮与弹层打开共用，不动任何业务逻辑
async function loadReviews() {
  reviewsLoading.value = true;
  reviewsLoadError.value = false;
  try {
    // 后端已按页返回：循环取完所有页（硬上限 500 条，防御老账号数据膨胀）
    reviews.value = await fetchAllReviews();
    reviewsAvg.value = reviews.value.length
      ? Math.round((reviews.value.reduce((s, r) => s + r.rating, 0) / reviews.value.length) * 10) / 10
      : null;
  } catch {
    reviewsLoadError.value = true;
    showToast("评价加载失败");
  } finally {
    reviewsLoading.value = false;
  }
}

watch(
  show,
  (visible) => {
    if (visible) loadReviews();
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
        <div class="text-base font-semibold text-primary">收到的评价</div>
        <span v-if="reviewsAvg != null" class="text-sm text-warning-deep">
          均分 {{ reviewsAvg }} ★
        </span>
      </div>
      <button
        v-if="reviews.length > 0"
        class="mb-3 w-full rounded-xl bg-surface-soft py-2 text-sm font-medium text-secondary"
        @click="shareScorecard"
      >
        生成可转发的成绩单（发给家长看） →
      </button>
      <div class="overflow-y-auto">
        <div v-if="reviewsLoading" class="flex justify-center py-8">
          <van-loading type="spinner" color="var(--st-text-secondary)" />
        </div>
        <div
          v-else-if="reviewsLoadError && reviews.length === 0"
          class="flex flex-col items-center justify-center px-6 py-12 text-center"
        >
          <van-icon name="warning-o" size="48" />
          <p class="mt-5 text-sm font-medium text-primary">评价加载失败</p>
          <p class="mt-1 text-xs leading-5 text-muted">网络或服务暂时不可用，重试不会影响已有评价</p>
          <div class="mt-6">
            <AppButton size="md" @click="loadReviews">重新加载</AppButton>
          </div>
        </div>
        <AppEmpty
          v-else-if="reviews.length === 0"
          icon="⭐"
          title="暂无评价"
          description="完成订单后，中介的评价会在这里展示"
        >
          <template #action>
            <AppButton size="lg" @click="shareScorecard">生成可转发的成绩单</AppButton>
          </template>
        </AppEmpty>
        <div v-else class="space-y-3 pb-4">
          <article
            v-for="item in reviews"
            :key="item.id"
            class="rounded-lg border border-default p-3"
          >
            <div class="flex items-center justify-between">
              <van-rate :model-value="item.rating" readonly :size="14" color="var(--st-accent-deep)" />
              <span class="text-xs text-muted">订单 #{{ item.order_id }}</span>
            </div>
            <p v-if="item.comment" class="mt-2 text-sm leading-5 text-secondary">{{ item.comment }}</p>
            <div class="mt-1 text-xs text-muted">
              {{ formatDateTime(item.created_at) }}
            </div>
          </article>
        </div>
      </div>
    </div>
  </van-popup>
</template>
