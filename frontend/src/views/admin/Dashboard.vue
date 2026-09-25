<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import type { OrderBrief } from "@/api/types";
import { notificationsApi } from "@/api/notifications";
import { tenantsApi, type TenantRoiSummary } from "@/api/tenants";
import { formatMoney } from "@/utils/format";
import AdminTabbar from "@/components/AdminTabbar.vue";
import NotificationList from "@/components/NotificationList.vue";
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import TodoCard, { type TodoViewModel } from "@/components/business/TodoCard.vue";
import { buildWorkbenchTodos } from "@/components/business/workbench";
import { applicationsApi } from "@/api/applications";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

// 工作台只关心"现在要处理什么"：招聘中=去配教员，试课中=跟进成交
const stats = ref({ recruiting: 0, trial: 0 });
const applicationTotal = ref(0);
const recentOrders = ref<OrderBrief[]>([]);
const loading = ref(true);
const loadError = ref(false);

// 「本月经营」ROI：加载失败静默隐藏，不干扰主流程
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

// 投递成交率：本月成交 ÷ 收到投递；无投递时不显示百分比
const conversionText = computed(() => {
  const received = roi.value?.applications_received ?? 0;
  if (received <= 0) return "—";
  return `${Math.round(((roi.value?.deals_completed ?? 0) / received) * 100)}%`;
});

