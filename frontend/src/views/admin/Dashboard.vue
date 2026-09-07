<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import { notificationsApi, type NotificationItem } from "@/api/notifications";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

const stats = ref({ archived: 0, recruiting: 0, trial: 0, completed: 0 });
const recentOrders = ref<any[]>([]);
const loading = ref(true);
const loadError = ref(false);

// B 端通知
const notifVisible = ref(false);
const notifLoading = ref(false);
const notifUnread = ref(0);
const notifications = ref<NotificationItem[]>([]);

async function loadNotifBadge() {
  try {
    const data = await notificationsApi.tenantMine();
    notifications.value = data.items;
    notifUnread.value = data.unread_count;
  } catch {
    // 角标加载失败不打扰主流程
  }
}

async function openNotifications() {
  notifVisible.value = true;
  notifLoading.value = true;
  try {
    const data = await notificationsApi.tenantMine();
    notifications.value = data.items;
    notifUnread.value = data.unread_count;
  } catch {
    showToast("通知加载失败");
  } finally {
    notifLoading.value = false;
  }
}

async function markTenantRead() {
  try {
    await notificationsApi.tenantReadAll();
    notifications.value = notifications.value.map((n) => ({ ...n, is_read: true }));
    notifUnread.value = 0;
    showToast("已全部标记为已读");
  } catch {
    showToast("操作失败");
  }
}

onMounted(async () => {
  await loadData();
  loadNotifBadge();
  // 通知角标每 60 秒静默刷新，新投递/临期提醒不用手动刷新页面
  badgeTimer = window.setInterval(loadNotifBadge, 60_000);
});

onUnmounted(() => {
  if (badgeTimer) window.clearInterval(badgeTimer);
});

let badgeTimer: number | undefined;

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
    showToast("数据加载失败，请点击右上角设置旁的任意卡片重试");
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

const statusLabels: Record<string, string> = {
  recruiting: "招聘中",
  trial_in_progress: "试课中",
  completed: "已成交",
  archived: "已归档",
};

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
        <div class="flex items-center gap-2">
          <button
            class="relative inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-700"
            @click="openNotifications"
          >
            <van-icon name="bell" size="18" />
            <span
              v-if="notifUnread > 0"
              class="absolute -right-1 -top-1 min-w-[16px] rounded-full bg-red-500 px-1 text-[10px] font-bold leading-4 text-white"
            >
              {{ notifUnread > 99 ? "99+" : notifUnread }}
            </span>
          </button>
          <button class="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" @click="router.push('/admin/settings')">
            <van-icon name="setting-o" size="18" />
            设置
          </button>
        </div>
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
        <template v-if="loadError">
          数据加载失败
          <button class="ml-2 rounded-lg bg-slate-100 px-3 py-1 text-sm text-slate-600" @click="loadData">
            重试
          </button>
        </template>
        <template v-else>暂无订单，去导入吧</template>
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
                {{ statusLabels[order.status] || order.status }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AdminTabbar />

    <!-- B 端通知弹层 -->
    <van-popup v-model:show="notifVisible" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
      <div class="flex max-h-[75vh] flex-col p-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-base font-semibold text-slate-950">消息通知</div>
          <button
            v-if="notifUnread > 0"
            class="text-sm text-blue-600"
            @click="markTenantRead"
          >
            全部已读
          </button>
        </div>
        <div class="overflow-y-auto">
          <div v-if="notifLoading" class="flex justify-center py-8">
            <van-loading type="spinner" color="#2563eb" />
          </div>
          <div v-else-if="notifications.length === 0" class="py-8 text-center text-sm text-slate-400">
            暂无通知。收到新投递、订单即将过期时会在这里提醒。
          </div>
          <div v-else class="space-y-3 pb-4">
            <article
              v-for="item in notifications"
              :key="item.id"
              class="rounded-lg border p-3"
              :class="item.is_read ? 'border-slate-100 bg-white' : 'border-blue-100 bg-blue-50/40'"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="text-sm font-semibold text-slate-900">
                  {{ item.is_read ? "" : "● " }}{{ item.title }}
                </div>
                <div class="shrink-0 text-xs text-slate-400">
                  {{ new Date(item.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) }}
                </div>
              </div>
              <p v-if="item.content" class="mt-1 text-sm leading-5 text-slate-600">{{ item.content }}</p>
              <button
                v-if="item.order_id"
                class="mt-2 text-xs text-blue-600"
                @click="notifVisible = false; router.push(`/admin/applications?order=${item.order_id}`)"
              >
                去处理 →
              </button>
            </article>
          </div>
        </div>
      </div>
    </van-popup>

    <van-overlay :show="loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
  </div>
</template>
