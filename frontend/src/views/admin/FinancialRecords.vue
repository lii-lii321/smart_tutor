<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { financialApi } from "@/api/financial";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast } from "vant";

const router = useRouter();
const loading = ref(true);
const summary = ref<any>({
  deposit_in: 0,
  balance_in: 0,
  refund_out: 0,
  forfeit: 0,
  net_amount: 0,
  records: [],
});

onMounted(() => loadData());

async function loadData() {
  loading.value = true;
  try {
    summary.value = await financialApi.list(1, 100);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载财务数据失败");
  } finally {
    loading.value = false;
  }
}

const typeLabels: Record<string, string> = {
  deposit_in: "定金收入",
  balance_in: "尾款收入",
  refund_out: "退款支出",
  forfeit: "定金没收",
};

const typeClasses: Record<string, string> = {
  deposit_in: "bg-blue-50 text-blue-700",
  balance_in: "bg-green-50 text-green-700",
  refund_out: "bg-red-50 text-red-600",
  forfeit: "bg-amber-50 text-amber-700",
};
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="财务流水" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="p-4">
      <div class="bg-[#1a365d] text-white rounded-2xl p-4 shadow-sm">
        <div class="text-sm opacity-80">净收入</div>
        <div class="text-3xl font-bold mt-1">¥{{ summary.net_amount }}</div>
      </div>

      <div class="grid grid-cols-2 gap-3 mt-3">
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-gray-400 text-xs">定金收入</div>
          <div class="text-xl font-bold text-blue-700 mt-1">¥{{ summary.deposit_in }}</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-gray-400 text-xs">尾款收入</div>
          <div class="text-xl font-bold text-green-700 mt-1">¥{{ summary.balance_in }}</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-gray-400 text-xs">退款支出</div>
          <div class="text-xl font-bold text-red-600 mt-1">¥{{ summary.refund_out }}</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-gray-400 text-xs">其他收入</div>
          <div class="text-xl font-bold text-amber-700 mt-1">¥{{ summary.forfeit }}</div>
        </div>
      </div>

      <div class="mt-5 mb-3 flex items-center justify-between">
        <h3 class="font-semibold">流水明细</h3>
        <button class="text-primary-600 text-sm" @click="loadData">刷新</button>
      </div>

      <div v-if="summary.records.length === 0" class="text-center py-16 text-gray-400">
        <van-icon name="balance-list-o" size="42" />
        <p class="mt-3 text-sm">暂无流水</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="record in summary.records"
          :key="record.id"
          class="bg-white rounded-2xl p-4 shadow-sm"
        >
          <div class="flex items-center justify-between">
            <span class="px-2 py-0.5 rounded-full text-xs" :class="typeClasses[record.type]">
              {{ typeLabels[record.type] || record.type }}
            </span>
            <div
              class="font-bold text-lg"
              :class="record.type === 'refund_out' ? 'text-red-600' : 'text-gray-900'"
            >
              {{ record.type === 'refund_out' ? '-' : '+' }}¥{{ record.amount }}
            </div>
          </div>
          <div class="text-sm text-gray-600 mt-2">
            订单 #{{ record.order_id }} · 教员 #{{ record.teacher_id }}
          </div>
          <div class="text-xs text-gray-400 mt-1">
            {{ record.remark || "无备注" }} · {{ new Date(record.created_at).toLocaleString("zh-CN") }}
          </div>
        </div>
      </div>
    </div>

    <van-overlay :show="loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
    <AdminTabbar />
  </div>
</template>
