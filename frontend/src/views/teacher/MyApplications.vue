<script setup lang="ts">
import { ref, onMounted } from "vue";
import { formatDateTime } from "@/utils/format";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRouter } from "vue-router";
import { applicationsApi } from "@/api/applications";
import type { ApplicationItem, ApplicationStatus } from "@/api/types";
import { APPLICATION_STATUS_LABELS } from "@/constants/applicationStatus";
import { tenantsApi } from "@/api/tenants";
import { useAsyncAction } from "@/composables/useAsyncAction";
import { usePagedList } from "@/composables/usePagedList";
import { appConfirm } from "@/composables/appConfirm";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { getLastInviteCode } from "@/utils/inviteCode";
import { showToast } from "vant";

const router = useRouter();
// 加载更多/去重/到底状态收敛到 usePagedList（后端按 applied_at 倒序返回）
const PAGE_SIZE = 20;
const pagedList = usePagedList<ApplicationItem>(
  (page, pageSize) =>
    applicationsApi.listMine(page, pageSize).then((list) => ({ items: list })),
  { pageSize: PAGE_SIZE }
);
const { items: applications, loading, hasMore, load, loadMore } = pagedList;
// 被中介拉黑记录（教员可见性提示）
const blacklistRecords = ref<{ tenant_name: string; reason?: string | null }[]>([]);

function goBoard() {
  router.push(`/teacher/board/${getLastInviteCode()}`);
}

onMounted(async () => {
  await Promise.all([refresh(), loadBlacklistStatus()]);
});

async function loadBlacklistStatus() {
  try {
    blacklistRecords.value = await tenantsApi.myBlacklistStatus();
  } catch {
    blacklistRecords.value = [];
  }
}

// usePagedList 把异常抛给调用方，由视图决定 toast 文案
async function refresh() {
  try {
    await load();
  } catch {
    showToast("加载失败");
  }
}

async function loadMoreSafe() {
  try {
    await loadMore();
  } catch {
    showToast("加载失败");
  }
}

