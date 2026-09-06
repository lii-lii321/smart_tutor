<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

const stats = ref({ archived: 0, recruiting: 0, trial: 0, completed: 0 });
const recentOrders = ref<any[]>([]);
const loading = ref(true);

onMounted(async () => {
  await loadData();
});

async function loadData() {
  loading.value = true;
  try {
    // 最近订单只取 5 条；四个统计数字全部用后端 total，避免从第一页 filter 导致的口径错误
    const [recent, recruitingRes, trialRes, completedRes, archivedRes] = await Promise.all([
      ordersApi.listOrders(1, 5),
      ordersApi.listOrders(1, 1, "recruiting"),
      ordersApi.listOrders(1, 1, "trial_in_progress"),
      ordersApi.listOrders(1, 1, "completed"),
      ordersApi.listOrders(1, 1, "archived"),
    ]);
    recentOrders.value = recent.items || [];
    stats.value = {
      archived: archivedRes?.total ?? 0,
      recruiting: recruitingRes?.total ?? 0,
      trial: trialRes?.total ?? 0,
      completed: completedRes?.total ?? 0,
    };
  } catch {
    showToast("数据加载失败，请下拉重试");
  } finally {
    loading.value = false;
  }
}

const statCards = [
  { key: "archived", label: "已归档", icon: "records-o", color: "bg-slate-100 text-slate-600", query: "archived" },
  { key: "recruiting", label: "招聘中", icon: "search", color: "bg-green-50 text-green-600", query: "recruiting" },
  { key: "trial", label: "试课中", icon: "edit", color: "bg-emerald-50 text-emerald-700", query: "trial_in_progress" },
  { key: "completed", label: "已成交", icon: "checked", color: "bg-yellow-50 text-yellow-600", query: "completed" },
];

function openOrders(status = "") {
  router.push({ path: "/admin/orders", query: status ? { status } : {} });
}

const statusColors: Record<string, string> = {
  recruiting: "bg-blue-100 text-blue-700",
  trial_in_progress: "bg-green-100 text-green-700",
  completed: "bg-gray-100 text-gray-700",
  archived: "bg-red-50 text-red-400",
};
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <!-- 头部 -->
    <div class="dashboard-header mx-3 mt-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 shadow-sm">
      <div class="flex items-center justify-between">
        <div class="text-slate-900">
          <div class="text-lg font-bold leading-tight">
            {{ auth.tenant?.tenant_name || (auth.role === "super_admin" ? "平台管理" : "中介后台") }}
          </div>
          <div class="mt-0.5 text-xs text-slate-500">
            {{ auth.tenant?.invite_code || (auth.role === "super_admin" ? "全平台数据" : "") }}
          </div>
        </div>
        <button class="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" @click="router.push('/admin/settings')">
          <van-icon name="setting-o" size="18" />
          设置
        </button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="px-4 mt-3">
      <div class="grid grid-cols-2 gap-3">
        <button
          v-for="card in statCards" :key="card.key"
          class="bg-white rounded-2xl p-4 text-left shadow-sm transition active:scale-[0.99]"
          @click="openOrders(card.query)"
        >
          <div class="mb-2 flex h-9 w-9 items-center justify-center rounded-xl" :class="card.color">
            <van-icon :name="card.icon" size="22" />
          </div>
          <div class="text-2xl font-bold">{{ stats[card.key as keyof typeof stats] }}</div>
          <div class="text-gray-400 text-xs mt-1">{{ card.label }}</div>
        </button>
      </div>
    </div>

    <!-- 快捷操作 -->
    <div class="px-4 mt-4">
      <div class="grid grid-cols-2 gap-3">
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/batch-import')"
        >
          <van-icon name="upgrade" size="30" color="#2563eb" />
          <div class="font-semibold mt-2">批量导入</div>
          <div class="text-gray-400 text-xs mt-1">粘贴微信文本</div>
        </button>
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/applications')"
        >
          <van-icon name="friends-o" size="30" color="#2563eb" />
          <div class="font-semibold mt-2">投递审核</div>
          <div class="text-gray-400 text-xs mt-1">筛选合适教员</div>
        </button>
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/financial-records')"
        >
          <van-icon name="balance-list-o" size="30" color="#2563eb" />
          <div class="font-semibold mt-2">财务流水</div>
          <div class="text-gray-400 text-xs mt-1">查看线下收款</div>
        </button>
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/map')"
        >
          <van-icon name="location-o" size="30" color="#2563eb" />
          <div class="font-semibold mt-2">地图看单</div>
          <div class="text-gray-400 text-xs mt-1">按位置查看订单</div>
        </button>
      </div>
    </div>

    <!-- 最近订单 -->
    <div class="px-4 mt-6">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-bold text-lg">最近订单</h3>
        <span class="text-primary-600 text-sm cursor-pointer" @click="router.push('/admin/orders')">查看全部 →</span>
      </div>

      <div v-if="recentOrders.length === 0" class="text-center py-10 text-gray-400">
        暂无订单，去导入吧
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="order in recentOrders" :key="order.id"
          class="bg-white rounded-2xl p-4 shadow-sm order-card"
        >
          <div class="flex items-center justify-between">
            <div>
              <div class="font-semibold">{{ order.grade_subject }}</div>
              <div class="text-gray-400 text-xs mt-1">{{ order.fuzzy_address }}</div>
            </div>
            <div class="text-right">
              <div class="text-primary-600 font-bold text-lg price-highlight">¥{{ order.base_price }}</div>
              <span class="px-2 py-0.5 rounded-full text-xs" :class="statusColors[order.status] || 'bg-gray-100'">
                {{ order.status }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AdminTabbar />

    <van-overlay :show="loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
  </div>
</template>
