<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import type { OrderBrief } from "@/api/types";
import { notificationsApi } from "@/api/notifications";
import { tenantsApi, type TenantRoiSummary } from "@/api/tenants";
import { formatMoney } from "@/utils/format";
import { ORDER_STATUS_COLORS, ORDER_STATUS_LABELS } from "@/constants/orderStatus";
import AdminTabbar from "@/components/AdminTabbar.vue";
import NotificationList from "@/components/NotificationList.vue";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

const stats = ref({ archived: 0, recruiting: 0, trial: 0, completed: 0 });
const recentOrders = ref<OrderBrief[]>([]);
const loading = ref(true);
const loadError = ref(false);

// 「本月为你」ROI 卡片：加载失败静默隐藏，不干扰主流程
const roi = ref<TenantRoiSummary | null>(null);

async function loadRoi() {
  try {
    roi.value = await tenantsApi.roiSummary();
  } catch {
    roi.value = null;
  }
}

const savedMinutes = computed(() => (roi.value?.orders_imported ?? 0) * 3);

function formatSaved(minutes: number): string {
  if (minutes <= 0) return "0 分钟";
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = minutes / 60;
  return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} 小时`;
}

// B 端通知：角标轮询在本页，列表弹层复用全站共享的 NotificationList 组件
const notifVisible = ref(false);
const notifUnread = ref(0);
// 角标定时器句柄：声明提前，避免阅读时误以为 onMounted 之后才存在
let badgeTimer: number | undefined;

async function loadNotifBadge() {
  try {
    // 轻量未读数端点：角标轮询不再每 60s 拉一次全量通知列表
    notifUnread.value = await notificationsApi.tenantUnreadCount();
  } catch {
    // 角标加载失败不打扰主流程
  }
}

function openNotifications() {
  notifVisible.value = true;
}

onMounted(async () => {
  await loadData();
  loadNotifBadge();
  loadRoi();
  // 通知角标每 60 秒静默刷新，新投递/临期提醒不用手动刷新页面；
  // 页面切到后台时暂停轮询（浏览器会节流定时器，但请求仍在发），回到前台立即补一次
  badgeTimer = window.setInterval(() => {
    if (document.hidden) return;
    loadNotifBadge();
  }, 60_000);
  document.addEventListener("visibilitychange", onVisibilityChange);
});

function onVisibilityChange() {
  if (!document.hidden) loadNotifBadge();
}

onUnmounted(() => {
  if (badgeTimer) window.clearInterval(badgeTimer);
  document.removeEventListener("visibilitychange", onVisibilityChange);
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
    showToast("数据加载失败，请点击右上角设置旁的任意卡片重试");
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

// 状态文案/配色唯一口径在 constants/orderStatus.ts（与订单列表页共用）
const statusLabels = ORDER_STATUS_LABELS;

const statCards = [
  { key: "archived", label: "已归档", icon: "records-o", color: "bg-slate-100 text-slate-600", query: "archived" },
  { key: "recruiting", label: "招聘中", icon: "search", color: "bg-green-50 text-green-600", query: "recruiting" },
  { key: "trial", label: "试课中", icon: "edit", color: "bg-emerald-50 text-emerald-700", query: "trial_in_progress" },
  { key: "completed", label: "已成交", icon: "checked", color: "bg-yellow-50 text-yellow-600", query: "completed" },
];

function openOrders(status = "") {
  router.push({ path: "/admin/orders", query: status ? { status } : {} });
}

const statusColors = ORDER_STATUS_COLORS;
</script>

<template>
  <!-- 宽屏下约束内容宽度，保持 H5 卡片比例 -->
  <div class="min-h-screen bg-gray-50 pb-20 mx-auto max-w-2xl">
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

    <!-- 本月为你（ROI 卡片） -->
    <div v-if="roi" class="px-4 mt-3">
      <div class="bg-white rounded-2xl p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <h3 class="font-bold text-slate-900">本月为你</h3>
          <span class="text-xs text-slate-400">{{ roi.month }}</span>
        </div>
        <div class="mt-3 grid grid-cols-3 gap-x-2 gap-y-4">
          <div>
            <div class="text-xl font-bold text-slate-900">{{ roi.orders_imported }}</div>
            <div class="mt-0.5 text-xs text-slate-400">录单（条）</div>
          </div>
          <div>
            <div class="text-xl font-bold text-blue-600">≈{{ formatSaved(savedMinutes) }}</div>
            <div class="mt-0.5 text-xs text-slate-400">录单省时（估）</div>
          </div>
          <div>
            <div class="text-xl font-bold text-slate-900">{{ roi.applications_received }}</div>
            <div class="mt-0.5 text-xs text-slate-400">收到投递</div>
          </div>
          <div>
            <div class="text-xl font-bold text-slate-900">{{ roi.deals_completed }}</div>
            <div class="mt-0.5 text-xs text-slate-400">成交订单</div>
          </div>
          <div>
            <div class="text-xl font-bold text-emerald-600">{{ formatMoney(roi.net_amount) }}</div>
            <div class="mt-0.5 text-xs text-slate-400">净入账流水</div>
          </div>
          <div>
            <div class="text-xl font-bold text-slate-900">{{ roi.teacher_pool }}</div>
            <div class="mt-0.5 text-xs text-slate-400">我的教员库</div>
          </div>
        </div>
        <div class="mt-3 text-[11px] leading-4 text-slate-400">
          净入账 = 定金 + 尾款 − 退款；录单省时按手工录单约 3 分钟/条估算
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

    <!-- B 端通知弹层（列表/管理/已读逻辑在共享组件内） -->
    <NotificationList
      v-model:show="notifVisible"
      scope="tenant"
      title="消息通知"
      empty-hint="暂无通知。收到新投递、订单即将过期时会在这里提醒。"
    />

    <van-overlay :show="loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
  </div>
</template>