const [handleCancel, cancelling] = useAsyncAction(async (app: ApplicationItem) => {
  const isDepositPaid = app.status === "deposit_paid";
  const ok = await appConfirm({
    title: isDepositPaid ? "申请退定金并取消？" : "取消投递？",
    message: isDepositPaid
      ? "取消后定金将登记为退款（线下原路退回），订单会重新开放。"
      : "取消后该订单将重新开放给其他教员。",
    confirmText: isDepositPaid ? "取消并退定金" : "确认取消",
    danger: isDepositPaid,
  });
  if (!ok) return; // 用户在底部弹层取消：不提示、不请求
  try {
    await applicationsApi.cancel(app.id);
    showToast(isDepositPaid ? "已取消并登记退定金" : "已取消投递");
    await load();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
});

// 状态文案唯一口径来自 constants/applicationStatus；这里只维护各端配色
const statusColors: Record<string, string> = {
  pending: "text-yellow-600 bg-yellow-50",
  shortlisted: "text-slate-600 bg-slate-100",
  trial_in_progress: "text-emerald-700 bg-emerald-50",
  deposit_paid: "text-sky-700 bg-sky-50",
  balance_paid: "text-green-600 bg-green-50",
  completed: "text-emerald-700 bg-emerald-50",
  rejected: "text-red-600 bg-red-50",
  refunded: "text-gray-600 bg-gray-50",
  forfeited: "text-amber-700 bg-amber-50",
};

const statusMap: Record<string, { label: string; color: string }> = Object.fromEntries(
  (Object.keys(APPLICATION_STATUS_LABELS) as ApplicationStatus[]).map((status) => [
    status,
    { label: APPLICATION_STATUS_LABELS[status], color: statusColors[status] ?? "text-gray-600 bg-gray-50" },
  ]),
);
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="我的投递" left-arrow @click-left="router.back()" />

    <van-pull-refresh v-model="loading" @refresh="refresh">
      <div
        v-if="blacklistRecords.length > 0"
        class="mx-4 mt-3 rounded-xl border border-red-100 bg-red-50 p-3 text-xs leading-5 text-red-600"
      >
        您已被以下中介限制投递：{{
          blacklistRecords.map((r) => r.tenant_name).join("、")
        }}。如有疑问请联系对应中介沟通移除。
      </div>

      <!-- 空态/加载态撑满导航栏与底部标签栏之间的可用高度；
           pt-12 补回 pb-24 预留的一半，使内容落在导航栏与标签栏的视觉正中 -->
      <div v-if="loading && applications.length === 0" class="flex min-h-[calc(100vh-142px)] flex-col items-center justify-center pt-12 text-gray-400">
        <van-loading type="spinner" size="32" color="#334155" />
        <p class="mt-4 text-sm">加载中...</p>
      </div>

      <div v-else-if="applications.length === 0" class="flex min-h-[calc(100vh-142px)] flex-col items-center justify-center pt-12 text-gray-400">
        <!-- 显式整行居中：不依赖图标字体的字形宽度，字体回退时也不会偏 -->
        <div class="flex w-full justify-center">
          <van-icon name="notes-o" size="48" />
        </div>
        <p class="mt-5">暂无投递记录</p>
        <!-- 间距挂在外层 div：Vant 的 .van-button margin:0 会覆盖 Tailwind 的 mt-* -->
        <div class="mt-10">
          <van-button type="primary" round size="small" color="#1e3558" @click="goBoard">
            去看看订单
          </van-button>
        </div>
      </div>

      <div v-else class="space-y-3 p-4">
        <div
          v-for="app in applications"
          :key="app.id"
          class="relative cursor-pointer rounded-2xl bg-white p-4 pb-12 shadow-sm order-card"
          @click="router.push(`/teacher/orders/${app.order_id}`)"
        >
          <div class="mb-3 w-full break-words text-base font-semibold leading-7 text-slate-900">
            订单 #{{ app.raw_order_id || app.order_id }}
          </div>
          <div v-if="app.order_grade_subject || app.order_price_total" class="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-slate-700">
            <span v-if="app.order_grade_subject">{{ app.order_grade_subject }}</span>
            <span v-if="app.order_price_total" class="font-medium text-slate-900">{{ app.order_price_total }}</span>
          </div>
          <div v-if="app.order_fuzzy_address" class="mb-3 text-sm text-slate-600">
            授课区域：{{ app.order_fuzzy_address }}
          </div>
          <div class="mb-3 flex items-center gap-1 text-sm text-slate-600">
            <span class="text-xs text-gray-400">发布中介：</span>
            <span class="font-medium">{{ app.tenant_name || `中介 #${app.tenant_id}` }}</span>
          </div>
          <div class="space-y-1 text-xs text-gray-400">
            <div>投递时间：{{ formatDateTime(app.applied_at) }}</div>
            <div v-if="app.shortlisted_at">选中时间：{{ formatDateTime(app.shortlisted_at) }}</div>
            <div v-if="app.balance_paid_at">尾款支付：{{ formatDateTime(app.balance_paid_at) }}</div>
          </div>
          <div v-if="['trial_in_progress', 'balance_paid'].includes(app.status)" class="mt-3 border-t border-gray-100 pt-3">
            <button
              class="w-full rounded-xl bg-green-50 py-2 text-sm font-medium text-green-600"
              @click.stop="router.push(`/teacher/orders/${app.order_id}`)"
            >
              复制消息微信联系中介
            </button>
          </div>
          <div v-if="['pending', 'shortlisted', 'deposit_paid'].includes(app.status)" class="mt-3 border-t border-gray-100 pt-3">
            <button
              class="w-full rounded-xl bg-red-50 py-2 text-sm font-medium text-red-500 disabled:opacity-50"
              :disabled="cancelling"
              @click.stop="handleCancel(app)"
            >
              {{ app.status === 'deposit_paid' ? '取消并申请退定金' : '取消投递' }}
            </button>
          </div>
          <span
            class="absolute bottom-4 right-4 inline-flex max-w-[45%] items-center rounded-full px-3 py-1 text-xs font-semibold"
            :class="statusMap[app.status]?.color || 'bg-gray-100 text-gray-600'"
          >
            {{ statusMap[app.status]?.label || app.status }}
          </span>
        </div>

        <button
          v-if="hasMore && !loading"
          class="w-full rounded-xl bg-white py-3 text-sm font-medium text-slate-600 shadow-sm"
          @click="loadMoreSafe"
        >
          加载更多
        </button>
        <div v-if="!hasMore && applications.length > PAGE_SIZE" class="py-2 text-center text-xs text-gray-300">
          — 已经到底了 —
        </div>
      </div>
    </van-pull-refresh>
    <TeacherTabbar />
  </div>
</template>