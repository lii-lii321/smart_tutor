<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { applicationsApi } from "@/api/applications";
import { tenantsApi } from "@/api/tenants";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { getLastInviteCode } from "@/utils/inviteCode";
import { showToast, showConfirmDialog } from "vant";

const router = useRouter();
const applications = ref<any[]>([]);
const loading = ref(true);
// 分页加载：后端按 applied_at 倒序返回，到底后隐藏"加载更多"
const PAGE_SIZE = 20;
const page = ref(1);
const hasMore = ref(false);
// 被中介拉黑记录（教员可见性提示）
const blacklistRecords = ref<{ tenant_name: string; reason?: string | null }[]>([]);

function goBoard() {
  router.push(`/teacher/board/${getLastInviteCode()}`);
}

onMounted(async () => {
  await Promise.all([loadData(), loadBlacklistStatus()]);
});

async function loadBlacklistStatus() {
  try {
    blacklistRecords.value = await tenantsApi.myBlacklistStatus();
  } catch {
    blacklistRecords.value = [];
  }
}

async function loadData(reset = true) {
  loading.value = true;
  try {
    const targetPage = reset ? 1 : page.value;
    const list = (await applicationsApi.listMine(targetPage, PAGE_SIZE)) as any[];
    applications.value = reset ? list : [...applications.value, ...list];
    page.value = targetPage + 1;
    hasMore.value = list.length === PAGE_SIZE;
  } catch {
    showToast("加载失败");
  } finally {
    loading.value = false;
  }
}

async function handleCancel(app: any) {
  const isDepositPaid = app.status === "deposit_paid";
  try {
    await showConfirmDialog({
      title: isDepositPaid ? "申请退定金并取消？" : "取消投递？",
      message: isDepositPaid
        ? "取消后定金将登记为退款（线下原路退回），订单会重新开放。"
        : "取消后该订单将重新开放给其他教员。",
      confirmButtonText: "确认取消",
    });
    await applicationsApi.cancel(app.id);
    showToast(isDepositPaid ? "已取消并登记退定金" : "已取消投递");
    await loadData();
  } catch (e: any) {
    if (e?.response) showToast(e.response.data?.detail || "操作失败");
  }
}

const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: "待审核", color: "text-yellow-600 bg-yellow-50" },
  shortlisted: { label: "候选排队", color: "text-blue-600 bg-blue-50" },
  trial_in_progress: { label: "正在试课", color: "text-emerald-700 bg-emerald-50" },
  deposit_paid: { label: "定金已付", color: "text-sky-700 bg-sky-50" },
  balance_paid: { label: "尾款已付", color: "text-green-600 bg-green-50" },
  completed: { label: "已成交", color: "text-emerald-700 bg-emerald-50" },
  rejected: { label: "未通过", color: "text-red-600 bg-red-50" },
  refunded: { label: "已退款", color: "text-gray-600 bg-gray-50" },
};
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-24">
    <van-nav-bar title="我的投递" left-arrow @click-left="router.back()" />

    <van-pull-refresh v-model="loading" @refresh="loadData">
      <div
        v-if="blacklistRecords.length > 0"
        class="mx-4 mt-3 rounded-xl border border-red-100 bg-red-50 p-3 text-xs leading-5 text-red-600"
      >
        您已被以下中介限制投递：{{
          blacklistRecords.map((r) => r.tenant_name).join("、")
        }}。如有疑问请联系对应中介沟通移除。
      </div>

      <div v-if="loading && applications.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <van-loading type="spinner" size="32" color="#2563eb" />
        <p class="mt-4 text-sm">加载中...</p>
      </div>

      <div v-else-if="applications.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <van-icon name="notes-o" size="48" />
        <p class="mt-4">暂无投递记录</p>
        <van-button class="mt-4" type="primary" round size="small" @click="goBoard">
          去看看订单
        </van-button>
      </div>

      <div v-else class="space-y-3 p-4">
        <div
          v-for="app in applications"
          :key="app.id"
          class="relative rounded-2xl bg-white p-4 pb-12 shadow-sm order-card"
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
            <div>投递时间：{{ new Date(app.applied_at).toLocaleString("zh-CN") }}</div>
            <div v-if="app.shortlisted_at">选中时间：{{ new Date(app.shortlisted_at).toLocaleString("zh-CN") }}</div>
            <div v-if="app.balance_paid_at">尾款支付：{{ new Date(app.balance_paid_at).toLocaleString("zh-CN") }}</div>
          </div>
          <div v-if="['trial_in_progress', 'balance_paid'].includes(app.status)" class="mt-3 border-t border-gray-100 pt-3">
            <button
              class="w-full rounded-xl bg-green-50 py-2 text-sm font-medium text-green-600"
              @click.stop="router.push(`/teacher/orders/${app.order_id}`)"
            >
              查看家长联系方式
            </button>
          </div>
          <div v-if="['pending', 'shortlisted', 'deposit_paid'].includes(app.status)" class="mt-3 border-t border-gray-100 pt-3">
            <button
              class="w-full rounded-xl bg-red-50 py-2 text-sm font-medium text-red-500"
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
          @click="loadData(false)"
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
