<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import AdminTabbar from "@/components/AdminTabbar.vue";

const router = useRouter();
const auth = useAuthStore();

const stats = ref({ total: 0, recruiting: 0, trial: 0, completed: 0 });
const recentOrders = ref<any[]>([]);
const loading = ref(true);

onMounted(async () => {
  await loadData();
});

async function loadData() {
  loading.value = true;
  try {
    const res: any = await ordersApi.listOrders(1, 50);
    const items = res.items || [];
    recentOrders.value = items.slice(0, 5);
    const doneRes: any = await ordersApi.listOrders(1, 1, "completed");
    stats.value = {
      total: items.length,
      recruiting: items.filter((o: any) => o.status === "recruiting").length,
      trial: items.filter((o: any) => o.status === "trial_in_progress").length,
      completed: doneRes?.total ?? 0,
    };
  } finally {
    loading.value = false;
  }
}

const statCards = [
  { key: "total", label: "活跃订单", icon: "📋", color: "bg-blue-50 text-blue-600" },
  { key: "recruiting", label: "招聘中", icon: "🔍", color: "bg-green-50 text-green-600" },
  { key: "trial", label: "试课中", icon: "📝", color: "bg-emerald-50 text-emerald-700" },
  { key: "completed", label: "已成交", icon: "✅", color: "bg-yellow-50 text-yellow-600" },
];

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
    <div class="header-gradient px-4 pt-8 pb-5">
      <div class="flex items-center justify-between">
        <div class="text-white">
          <div class="text-xl font-bold leading-tight">
            {{ auth.tenant?.tenant_name || "中介后台" }}
          </div>
          <div class="text-xs opacity-80 mt-1">{{ auth.tenant?.invite_code }}</div>
        </div>
        <button class="bg-white/20 rounded-lg px-3 py-2 text-white text-sm" @click="router.push('/admin/settings')">
          ⚙️ 设置
        </button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="px-4 mt-3">
      <div class="grid grid-cols-2 gap-3">
        <div
          v-for="card in statCards" :key="card.key"
          class="bg-white rounded-2xl p-4 shadow-sm"
        >
          <div class="text-2xl mb-1">{{ card.icon }}</div>
          <div class="text-2xl font-bold">{{ stats[card.key as keyof typeof stats] }}</div>
          <div class="text-gray-400 text-xs mt-1">{{ card.label }}</div>
        </div>
      </div>
    </div>

    <!-- 快捷操作 -->
    <div class="px-4 mt-4">
      <div class="grid grid-cols-2 gap-3">
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/batch-import')"
        >
          <div class="text-2xl">📥</div>
          <div class="font-semibold mt-2">批量导入</div>
          <div class="text-gray-400 text-xs mt-1">粘贴微信文本</div>
        </button>
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/applications')"
        >
          <div class="text-2xl">👥</div>
          <div class="font-semibold mt-2">投递审核</div>
          <div class="text-gray-400 text-xs mt-1">筛选合适教员</div>
        </button>
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/financial-records')"
        >
          <div class="text-2xl">¥</div>
          <div class="font-semibold mt-2">财务流水</div>
          <div class="text-gray-400 text-xs mt-1">查看线下收款</div>
        </button>
        <button
          class="bg-white rounded-2xl p-4 shadow-sm text-left order-card"
          @click="router.push('/admin/map')"
        >
          <div class="text-2xl">🗺️</div>
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
