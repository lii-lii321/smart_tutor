<script setup lang="ts">
/**
 * 投递审核主页面：左栏订单列表 + 右栏投递卡片。
 * 卡片展示与三个弹层拆分至 components/admin/（ApplicationCard/TrialFailedPopup/ReviewPopup），
 * 本页只保留数据加载与动作编排（操作后刷新当前投递与待处理角标）。
 */
import { ref, computed, onMounted } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import type { ApplicationItem, ApplicationSummaryResponse, OrderBrief } from "@/api/types";
import { applicationsApi } from "@/api/applications";
import TeacherMatchPopup from "@/components/admin/TeacherMatchPopup.vue";
import ApplicationDetailDialog from "@/components/admin/ApplicationDetailDialog.vue";
import ApplicationCard from "@/components/admin/ApplicationCard.vue";
import TrialFailedPopup from "@/components/admin/TrialFailedPopup.vue";
import ReviewPopup from "@/components/admin/ReviewPopup.vue";
import AppButton from "@/components/ui/AppButton.vue";
import { appConfirm } from "@/composables/appConfirm";
import { formatMoney, parseDbTime } from "@/utils/format";
import { usePagedList } from "@/composables/usePagedList";
import AdminShell from "@/components/admin/AdminShell.vue";
import OrderStageBar from "@/components/business/OrderStageBar.vue";
import { showToast, showSuccessToast } from "vant";
import { useSmartBack } from "@/composables/useSmartBack";

const router = useRouter();
const route = useRoute();
const { goBack } = useSmartBack("/admin/dashboard");
const orders = ref<OrderBrief[]>([]);
const selectedOrderId = ref<number | null>(null);
const loading = ref(true);
// 左栏首屏失败必须与"该状态下暂无订单"空态可区分：显式错误态 + 重试（MyApplications C3 范式）
const ordersLoadError = ref(false);
const applicationCountByOrder = ref<Record<number, number>>({});
const applicationTotal = ref(0);
const detailApplication = ref<ApplicationItem | null>(null);
const detailVisible = ref(false);
const trialFormVisible = ref(false);
const trialFormApp = ref<ApplicationItem | null>(null);
const reviewVisible = ref(false);
const reviewApp = ref<ApplicationItem | null>(null);

// 左栏拆"待办 / 历史"两个视图：待办=招聘中+试课中（工作队列），
// 已成交/已归档沉到"历史"里回查，不再混在工作队列垫底。
const viewMode = ref<"todo" | "history">("todo");
type OrderFilter = "all" | "recruiting" | "trial_in_progress" | "completed" | "archived";
const orderFilter = ref<OrderFilter>("all");
const todoFilterOptions = [
  { key: "all", label: "全部" },
  { key: "recruiting", label: "招聘中" },
  { key: "trial_in_progress", label: "试课中" },
] as const;
const historyFilterOptions = [
  { key: "completed", label: "已成交" },
  { key: "archived", label: "已归档" },
] as const;
const activeFilterOptions = computed(() =>
  viewMode.value === "todo" ? todoFilterOptions : historyFilterOptions
);

const LEFT_PAGE_SIZE = 50;
// todo: 只有一个来源；history: 已成交 + 已归档 两个来源各自翻页
const primaryLoaded = ref(0);
const primaryTotal = ref(0);
const secondaryLoaded = ref(0);
const secondaryTotal = ref(0);
const loadingMore = ref(false);
const hasMoreOrders = computed(() =>
  viewMode.value === "todo"
    ? primaryLoaded.value < primaryTotal.value
    : primaryLoaded.value < primaryTotal.value || secondaryLoaded.value < secondaryTotal.value
);

// 紧迫度（用户口径：一周没反应才算急，不按天）：
// 最后反应时间 = max(创建, 最近重发, 最新待审投递)
// 🔴 急：没反应 ≥ 7 天，或距过期 ≤ 24h；🟡 滞留：没反应 ≥ 5 天；🟢 正常
const lastApplicationAt = ref<Record<string, string | null>>({});
type Urgency = "urgent" | "stale" | "normal";
const URGENCY_RANK: Record<Urgency, number> = { urgent: 0, stale: 1, normal: 2 };