function greetingByTime(): string {
  const hour = new Date().getHours();
  if (hour < 11) return "早上好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}
const greeting = computed(
  () => `${greetingByTime()}，${auth.tenant?.tenant_name || (auth.role === "super_admin" ? "老板" : "中介老板")}`
);

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
    // 最近订单只取 5 条；待办数字用后端 total，避免从第一页 filter 导致的口径错误
    const [recent, recruitingRes, trialRes, appSummary] = await Promise.all([
      ordersApi.listOrders(1, 5),
      ordersApi.listOrders(1, 1, "recruiting"),
      ordersApi.listOrders(1, 1, "trial_in_progress"),
      applicationsApi.summary().catch(() => null),
    ]);
    recentOrders.value = recent.items || [];
    stats.value = {
      recruiting: recruitingRes?.total ?? 0,
      trial: trialRes?.total ?? 0,
    };
    applicationTotal.value = Number(appSummary?.total_applications || 0);
  } catch {
    showToast("数据加载失败，请下拉重试或点击卡片重试");
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

// Workbench 待办（Batch 04）：视图模型由 workbench 适配器产出，页面只做路由分发
const workbenchTodos = computed(() =>
  buildWorkbenchTodos({
    recruiting: stats.value.recruiting,
    trial: stats.value.trial,
    applicationTotal: applicationTotal.value,
    notifUnread: notifUnread.value,
  })
);

function openTodo(todo: TodoViewModel) {
  const routes: Record<string, string> = {
    recruiting: "/admin/orders?status=recruiting",
    trial: "/admin/orders?status=trial_in_progress",
    applications: "/admin/applications",
  };
  if (routes[todo.key]) {
    router.push(routes[todo.key]);
    return;
  }
  openNotifications();
}

type QuickAction = {
  key: string;
  label: string;
  icon: string;
  to?: string;
  action?: () => void;
};

const quickActions: QuickAction[] = [
  { key: "import", label: "AI 批量录单", icon: "upgrade", to: "/admin/batch-import" },
  { key: "orders", label: "订单管理", icon: "records-o", to: "/admin/orders" },
  { key: "applications", label: "投递审核", icon: "friends-o", to: "/admin/applications" },
  { key: "financial", label: "财务流水", icon: "balance-list-o", to: "/admin/financial-records" },
  { key: "map", label: "地图看单", icon: "location-o", to: "/admin/map" },
  { key: "notif", label: "消息通知", icon: "bell", action: openNotifications },
];

function goQuick(action: QuickAction) {
  if (action.to) {
    router.push(action.to);
    return;
  }
  action.action?.();
}
</script>

<template>
  <!-- 宽屏下约束内容宽度，≥1024px 经 .admin-page 为左侧导航栏让位 -->
  <div class="admin-page min-h-screen bg-page pb-20 mx-auto max-w-2xl">
    <!-- 头部：问候 + 中介身份 + 通知/设置 -->
    <div class="dashboard-header mx-3 mt-2 rounded-xl border border-default bg-surface px-4 py-3 shadow-sm">
      <div class="flex items-center justify-between">
        <div class="min-w-0">
          <div class="truncate text-lg font-bold leading-tight text-primary">
            {{ greeting }}
          </div>
          <div class="mt-0.5 truncate text-xs text-muted">
            {{ auth.tenant?.tenant_name || (auth.role === "super_admin" ? "平台管理" : "中介后台") }}
            <template v-if="auth.tenant?.invite_code"> · {{ auth.tenant.invite_code }}</template>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            class="relative inline-flex h-9 w-9 items-center justify-center rounded-lg bg-surface-soft text-slate-700"
            aria-label="消息通知"
            @click="openNotifications"
          >
            <van-icon name="bell" size="18" />
            <span
              v-if="notifUnread > 0"
              class="admin-notification-badge absolute -right-1 -top-1"
            >
              {{ notifUnread > 99 ? "99+" : notifUnread }}
            </span>
          </button>
          <button
            class="inline-flex items-center gap-1.5 rounded-lg bg-surface-soft px-3 py-2 text-sm text-slate-700"
            @click="router.push('/admin/settings')"
          >
            <van-icon name="setting-o" size="18" />
            设置
          </button>
        </div>
      </div>
    </div>

    <!-- 今日工作摘要（Batch 04）：数字全部来自真实 API total，点击进入对应工作流 -->
    <div class="px-4 mt-3">
      <div class="grid grid-cols-4 gap-2">
        <button
          v-for="todo in workbenchTodos"
          :key="todo.key"
          class="rounded-2xl border border-default bg-surface px-2 py-3 text-center shadow-card"
          @click="openTodo(todo)"
        >
          <div
            class="price-highlight text-xl font-bold leading-6"
            :class="todo.count && todo.count > 0 ? (todo.status === 'warning' ? 'text-warning' : 'text-brand-800') : 'text-slate-300'"
          >
            {{ todo.count ?? 0 }}
          </div>
          <div class="mt-0.5 truncate text-[11px] text-muted">{{ todo.title }}</div>
        </button>
      </div>
    </div>

    <!-- 今日待办：打开就知道下一步该做什么（TodoCard 纯展示） -->
    <div class="px-4 mt-3">
      <TodoCard
        title="今日待办"
        :todos="workbenchTodos"
        @open="openTodo"
      />
    </div>

    <!-- 本月经营 -->
    <div v-if="roi" class="px-4 mt-3">
      <div class="rounded-2xl border border-default bg-surface p-4 shadow-card">
        <div class="flex items-center justify-between">
          <h3 class="font-bold text-primary">本月经营</h3>
          <span class="text-xs text-muted">{{ roi.month }}</span>
        </div>
        <div class="mt-3 grid grid-cols-3 gap-x-2 gap-y-4">
          <div>
            <div class="price-highlight text-xl font-bold text-primary">{{ roi.orders_imported }}</div>
            <div class="mt-0.5 text-xs text-muted">录单（条）</div>
          </div>
          <div>
            <div class="price-highlight text-xl font-bold text-primary">{{ roi.deals_completed }}</div>
            <div class="mt-0.5 text-xs text-muted">成交（单）</div>
          </div>
          <div>
            <div class="price-highlight text-xl font-bold text-success">{{ formatMoney(roi.net_amount) }}</div>
            <div class="mt-0.5 text-xs text-muted">净入账流水</div>
          </div>
          <div>
            <div class="price-highlight text-xl font-bold text-primary">{{ roi.applications_received }}</div>
            <div class="mt-0.5 text-xs text-muted">收到投递</div>
          </div>
          <div>
            <div class="price-highlight text-xl font-bold text-brand-800">{{ conversionText }}</div>
            <div class="mt-0.5 text-xs text-muted">投递成交率</div>
          </div>
          <div>
            <div class="price-highlight text-xl font-bold text-primary">{{ roi.teacher_pool }}</div>
            <div class="mt-0.5 text-xs text-muted">我的教员库</div>
          </div>
        </div>
        <div class="mt-3 text-[11px] leading-4 text-muted">
          净入账 = 定金 + 尾款 − 退款；投递成交率 = 成交 ÷ 收到投递；AI 录单本月已为你省去约 {{ formatSaved(savedMinutes) }} 手工录入
        </div>
      </div>
    </div>

    <!-- 快捷功能 -->
    <div class="px-4 mt-3">
      <div class="grid grid-cols-3 gap-3">
        <button
          v-for="action in quickActions"
          :key="action.key"
          class="order-card flex flex-col items-center gap-1.5 rounded-2xl border border-default bg-surface py-3.5 shadow-card"
          @click="goQuick(action)"
        >
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-800">
            <van-icon :name="action.icon" size="20" />
          </span>
          <span class="text-xs font-medium text-primary">{{ action.label }}</span>
        </button>
      </div>
    </div>

    <!-- 最近订单 -->
    <div class="px-4 mt-5">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold text-primary">最近订单</h3>
        <button class="text-sm font-medium text-brand-700" @click="router.push('/admin/orders')">
          查看全部 →
        </button>
      </div>

      <div v-if="recentOrders.length === 0" class="bg-surface rounded-2xl py-10 text-center text-muted shadow-card">
        <template v-if="loadError">
          数据加载失败
          <button class="ml-2 rounded-lg bg-surface-soft px-3 py-1 text-sm text-secondary" @click="loadData">
            重试
          </button>
        </template>
        <template v-else>暂无订单，去「AI 批量录单」导入吧</template>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="order in recentOrders"
          :key="order.id"
          class="order-card rounded-2xl border border-default bg-surface p-4 shadow-card"
          @click="router.push(`/admin/orders/${order.id}`)"
        >
          <div class="flex items-center justify-between">
            <div class="min-w-0">
              <div class="truncate font-semibold text-primary">{{ order.grade_subject }}</div>
              <div class="mt-1 truncate text-xs text-muted">{{ order.fuzzy_address }}</div>
            </div>
            <div class="shrink-0 text-right">
              <div class="price-highlight text-lg font-bold text-brand-800">¥{{ order.base_price }}</div>
              <div class="mt-1">
                <AppStatusBadge :status="order.status" />
              </div>
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
        <van-loading type="spinner" size="32" />
      </div>
    </van-overlay>
  </div>
</template>
