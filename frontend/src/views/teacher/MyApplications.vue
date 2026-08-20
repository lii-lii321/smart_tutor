<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { applicationsApi } from "@/api/applications";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { showToast, showConfirmDialog } from "vant";

const router = useRouter();
const applications = ref<any[]>([]);
const loading = ref(true);

onMounted(async () => {
  await loadData();
});

async function loadData() {
  loading.value = true;
  try {
    applications.value = (await applicationsApi.listMine()) as any[];
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
  rejected: { label: "试课失败", color: "text-red-600 bg-red-50" },
  refunded: { label: "已退款", color: "text-gray-600 bg-gray-50" },
};
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-24">
    <van-nav-bar title="我的投递" left-arrow @click-left="router.back()" />

    <van-pull-refresh v-model="loading" @refresh="loadData">
      <div v-if="applications.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <van-icon name="notes-o" size="48" />
        <p class="mt-4">暂无投递记录</p>
        <van-button class="mt-4" type="primary" round size="small" @click="router.push('/')">
          去看看订单
        </van-button>
      </div>

      <div v-else class="p-4 space-y-3">
        <div
          v-for="app in applications"
          :key="app.id"
          class="bg-white rounded-2xl p-4 shadow-sm order-card"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="font-semibold">订单 #{{ app.order_id }}</div>
            <span
              class="px-3 py-1 rounded-full text-xs font-medium"
              :class="statusMap[app.status]?.color || 'text-gray-600 bg-gray-50'"
            >
              {{ statusMap[app.status]?.label || app.status }}
            </span>
          </div>
          <div class="text-xs text-gray-400 space-y-1">
            <div>投递时间：{{ new Date(app.applied_at).toLocaleString("zh-CN") }}</div>
            <div v-if="app.shortlisted_at">选中时间：{{ new Date(app.shortlisted_at).toLocaleString("zh-CN") }}</div>
            <div v-if="app.balance_paid_at">尾款支付：{{ new Date(app.balance_paid_at).toLocaleString("zh-CN") }}</div>
          </div>
          <div v-if="['trial_in_progress', 'balance_paid'].includes(app.status)" class="mt-3 pt-3 border-t border-gray-100">
            <button
              class="w-full bg-green-50 text-green-600 rounded-xl py-2 text-sm font-medium"
              @click="router.push(`/teacher/orders/${app.order_id}`)"
            >
              查看家长联系方式
            </button>
          </div>
          <div v-if="['pending', 'shortlisted', 'deposit_paid'].includes(app.status)" class="mt-3 pt-3 border-t border-gray-100">
            <button
              class="w-full bg-red-50 text-red-500 rounded-xl py-2 text-sm font-medium"
              @click="handleCancel(app)"
            >
              {{ app.status === 'deposit_paid' ? '取消并申请退定金' : '取消投递' }}
            </button>
          </div>
        </div>
      </div>
    </van-pull-refresh>
    <TeacherTabbar />
  </div>
</template>