function urgencyOf(order: OrderBrief): Urgency {
  if (order.status !== "recruiting") return "normal";
  const now = Date.now();
  const times = [
    order.created_at,
    order.expiry_refreshed_at,
    lastApplicationAt.value[String(order.id)],
  ]
    .filter(Boolean)
    .map((t) => parseDbTime(t as string).getTime())
    .filter((t) => Number.isFinite(t));
  const last = times.length ? Math.max(...times) : now;
  const staleDays = (now - last) / 86400000;
  const hoursToExpiry = order.expired_at
    ? (parseDbTime(order.expired_at).getTime() - now) / 3600000
    : Infinity;
  if (staleDays >= 7 || hoursToExpiry <= 24) return "urgent";
  if (staleDays >= 5) return "stale";
  return "normal";
}

/** 沉寂单：招聘中 + 无待审投递 + 超 DORMANT_AFTER_DAYS 天没有任何反应。
 *  折叠进列表底部（可展开），不再挤占日常工作面；重录唤醒/新投递会自动让它离开沉寂组。
 *  2026-10-03 用户拍板 3 天→2 周：与订单有效期（ORDER_EXPIRE_HOURS=336，14 天）同口径，
 *  即"挂满整个生命周期都没人问才沉寂"，沉寂组几乎等于临期组。 */
const DORMANT_AFTER_DAYS = 14;
const dormantCollapsed = ref(true);

function lastActivityTime(order: OrderBrief): number {
  const times = [
    order.created_at,
    order.expiry_refreshed_at,
    lastApplicationAt.value[String(order.id)],
  ]
    .filter(Boolean)
    .map((t) => parseDbTime(t as string).getTime())
    .filter((t) => Number.isFinite(t));
  return times.length ? Math.max(...times) : Date.now();
}

function isDormant(order: OrderBrief): boolean {
  if (order.status !== "recruiting") return false;
  if (applicationCount(order.id) > 0) return false;
  return (Date.now() - lastActivityTime(order)) / 86400000 >= DORMANT_AFTER_DAYS;
}

const dormantOrders = computed(() => visibleOrders.value.filter(isDormant));
const activeOrders = computed(() => visibleOrders.value.filter((o) => !isDormant(o)));

// 右栏投递分页：热门订单投递数会破百，按页加载；
// 加载更多/去重/到底收敛到 usePagedList（热门单跨页重复返回时不再渲染重复卡片）
const APP_PAGE_SIZE = 100;
const appList = usePagedList<ApplicationItem>(
  (page, pageSize) => {
    if (!selectedOrderId.value) return Promise.resolve({ items: [] });
    return applicationsApi
      .listByOrder(selectedOrderId.value, page, pageSize)
      .then((list) => ({ items: list }));
  },
  { pageSize: APP_PAGE_SIZE }
);
const {
  items: applications,
  loading: appLoading,
  loadingMore: appLoadingMore,
  hasMore: appHasMore,
  load: loadApplications,
  loadMore: loadMoreApplicationsRaw,
} = appList;

async function loadMoreApplications() {
  try {
    await loadMoreApplicationsRaw();
  } catch {
    showToast("加载更多失败，请稍后重试");
  }
}

// 订单找教员（一期）：选中招聘中订单后可主动邀约
const selectedOrder = computed(
  () => orders.value.find((o) => o.id === selectedOrderId.value) || null
);
const matchVisible = ref(false);

// 快捷拉黑：仅限制本租户，联动刷新列表
// 仅招聘中的订单可恢复被误拒的投递；已完成/已归档订单的落选属于终态
const canRestore = computed(
  () => orders.value.find((o) => o.id === selectedOrderId.value)?.status === "recruiting",
);

const visibleOrders = computed(() =>
  orderFilter.value === "all"
    ? orders.value
    : orders.value.filter((o) => o.status === orderFilter.value)
);

function sortOrders() {
  orders.value.sort((left, right) => {
    if (viewMode.value === "todo") {
      // 急单置顶凸显 → 待处理角标多优先 → 发布时间新到旧
      const ur = URGENCY_RANK[urgencyOf(left)] - URGENCY_RANK[urgencyOf(right)];
      if (ur !== 0) return ur;
      const byCount = applicationCount(right.id) - applicationCount(left.id);
      if (byCount !== 0) return byCount;
    } else {
      const lc = left.status === "completed" ? 0 : 1;
      const rc = right.status === "completed" ? 0 : 1;
      if (lc !== rc) return lc - rc;
    }
    const leftTime = left.created_at ? parseDbTime(left.created_at).getTime() : 0;
    const rightTime = right.created_at ? parseDbTime(right.created_at).getTime() : 0;
    return rightTime - leftTime;
  });
}

