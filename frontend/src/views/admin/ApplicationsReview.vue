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
import { appConfirm } from "@/composables/appConfirm";
import { parseDbTime } from "@/utils/format";
import { usePagedList } from "@/composables/usePagedList";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showSuccessToast } from "vant";

const router = useRouter();
const route = useRoute();
const orders = ref<OrderBrief[]>([]);
const selectedOrderId = ref<number | null>(null);
const loading = ref(true);
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
  } catch {
    // 主请求失败时明确提示，避免左栏被误读为"暂无订单"
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

/** 动作统一编排：底部确认弹窗 + API + 刷新（pendingSummary 控制左栏角标是否联动） */
async function runAction(
  appId: number,
  apiCall: (id: number) => Promise<unknown>,
  confirm: { title: string; message: string; confirmButtonText?: string; danger?: boolean },
  { refreshPending = false, successToast = "操作成功" as string | null } = {},
) {
  const ok = await appConfirm({
    title: confirm.title,
    message: confirm.message,
    confirmText: confirm.confirmButtonText,
    danger: confirm.danger,
  });
  if (!ok) return; // 用户在底部弹层取消
  try {
    await apiCall(appId);
    if (successToast) showSuccessToast(successToast);
    await refreshSelected();
    if (refreshPending) await refreshPendingSummary();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
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

const handleConfirmDeposit = (appId: number) =>
  runAction(appId, applicationsApi.confirmDeposit, {
    title: "确认定金？",
    message: "确认后会生成一条定金收入流水",
  }, { successToast: "定金已确认" });

const handleConfirmBalance = (appId: number) =>
  runAction(appId, applicationsApi.confirmBalance, {
    title: "确认尾款？",
    message: "确认后会生成一条尾款收入流水",
  }, { successToast: "尾款已确认" });

const handleComplete = (appId: number) =>
  runAction(appId, applicationsApi.complete, {
    title: "确认完成？",
    message: "订单将标记为已完成",
  }, { successToast: "订单已完成" });

const handleReject = (appId: number) =>
  runAction(appId, applicationsApi.reject, {
    title: "拒绝该投递？",
    message: "拒绝后教员会从待处理列表移除，且无法再对该订单操作。",
    confirmButtonText: "确认拒绝",
    danger: true,
  }, { refreshPending: true, successToast: "已拒绝该投递" });

const handleForfeit = (appId: number) =>
  runAction(appId, applicationsApi.forfeit, {
    title: "没收定金？",
    message: "确认教员违约后，已交定金/尾款将登记为没收收入，订单重新开放。此操作不可撤销。",
    confirmButtonText: "确认没收",
    danger: true,
  }, { successToast: "已没收信息费" });

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
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar
      title="投递审核"
      left-arrow
      @click-left="router.push('/admin/dashboard')"
    />

    <div class="mx-auto w-full max-w-5xl flex h-[calc(100vh-96px)]">
      <!-- 左侧订单列表 -->
      <div class="w-40 shrink-0 bg-white border-r overflow-y-auto">
        <!-- 待办 / 历史 视图切换 + 状态筛选 -->
        <div class="sticky top-0 z-10 bg-white border-b">
          <div class="flex border-b border-gray-100">
            <button
              class="flex-1 py-2 text-xs font-medium"
              :class="viewMode === 'todo' ? 'border-b-2 border-primary-600 text-primary-600' : 'text-gray-400'"
              @click="switchMode('todo')"
            >
              待办
            </button>
            <button
              class="flex-1 py-2 text-xs font-medium"
              :class="viewMode === 'history' ? 'border-b-2 border-primary-600 text-primary-600' : 'text-gray-400'"
              @click="switchMode('history')"
            >
              历史
            </button>
          </div>
          <div class="flex gap-1 px-1.5 py-1.5">
            <button
              v-for="opt in activeFilterOptions"
              :key="opt.key"
              class="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
              :class="orderFilter === opt.key ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-500'"
              @click="orderFilter = opt.key"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
        <!-- 首屏骨架：订单列表加载中先占 3 行 -->
        <template v-if="loading">
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
        <template v-else>
          <div
            v-for="order in visibleOrders"
            :key="order.id"
            class="relative p-3 text-xs border-b cursor-pointer"
            :class="selectedOrderId === order.id ? 'bg-primary-50 text-primary-600 font-semibold' : 'text-gray-600'"
            @click="selectOrder(order.id)"
          >
            <!-- 紧迫度角标：一周没反应/临期凸显 -->
            <span
              v-if="viewMode === 'todo' && urgencyOf(order) === 'urgent'"
              class="absolute left-0.5 top-0.5 rounded bg-red-500 px-0.5 text-[9px] font-bold text-white"
            >急</span>
            <span
              v-else-if="viewMode === 'todo' && urgencyOf(order) === 'stale'"
              class="absolute left-0.5 top-0.5 rounded bg-amber-400 px-0.5 text-[9px] font-bold text-white"
            >滞</span>
            <span
              v-if="applicationCount(order.id)"
              class="admin-notification-badge absolute right-2 top-2"
            >{{ applicationCount(order.id) > 99 ? "99+" : applicationCount(order.id) }}</span>
            <div class="truncate pr-5">
              {{ order.grade_subject }}
            </div>
            <div class="text-gray-400 text-[10px] mt-0.5 truncate">
              {{ order.raw_id }}
              <span
                v-if="order.status === 'completed'"
                class="font-medium text-emerald-600"
              >· 已成交</span>
              <span
                v-else-if="order.status === 'archived'"
                class="font-medium text-gray-400"
              >· 已归档</span>
            </div>
          </div>
          <div
            v-if="visibleOrders.length === 0"
            class="p-4 text-gray-400 text-xs text-center"
          >
            该状态下暂无订单
          </div>
          <button
            v-else-if="hasMoreOrders"
            class="w-full py-2 text-center text-xs text-primary-600 disabled:opacity-50"
            :disabled="loadingMore"
            @click="loadMoreOrders"
          >
            {{ loadingMore ? "加载中..." : "加载更多订单" }}
          </button>
        </template>
      </div>

      <!-- 右侧投递详情 -->
      <div class="flex-1 overflow-y-auto p-3">
        <!-- 找教员（一期）：滞留订单主动邀约，选中招聘中订单时可用 -->
        <div
          v-if="selectedOrder && selectedOrder.status === 'recruiting'"
          class="mb-2 flex justify-end"
        >
          <button
            class="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-primary-600"
            @click="matchVisible = true"
          >
            🔍 找教员
          </button>
        </div>

        <div
          v-if="!selectedOrderId"
          class="text-center py-20 text-gray-400 text-sm"
        >
          ← 选择左侧订单查看投递
        </div>

        <div
          v-else-if="applications.length === 0"
          class="text-center py-20 text-gray-400 text-sm"
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
            class="w-full rounded-lg border border-gray-200 bg-white py-2 text-center text-xs text-primary-600 disabled:opacity-50"
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

    <AdminTabbar :application-count="applicationTotal" />
  </div>
</template>
