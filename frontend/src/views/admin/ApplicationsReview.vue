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
import type { ApplicationItem, OrderBrief } from "@/api/types";
import { applicationsApi } from "@/api/applications";
import ApplicationDetailDialog from "@/components/admin/ApplicationDetailDialog.vue";
import ApplicationCard from "@/components/admin/ApplicationCard.vue";
import TrialFailedPopup from "@/components/admin/TrialFailedPopup.vue";
import ReviewPopup from "@/components/admin/ReviewPopup.vue";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showSuccessToast, showConfirmDialog } from "vant";

const router = useRouter();
const route = useRoute();
const orders = ref<OrderBrief[]>([]);
const applications = ref<ApplicationItem[]>([]);
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

// 快捷拉黑：仅限制本租户，联动刷新列表
// 仅招聘中的订单可恢复被误拒的投递；已完成/已归档订单的落选属于终态
const canRestore = computed(
  () => orders.value.find((o) => o.id === selectedOrderId.value)?.status === "recruiting",
);

// 左栏订单状态筛选
type OrderFilter = "all" | "recruiting" | "trial_in_progress" | "completed";
const orderFilter = ref<OrderFilter>("all");
const filterOptions: { key: OrderFilter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "recruiting", label: "招聘中" },
  { key: "trial_in_progress", label: "试课中" },
  { key: "completed", label: "已成交" },
];

const visibleOrders = computed(() =>
  orderFilter.value === "all"
    ? orders.value
    : orders.value.filter((o) => o.status === orderFilter.value)
);

function sortOrders() {
  // 未完成的排前面；同层按待处理投递数降序；再按发布时间新到旧
  orders.value.sort((left, right) => {
    const leftDone = left.status === "completed" ? 1 : 0;
    const rightDone = right.status === "completed" ? 1 : 0;
    if (leftDone !== rightDone) return leftDone - rightDone;
    const byCount = applicationCount(right.id) - applicationCount(left.id);
    if (byCount !== 0) return byCount;
    const leftTime = left.created_at ? new Date(left.created_at).getTime() : 0;
    const rightTime = right.created_at ? new Date(right.created_at).getTime() : 0;
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

async function loadOrders() {
  loading.value = true;
  try {
    // 活跃订单之外再拉已成交订单，成交后仍可在本页回查投递记录
    const [res, doneRes, summary] = await Promise.all([
      ordersApi.listOrders(1, 50),
      ordersApi.listOrders(1, 50, "completed").catch(() => ({ items: [] as OrderBrief[] })),
      applicationsApi.summary().catch(() => null),
    ]);
    applicationCountByOrder.value = summary?.order_counts || {};
    applicationTotal.value = Number(summary?.total_applications || 0);
    orders.value = [...(res.items || []), ...(doneRes.items || [])];
    sortOrders();
  } catch {
    // 主请求失败时明确提示，避免左栏被误读为"暂无订单"
    showToast("加载订单失败，请稍后重试");
  } finally {
    loading.value = false;
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
    const summary = await applicationsApi.summary();
    applicationCountByOrder.value = summary?.order_counts || {};
    applicationTotal.value = Number(summary?.total_applications || 0);
    sortOrders();
  } catch {
    // 保留当前角标，避免短暂网络波动清空提醒。
  }
}

async function selectOrder(orderId: number) {
  selectedOrderId.value = orderId;
  try {
    applications.value = await applicationsApi.listByOrder(orderId);
  } catch {
    showToast("加载投递列表失败");
  }
}

async function refreshSelected() {
  if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
}

/** 动作统一编排：确认弹窗文案 + API + 刷新（pendingSummary 控制左栏角标是否联动） */
async function runAction(
  appId: number,
  apiCall: (id: number) => Promise<unknown>,
  confirm: { title: string; message: string; confirmButtonText?: string },
  { refreshPending = false, successToast = "操作成功" as string | null } = {},
) {
  try {
    await showConfirmDialog({ ...confirm });
  } catch {
    return; // 用户取消确认弹窗（vant 以 "cancel"/"overlay" reject），静默返回
  }
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
  }, { refreshPending: true, successToast: "已拒绝该投递" });

const handleForfeit = (appId: number) =>
  runAction(appId, applicationsApi.forfeit, {
    title: "没收定金？",
    message: "确认教员违约后，已交定金/尾款将登记为没收收入，订单重新开放。此操作不可撤销。",
    confirmButtonText: "确认没收",
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
        <div class="sticky top-0 z-10 flex gap-1 border-b bg-white px-1.5 py-1.5">
          <button
            v-for="opt in filterOptions"
            :key="opt.key"
            class="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
            :class="orderFilter === opt.key ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-500'"
            @click="orderFilter = opt.key"
          >
            {{ opt.label }}
          </button>
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
            </div>
          </div>
          <div
            v-if="visibleOrders.length === 0"
            class="p-4 text-gray-400 text-xs text-center"
          >
            该状态下暂无订单
          </div>
        </template>
      </div>

      <!-- 右侧投递详情 -->
      <div class="flex-1 overflow-y-auto p-3">
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
    <AdminTabbar :application-count="applicationTotal" />
  </div>
</template>