onMounted(async () => {
  await loadOrders();
  // 支持通知"去处理"直达：/admin/applications?order=123 自动选中该订单
  const targetOrderId = Number(route.query.order);
  if (Number.isFinite(targetOrderId) && targetOrderId > 0) {
    await selectOrder(targetOrderId);
  }
});

function applySummary(summary: ApplicationSummaryResponse | null) {
  applicationCountByOrder.value = summary?.order_counts || {};
  applicationTotal.value = Number(summary?.total_applications || 0);
  lastApplicationAt.value = summary?.last_application_at || {};
}

function switchMode(mode: "todo" | "history") {
  if (viewMode.value === mode) return;
  viewMode.value = mode;
  orderFilter.value = mode === "todo" ? "all" : "completed";
  loadOrders();
}

async function loadOrders() {
  loading.value = true;
  try {
    const summaryPromise = applicationsApi.summary().catch(() => null);
    if (viewMode.value === "todo") {
      const [res, summary] = await Promise.all([
        ordersApi.listOrders(1, LEFT_PAGE_SIZE),
        summaryPromise,
      ]);
      applySummary(summary);
      primaryLoaded.value = res.items?.length || 0;
      primaryTotal.value = Number(res.total || 0);
      secondaryLoaded.value = 0;
      secondaryTotal.value = 0;
      orders.value = [...(res.items || [])];
    } else {
      const [doneRes, archRes, summary] = await Promise.all([
        ordersApi.listOrders(1, LEFT_PAGE_SIZE, "completed"),
        ordersApi.listOrders(1, LEFT_PAGE_SIZE, "archived").catch(() => ({ items: [] as OrderBrief[], total: 0 })),
        summaryPromise,
      ]);
      applySummary(summary);
      primaryLoaded.value = doneRes.items?.length || 0;
      primaryTotal.value = Number(doneRes.total || 0);
      secondaryLoaded.value = archRes.items?.length || 0;
      secondaryTotal.value = Number(archRes.total || 0);
      orders.value = [...(doneRes.items || []), ...(archRes.items || [])];
    }
    sortOrders();
    ordersLoadError.value = false;
  } catch {
    // 主请求失败时明确提示，避免左栏被误读为"暂无订单"
    ordersLoadError.value = true;
    showToast("加载订单失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function loadMoreOrders() {
  if (loadingMore.value || !hasMoreOrders.value) return;
  loadingMore.value = true;
  try {
    const fetched: OrderBrief[] = [];
    if (viewMode.value === "todo") {
      const page = Math.floor(primaryLoaded.value / LEFT_PAGE_SIZE) + 1;
      const res = await ordersApi.listOrders(page, LEFT_PAGE_SIZE);
      primaryLoaded.value += res.items?.length || 0;
      fetched.push(...(res.items || []));
    } else {
      if (primaryLoaded.value < primaryTotal.value) {
        const page = Math.floor(primaryLoaded.value / LEFT_PAGE_SIZE) + 1;
        const res = await ordersApi.listOrders(page, LEFT_PAGE_SIZE, "completed");
        primaryLoaded.value += res.items?.length || 0;
        fetched.push(...(res.items || []));
      }
      if (secondaryLoaded.value < secondaryTotal.value) {
        const page = Math.floor(secondaryLoaded.value / LEFT_PAGE_SIZE) + 1;
        const res = await ordersApi.listOrders(page, LEFT_PAGE_SIZE, "archived");
        secondaryLoaded.value += res.items?.length || 0;
        fetched.push(...(res.items || []));
      }
    }
    orders.value.push(...fetched);
    sortOrders();
  } catch {
    showToast("加载更多失败，请稍后重试");
  } finally {
    loadingMore.value = false;
  }
}

function applicationCount(orderId: number) {
  return Number(applicationCountByOrder.value[orderId] || 0);
}

async function onBlacklisted() {
  await refreshSelected();
}

async function refreshPendingSummary() {
  try {
    applySummary(await applicationsApi.summary());
    sortOrders();
  } catch {
    // 保留当前角标，避免短暂网络波动清空提醒。
  }
}

async function selectOrder(orderId: number) {
  selectedOrderId.value = orderId;
  try {
    await loadApplications();
  } catch {
    showToast("加载投递列表失败");
  }
}

async function refreshSelected() {
  if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
}

// F2 动作防重：记录 in-flight 的投递卡，动作期间禁用该卡全部按钮；不同卡互不阻塞
const actingAppIds = ref<number[]>([]);

/** 动作统一编排：底部确认弹窗 + API + 刷新（pendingSummary 控制左栏角标是否联动） */
async function runAction(
  appId: number,
  apiCall: (id: number) => Promise<unknown>,
  confirm: { title: string; message: string; confirmButtonText?: string; danger?: boolean },
  { refreshPending = false, successToast = "操作成功" as string | null } = {},
) {
  if (actingAppIds.value.includes(appId)) return;
  actingAppIds.value = [...actingAppIds.value, appId];
  try {
    const ok = await appConfirm({
      title: confirm.title,
      message: confirm.message,
      confirmText: confirm.confirmButtonText,
      danger: confirm.danger,
    });
    if (!ok) return; // 用户在底部弹层取消
    await apiCall(appId);
    if (successToast) showSuccessToast(successToast);
    // 多数动作会推进订单本身的状态（开始试课/确认完成/试课失败回收…），
    // 左栏列表与订单状态机横条读的是 orders 缓存，必须一并重拉，否则显示滞后；
    // 刷新期间旧列表保持渲染（usePagedList 拉到新数据才整体替换），不闪骨架/空态
    await Promise.all([refreshSelected(), loadOrders()]);
    if (refreshPending) await refreshPendingSummary();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  } finally {
    actingAppIds.value = actingAppIds.value.filter((id) => id !== appId);
  }
}

const handleShortlist = (appId: number) =>
  runAction(appId, applicationsApi.shortlist, {
    title: "加入候选队列？",
    message: "教员将进入该订单的候选排队，等待线下定金收取后确认。",
    confirmButtonText: "加入候选",
  }, { refreshPending: true, successToast: "已加入候选队列" });

const handleStartTrial = (appId: number) => {
  const target = applications.value.find((a) => a.id === appId);
  return runAction(appId, applicationsApi.startTrial, {
    title: "开始试课？",
    message: `开始后「${target?.teacher?.name || "该教员"}」将解锁家长联系方式，订单进入试课中。`,
    confirmButtonText: "开始试课",
  }, { refreshPending: true, successToast: "已开始试课" });
};

const handleRestore = (appId: number) => {
  const target = applications.value.find((a) => a.id === appId);
  return runAction(appId, applicationsApi.restore, {
    title: "恢复为待审核？",
    message: `「${target?.teacher?.name || "该教员"}」的投递将回到待审核列表（仅限未产生资金往来的误拒绝）。`,
    confirmButtonText: "恢复待审核",
  }, { refreshPending: true, successToast: "已恢复为待审核" });
};

// F1：资金动作确认统一口径——点名教员 + fee 快照金额；金额只读投递响应的 fee 字段，
// 缺快照（含未取到投递）降级为只点名教员不显示金额，前端绝不复算。
const handleConfirmDeposit = (appId: number) => {
  const target = applications.value.find((a) => a.id === appId);
  const deposit = target?.fee ? ` ${formatMoney(target.fee.deposit)}` : "";
  return runAction(appId, applicationsApi.confirmDeposit, {
    title: "确认定金？",
    message: `将为「${target?.teacher?.name || "该教员"}」的投递确认定金${deposit}，生成一条定金收入流水`,
  }, { successToast: "定金已确认" });
};

const handleConfirmBalance = (appId: number) => {
  const target = applications.value.find((a) => a.id === appId);
  const balance = target?.fee ? ` ${formatMoney(target.fee.balance)}` : "";
  return runAction(appId, applicationsApi.confirmBalance, {
    title: "确认尾款？",
    message: `将为「${target?.teacher?.name || "该教员"}」的投递确认尾款${balance}，生成一条尾款收入流水`,
  }, { successToast: "尾款已确认" });
};

const handleComplete = (appId: number) => {
  const target = applications.value.find((a) => a.id === appId);
  const totalFee = target?.fee ? `，信息费合计 ${formatMoney(target.fee.total_info_fee)}` : "";
  return runAction(appId, applicationsApi.complete, {
    title: "确认完成？",
    message: `将为「${target?.teacher?.name || "该教员"}」的投递确认完成${totalFee}，订单将标记为已完成`,
  }, { successToast: "订单已完成" });
};

const handleReject = (appId: number) =>
  runAction(appId, applicationsApi.reject, {
    title: "拒绝该投递？",
    message: "拒绝后教员会从待处理列表移除，且无法再对该订单操作。",
    confirmButtonText: "确认拒绝",
    danger: true,
  }, { refreshPending: true, successToast: "已拒绝该投递" });

const handleForfeit = (appId: number) => {
  const target = applications.value.find((a) => a.id === appId);
  const fee = target?.fee;
  // 没收范围随投递状态而变（已付尾款则一并没收）：分开点名两项快照金额，不做加总复算
  const scope =
    fee && target?.status === "balance_paid"
      ? `（定金 ${formatMoney(fee.deposit)}、尾款 ${formatMoney(fee.balance)}）`
      : fee
        ? `（定金 ${formatMoney(fee.deposit)}）`
        : "";
  return runAction(appId, applicationsApi.forfeit, {
    title: "没收定金？",
    message: `确认教员违约后，将为「${target?.teacher?.name || "该教员"}」的投递登记没收收入${scope}，订单重新开放。此操作不可撤销。`,
    confirmButtonText: "确认没收",
    danger: true,
  }, { successToast: "已没收信息费" });
};

function handleTrialFailed(appId: number) {
  const target = applications.value.find((a) => a.id === appId);
  if (!target) return;
  trialFormApp.value = target;
  trialFormVisible.value = true;
}

function openReview(app: ApplicationItem) {
  reviewApp.value = app;
  reviewVisible.value = true;
}

function openApplicationDetail(application: ApplicationItem) {
  detailApplication.value = application;
  detailVisible.value = true;
}
</script>

<template>
  <AdminShell fluid>
    <van-nav-bar
      title="投递审核"
      left-arrow
      @click-left="goBack"
    />

    <div class="mx-auto w-full max-w-5xl flex h-[calc(100vh-96px)] lg:h-[calc(100vh-128px)] lg:max-w-none lg:gap-4 lg:px-6 lg:pt-4">
      <!-- 左侧订单列表 -->
      <div class="w-40 shrink-0 bg-surface border-r border-default overflow-y-auto lg:w-64 lg:rounded-2xl lg:border lg:shadow-card">
        <!-- 待办 / 历史 视图切换 + 状态筛选 -->
        <div class="sticky top-0 z-10 bg-white border-b">
          <div class="flex border-b border-default">
            <button
              class="flex-1 py-2 text-xs font-medium"
              :class="viewMode === 'todo' ? 'border-b-2 border-brand-800 text-brand-800' : 'text-muted'"
              @click="switchMode('todo')"
            >
              待办
            </button>
            <button
              class="flex-1 py-2 text-xs font-medium"
              :class="viewMode === 'history' ? 'border-b-2 border-brand-800 text-brand-800' : 'text-muted'"
              @click="switchMode('history')"
            >
              历史
            </button>
          </div>
          <div class="flex gap-1 px-1.5 py-1.5">
            <button
              v-for="opt in activeFilterOptions"
              :key="opt.key"
              class="shrink-0 rounded-full px-1.5 py-0.5 text-caption font-medium"
              :class="orderFilter === opt.key ? 'bg-brand-800 text-white' : 'bg-surface-soft text-secondary'"
              @click="orderFilter = opt.key"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
        <!-- 首屏骨架：仅无数据时占位；动作后的重拉保持旧列表渲染，不再整栏闪骨架 -->
        <template v-if="loading && orders.length === 0">
          <div
            v-for="i in 3"
            :key="`sk-${i}`"
            class="border-b p-3"
          >
            <van-skeleton
              title
              :row="1"
              title-width="70%"
            />
          </div>
        </template>
        <!-- 首屏失败：独立错误态，与"该状态下暂无订单"严格区分 -->
        <template v-else-if="ordersLoadError && orders.length === 0">
          <div class="p-4 pt-8 text-center">
            <van-icon name="warning-o" size="36" class="text-muted" />
            <p class="mt-3 text-xs font-medium text-primary">订单列表加载失败</p>
            <p class="mt-1 text-caption leading-5 text-muted">网络或服务暂时不可用，重试不会影响已有数据</p>
            <div class="mt-4">
              <AppButton size="sm" @click="loadOrders">重新加载</AppButton>
            </div>
          </div>
        </template>
        <template v-else>
          <div
            v-for="order in activeOrders"
            :key="order.id"
            class="relative p-3 text-xs border-b cursor-pointer"
            :class="selectedOrderId === order.id ? 'bg-brand-50 text-brand-800 font-semibold' : 'text-secondary'"
            @click="selectOrder(order.id)"
          >
            <!-- 紧迫度角标：一周没反应/临期凸显 -->
            <span
              v-if="viewMode === 'todo' && urgencyOf(order) === 'urgent'"
              class="absolute left-0.5 top-0.5 rounded bg-danger px-0.5 text-caption font-bold text-white"
            >急</span>
            <span
              v-else-if="viewMode === 'todo' && urgencyOf(order) === 'stale'"
              class="absolute left-0.5 top-0.5 rounded bg-warning-deep px-0.5 text-caption font-bold text-white"
            >滞</span>
            <span
              v-if="applicationCount(order.id)"
              class="admin-notification-badge absolute right-2 top-2"
            >{{ applicationCount(order.id) > 99 ? "99+" : applicationCount(order.id) }}</span>
            <div class="truncate pr-5">
              {{ order.grade_subject }}
            </div>
            <div class="text-muted text-caption mt-0.5 truncate">
              {{ order.raw_id }}
              <span
                v-if="order.status === 'completed'"
                class="font-medium text-success-deep"
              >· 已成交</span>
              <span
                v-else-if="order.status === 'archived'"
                class="font-medium text-muted"
              >· 已归档</span>
            </div>
          </div>

          <!-- 沉寂订单折叠组：无待审投递且超 3 天没反应的单，不再挤占日常工作面；
               重录唤醒/新投递会自动让它离开本组 -->
          <div v-if="dormantOrders.length">
            <button
              class="flex w-full items-center justify-between px-3 py-2 text-caption text-muted"
              @click="dormantCollapsed = !dormantCollapsed"
            >
              <span>沉寂订单（{{ dormantOrders.length }}）· 无投递超 {{ DORMANT_AFTER_DAYS }} 天</span>
              <van-icon :name="dormantCollapsed ? 'arrow-down' : 'arrow-up'" size="11" />
            </button>
            <template v-if="!dormantCollapsed">
              <div
                v-for="order in dormantOrders"
                :key="order.id"
                class="relative p-3 text-xs border-b cursor-pointer opacity-60"
                :class="selectedOrderId === order.id ? 'bg-brand-50 text-brand-800 font-semibold' : 'text-secondary'"
                @click="selectOrder(order.id)"
              >
                <span
                  v-if="applicationCount(order.id)"
                  class="admin-notification-badge absolute right-2 top-2"
                >{{ applicationCount(order.id) > 99 ? "99+" : applicationCount(order.id) }}</span>
                <div class="truncate pr-5">
                  {{ order.grade_subject }}
                </div>
                <div class="text-muted text-caption mt-0.5 truncate">{{ order.raw_id }}</div>
              </div>
            </template>
          </div>

          <div
            v-if="activeOrders.length === 0 && dormantOrders.length === 0"
            class="p-4 text-muted text-xs text-center"
          >
            该状态下暂无订单
          </div>
          <button
            v-else-if="hasMoreOrders"
            class="w-full py-2 text-center text-xs text-brand-800 disabled:opacity-50"
            :disabled="loadingMore"
            @click="loadMoreOrders"
          >
            {{ loadingMore ? "加载中..." : "加载更多订单" }}
          </button>
        </template>
      </div>

      <!-- 右侧投递详情 -->
      <div class="flex-1 overflow-y-auto p-3 lg:rounded-2xl lg:border lg:border-default lg:bg-surface lg:shadow-card">
        <!-- 订单上下文条 + 常驻状态机：中介随时知道这单处在哪一环、
             手里这单值多少钱。整条可点 → 订单工作区（完整详情 + 编辑订单信息） -->
        <div
          v-if="selectedOrder"
          class="mb-3 border-b border-default pb-3"
        >
          <div
            class="group -mx-1 flex cursor-pointer items-start justify-between gap-3 rounded-xl px-1 py-1 transition-colors hover:bg-surface-soft"
            title="点击进入订单工作区：查看完整信息 / 编辑"
            @click="router.push(`/admin/orders/${selectedOrder.id}`)"
          >
            <div class="min-w-0">
              <div class="flex items-baseline gap-2">
                <span class="mono text-caption text-muted">#{{ selectedOrder.raw_id }}</span>
                <span class="truncate text-emphasis font-bold text-primary">
                  {{ selectedOrder.grade_subject }}
                </span>
              </div>
              <div class="mt-1 flex flex-wrap items-center gap-x-3 text-caption text-muted">
                <span class="truncate">{{ selectedOrder.fuzzy_address }}</span>
                <span v-if="selectedOrder.weekly_frequency">每周 {{ selectedOrder.weekly_frequency }} 次</span>
                <span v-if="selectedOrder.price_total">{{ selectedOrder.price_total }}</span>
              </div>
              <div class="mt-1 text-caption font-medium text-link">
                查看完整信息 / 编辑订单 →
              </div>
            </div>
            <div class="shrink-0 text-right">
              <div class="text-caption text-muted">信息费</div>
              <div class="price-highlight text-xl font-bold leading-tight text-brand-800">
                ¥{{ selectedOrder.calculated_info_fee }}
              </div>
            </div>
          </div>
          <div class="mt-2.5">
            <OrderStageBar :status="selectedOrder.status" />
          </div>
        </div>

        <!-- 找教员（一期）：滞留订单主动邀约，选中招聘中订单时可用 -->
        <div
          v-if="selectedOrder && selectedOrder.status === 'recruiting'"
          class="mb-2 flex justify-end"
        >
          <button
            class="inline-flex items-center gap-1.5 rounded-lg border border-default px-3 py-1.5 text-xs font-medium text-secondary transition-colors hover:bg-surface-soft"
            @click="matchVisible = true"
          >
            <van-icon name="search" size="13" />
            找教员
          </button>
        </div>

        <div
          v-if="!selectedOrderId"
          class="text-center py-20 text-muted text-sm"
        >
          ← 选择左侧订单查看投递
        </div>

        <!-- 切单加载中：无旧内容可保留时行内转圈，不闪"暂无投递" -->
        <div
          v-else-if="appLoading && applications.length === 0"
          class="flex justify-center py-20"
        >
          <van-loading color="var(--st-text-secondary)" />
        </div>

        <div
          v-else-if="applications.length === 0"
          class="text-center py-20 text-muted text-sm"
        >
          暂无投递
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <ApplicationCard
            v-for="app in applications"
            :key="app.id"
            :app="app"
            :can-restore="canRestore"
            :busy="actingAppIds.includes(app.id)"
            @open-detail="openApplicationDetail"
            @shortlist="handleShortlist"
            @reject="handleReject"
            @confirm-deposit="handleConfirmDeposit"
            @start-trial="handleStartTrial"
            @trial-failed="handleTrialFailed"
            @confirm-balance="handleConfirmBalance"
            @complete="handleComplete"
            @forfeit="handleForfeit"
            @review="openReview"
            @restore="handleRestore"
          />
          <button
            v-if="appHasMore"
            class="w-full rounded-lg border border-default bg-white py-2 text-center text-xs text-brand-800 disabled:opacity-50"
            :disabled="appLoadingMore"
            @click="loadMoreApplications"
          >
            {{ appLoadingMore ? "加载中..." : "加载更多投递" }}
          </button>
        </div>
      </div>
    </div>

    <ReviewPopup
      v-model:show="reviewVisible"
      :app="reviewApp"
      @submitted="refreshSelected"
    />

    <ApplicationDetailDialog
      v-model:show="detailVisible"
      :application="detailApplication"
      @blacklisted="onBlacklisted"
    />

    <TrialFailedPopup
      v-model:show="trialFormVisible"
      :app="trialFormApp"
      @confirmed="refreshSelected"
    />

    <TeacherMatchPopup
      v-model:show="matchVisible"
      :order-id="selectedOrderId"
      :subject="selectedOrder?.grade_subject || ''"
    />

  </AdminShell>
</template>
