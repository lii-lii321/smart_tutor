<script setup lang="ts">
/**
 * 教员公开成绩单（无需登录）：中介转发给家长的信任凭证。
 * 只读 + 脱敏（后端不露联系方式/全名）；顶部提供"复制链接/系统分享"。
 */
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { showToast } from "vant";
import { publicApi, type Scorecard } from "@/api/public";
import { getApiErrorMessage } from "@/utils/apiError";

const route = useRoute();
const scorecard = ref<Scorecard | null>(null);
const loading = ref(true);
const loadFailed = ref(false);

const teacherId = Number(route.params.id);

onMounted(async () => {
  if (!Number.isFinite(teacherId) || teacherId <= 0) {
    loadFailed.value = true;
    loading.value = false;
    return;
  }
  try {
    scorecard.value = await publicApi.scorecard(teacherId);
  } catch (e) {
    showToast(getApiErrorMessage(e, "成绩单加载失败"));
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
});

async function shareLink() {
  const url = window.location.href;
  const title = scorecard.value
    ? `【智派家教】${scorecard.value.display_name} · ${scorecard.value.school}`
    : "教员成绩单";
  // 优先系统分享（微信内/手机浏览器），退化复制链接
  if (navigator.share) {
    try {
      await navigator.share({ title, url });
      return;
    } catch {
      // 用户取消分享不提示
      return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    showToast("链接已复制，可粘贴给家长");
  } catch {
    showToast("复制失败，请手动复制地址栏链接");
  }
}

function stars(rating: number): string {
  return "★".repeat(Math.max(0, Math.min(5, rating))) + "☆".repeat(Math.max(0, 5 - rating));
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 mx-auto max-w-2xl">
    <div v-if="loading" class="flex justify-center py-20">
      <van-loading type="spinner" size="32" color="#2563eb" />
    </div>

    <div v-else-if="loadFailed || !scorecard" class="flex flex-col items-center py-20 text-slate-400">
      <van-icon name="info-o" size="48" />
      <p class="mt-4 text-sm">成绩单不存在或已失效</p>
    </div>

    <template v-else>
      <!-- 头部：身份卡 -->
      <div class="m-3 rounded-2xl bg-white p-5 shadow-sm">
        <div class="flex items-center justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-lg font-bold text-slate-900">{{ scorecard.display_name }}</span>
              <span
                v-for="tag in scorecard.tags"
                :key="tag"
                class="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-600"
              >{{ tag }}</span>
            </div>
            <div class="mt-1 text-sm text-slate-500">
              {{ scorecard.school }}<template v-if="scorecard.major"> · {{ scorecard.major }}</template><template v-if="scorecard.grade"> · {{ scorecard.grade }}</template>
            </div>
          </div>
          <div class="shrink-0 text-right">
            <div class="text-2xl font-bold text-amber-500">
              {{ scorecard.avg_rating != null ? scorecard.avg_rating.toFixed(1) : "—" }}
            </div>
            <div class="text-xs text-slate-400">综合评分</div>
          </div>
        </div>
        <button
          class="mt-4 w-full rounded-xl bg-blue-600 py-2.5 text-sm font-semibold text-white"
          @click="shareLink"
        >
          分享这份成绩单
        </button>
      </div>

      <!-- 经营事实三卡 -->
      <div class="mx-3 grid grid-cols-3 gap-2">
        <div class="rounded-xl bg-white p-3 text-center shadow-sm">
          <div class="text-xl font-bold text-emerald-600">{{ scorecard.completed_count }}</div>
          <div class="mt-0.5 text-xs text-slate-400">累计成交</div>
        </div>
        <div class="rounded-xl bg-white p-3 text-center shadow-sm">
          <div
            class="text-xl font-bold"
            :class="scorecard.violation_count > 0 ? 'text-red-500' : 'text-slate-700'"
          >{{ scorecard.violation_count }}</div>
          <div class="mt-0.5 text-xs text-slate-400">违约记录</div>
        </div>
        <div class="rounded-xl bg-white p-3 text-center shadow-sm">
          <div class="text-xl font-bold text-slate-700">{{ scorecard.review_count }}</div>
          <div class="mt-0.5 text-xs text-slate-400">家长/中介评价</div>
        </div>
      </div>

      <!-- 评价列表 -->
      <div class="m-3 rounded-2xl bg-white p-4 shadow-sm">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-slate-900">教学评价</h3>
          <span class="text-xs text-slate-400">来自成交订单（一单一评）</span>
        </div>
        <div v-if="scorecard.reviews.length === 0" class="py-8 text-center text-sm text-slate-400">
          暂无评价。成交订单越多，这里越能反映真实水平。
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="(review, index) in scorecard.reviews"
            :key="index"
            class="rounded-xl bg-slate-50 p-3"
          >
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium text-amber-500">{{ stars(review.rating) }}</span>
              <span
                v-if="review.grade_subject"
                class="text-xs text-slate-400"
              >{{ review.grade_subject }}</span>
            </div>
            <p v-if="review.comment" class="mt-1.5 text-sm leading-5 text-slate-600">
              {{ review.comment }}
            </p>
            <div v-if="review.created_at" class="mt-1.5 text-xs text-slate-400">
              {{ new Date(review.created_at).toLocaleDateString("zh-CN") }}
            </div>
          </div>
        </div>
      </div>

      <div class="px-4 pb-6 text-center text-xs leading-5 text-slate-400">
        本成绩单由智派家教平台生成，数据来自平台真实成交记录与评价。<br>
        联系方式受平台保护，如需联系该教员请联系对应中介。
      </div>
    </template>
  </div>
</template>
