<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import type { OrderBrief } from "@/api/types";
import { notificationsApi, type NotificationItem } from "@/api/notifications";
import { tenantsApi, type TenantRoiSummary } from "@/api/tenants";
import { formatMoney } from "@/utils/format";
import { ORDER_STATUS_COLORS, ORDER_STATUS_LABELS } from "@/constants/orderStatus";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";

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

// B 端通知
const notifVisible = ref(false);
const notifLoading = ref(false);
const notifUnread = ref(0);
const notifications = ref<NotificationItem[]>([]);

async function loadNotifBadge() {
  try {
    // 轻量未读数端点：角标轮询不再每 60s 拉一次全量通知列表
    notifUnread.value = await notificationsApi.tenantUnreadCount();
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

// 通知管理模式：勾选批量删除 / 清空全部（用户主动删除，不设自动清理）
const notifManaging = ref(false);
const notifChecked = ref<Set<number>>(new Set());
const notifAllChecked = computed(
  () => notifications.value.length > 0 && notifChecked.value.size === notifications.value.length
);

function toggleNotifManaging() {
  notifManaging.value = !notifManaging.value;
  notifChecked.value = new Set();
}

function toggleNotifChecked(id: number) {
  const next = new Set(notifChecked.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  notifChecked.value = next;
}

function toggleNotifAll() {
  notifChecked.value = notifAllChecked.value
    ? new Set()
    : new Set(notifications.value.map((n) => n.id));
}

async function deleteCheckedNotifs() {
  const ids = [...notifChecked.value];
  if (ids.length === 0) return;
  try {
    const res = await notificationsApi.deleteTenant(ids);
    notifications.value = notifications.value.filter((n) => !notifChecked.value.has(n.id));
    notifChecked.value = new Set();
    showToast(`已删除 ${res.marked} 条`);
  } catch {
    showToast("删除失败");
  }
}

async function deleteAllNotifs() {
  const ok = await appConfirm({
    title: "清空全部通知？",
    message: "删除后不可恢复，历史投递仍可在对应订单中查看。",
    confirmText: "清空",
    danger: true,
  });
  if (!ok) return;
  try {
    await notificationsApi.deleteAllTenant();
    notifications.value = [];
    notifChecked.value = new Set();
    showToast("已清空");
  } catch {
    showToast("删除失败");
  }
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

    <!-- B 端通知弹层 -->
    <van-popup v-model:show="notifVisible" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
      <div class="flex max-h-[75vh] flex-col p-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-base font-semibold text-slate-950">消息通知</div>
          <div class="flex items-center gap-3">
            <button
              v-if="!notifManaging && notifUnread > 0"
              class="text-sm text-blue-600"
              @click="markTenantRead"
            >
              全部已读
            </button>
            <button
              v-if="notifications.length > 0"
              class="text-sm text-slate-500"
              @click="toggleNotifManaging"
            >
              {{ notifManaging ? "完成" : "管理" }}
            </button>
          </div>
        </div>

        <!-- 管理模式工具条：全选 + 删除 -->
        <div v-if="notifManaging" class="mb-2 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
          <label class="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" :checked="notifAllChecked" @change="toggleNotifAll" />
            全选（{{ notifChecked.size }}/{{ notifications.length }}）
          </label>
          <button
            class="text-sm font-medium text-red-500 disabled:opacity-40"
            :disabled="notifChecked.size === 0"
            @click="deleteCheckedNotifs"
          >
            删除选中
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
              :class="notifManaging ? 'flex items-start gap-2 border-slate-100 bg-white' : item.is_read ? 'border-slate-100 bg-white' : 'border-blue-100 bg-blue-50/40'"
            >
              <input
                v-if="notifManaging"
                type="checkbox"
                class="mt-1"
                :checked="notifChecked.has(item.id)"
                @change="toggleNotifChecked(item.id)"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-start justify-between gap-2">
                  <div class="text-sm font-semibold text-slate-900">
                    {{ !notifManaging && !item.is_read ? "● " : "" }}{{ item.title }}
                  </div>
                  <div class="shrink-0 text-xs text-slate-400">
                    {{ new Date(item.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) }}
                  </div>
                </div>
                <p v-if="item.content" class="mt-1 text-sm leading-5 text-slate-600">{{ item.content }}</p>
                <button
                  v-if="!notifManaging && item.order_id"
                  class="mt-2 text-xs text-blue-600"
                  @click="notifVisible = false; router.push(`/admin/applications?order=${item.order_id}`)"
                >
                  去处理 →
                </button>
              </div>
            </article>
          </div>
        </div>

        <button
          v-if="notifManaging && notifications.length > 0"
          class="mt-3 shrink-0 text-center text-xs text-slate-400"
          @click="deleteAllNotifs"
        >
          清空全部通知
        </button>
      </div>
    </van-popup>

    <van-overlay :show="loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
  </div>
</template>
