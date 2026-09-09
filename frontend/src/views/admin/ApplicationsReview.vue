<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import type { ApplicationItem, ApplicationStatus, OrderBrief } from "@/api/types";
import { applicationsApi } from "@/api/applications";
import { tenantsApi } from "@/api/tenants";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showSuccessToast, showConfirmDialog } from "vant";

// 投递状态文案（与本文件模板两处共用；后端加状态时此处同步）
const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  pending: "待审核",
  shortlisted: "候选排队",
  trial_in_progress: "正在试课",
  deposit_paid: "定金已付",
  balance_paid: "尾款已付",
  completed: "已成交",
  rejected: "已拒绝",
  refunded: "已退款",
  forfeited: "定金已没收",
};

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
const trialPaidByParent = ref<string>("");
const isTeacherViolated = ref(false);
const manualRefund = ref<string>("");

// 评价教员
const reviewVisible = ref(false);
const reviewApp = ref<ApplicationItem | null>(null);
const reviewRating = ref(5);
const reviewComment = ref("");
const reviewSubmitting = ref(false);

function openReview(app: ApplicationItem) {
  reviewApp.value = app;
  const rating = (app as { teacher?: { avg_rating?: number | null } }).teacher?.avg_rating;
  reviewRating.value = rating != null ? Math.round(rating) : 5;
  reviewComment.value = "";
  reviewVisible.value = true;
}

// 快捷拉黑：仅限制本租户，联动刷新列表
const blacklistTarget = ref<ApplicationItem | null>(null);

// 仅招聘中的订单可恢复被误拒的投递；已完成/已归档订单的落选属于终态
const canRestore = computed(
  () => orders.value.find((o) => o.id === selectedOrderId.value)?.status === "recruiting",
);

// ── 进度时间线：把投递各节点时间可视化为追踪轨迹 ──
function fmtFlowTime(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function daysSince(value?: string | null) {
  if (!value) return 0;
  return Math.max(1, Math.floor((Date.now() - new Date(value).getTime()) / 86400000));
}

type TimelineNode = {
  label: string;
  time: string | null;
  done: boolean;
  state: "done" | "current" | "pending" | "skipped" | "terminal";
};

const appTimeline = computed(() => {
  const app = detailApplication.value;
  if (!app) return [];
  const terminalMap: Record<string, { label: string; time: string | null }> = {
    rejected: { label: "已拒绝", time: app.rejected_at },
    refunded: { label: "已退款", time: app.refunded_at },
    forfeited: { label: "定金已没收", time: null },
  };
  const isTerminal = !!terminalMap[app.status];
  const nodes: TimelineNode[] = [
    { label: "投递简历", time: app.applied_at as string | null, done: true, state: "done" },
    { label: "进入候选", time: app.shortlisted_at, done: !!app.shortlisted_at, state: "pending" },
    { label: "确认定金", time: app.deposit_paid_at, done: !!app.deposit_paid_at, state: "pending" },
    // 试课没有独立时间戳：进行中标记为当前阶段
    { label: "开始试课", time: null, done: ["balance_paid", "completed"].includes(app.status), state: "pending" },
    { label: "确认尾款", time: app.balance_paid_at, done: !!app.balance_paid_at, state: "pending" },
    { label: "成交完成", time: app.status === "completed" ? app.balance_paid_at : null, done: app.status === "completed", state: "pending" },
  ];
  const result: TimelineNode[] = nodes.map((node, i) => {
    let state: TimelineNode["state"] = node.done ? "done" : "pending";
    if (isTerminal && !node.done) {
      state = "skipped";
    } else if (!node.done && nodes.slice(0, i).every((p) => p.done)) {
      state = "current";
    }
    return { ...node, state };
  });
  if (terminalMap[app.status]) {
    result.push({ ...terminalMap[app.status], done: true, state: "terminal" });
  }
  return result;
});

function nodeTimeLabel(node: { label: string; time: string | null; state: string }) {
  if (node.state === "current" && node.label === "开始试课") {
    const days = daysSince(detailApplication.value?.deposit_paid_at);
    return days ? `进行中 · 第 ${days} 天` : "进行中";
  }
  return node.time ? fmtFlowTime(node.time) : node.state === "skipped" ? "—" : "";
}

async function copyContact(text: string, message: string) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(message);
  } catch {
    showToast("复制失败，请手动复制");
  }
}

async function quickBlacklist(app: ApplicationItem) {
  blacklistTarget.value = app;
  try {
    await showConfirmDialog({
      title: "拉黑该教员？",
      message: `拉黑「${app.teacher?.name || `#${app.teacher_id}`}」后：其待审投递将被拒绝，且无法再投递本中介订单（仅对本中介生效）。`,
    });
  } catch {
    return;
  }
  try {
    await tenantsApi.blacklist(app.teacher_id, "审核页快捷拉黑");
    showSuccessToast("已拉黑");
    detailVisible.value = false;
    if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function submitReview() {
  if (!reviewApp.value) return;
  reviewSubmitting.value = true;
  try {
    await applicationsApi.review(reviewApp.value.id, reviewRating.value, reviewComment.value.trim() || undefined);
    showSuccessToast("评价已提交");
    reviewVisible.value = false;
    if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
  } catch (e) {
    showToast(getApiErrorMessage(e, "提交失败"));
  } finally {
    reviewSubmitting.value = false;
  }
}

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
  } finally {
    loading.value = false;
  }
}

function applicationCount(orderId: number) {
  return Number(applicationCountByOrder.value[orderId] || 0);
}

function openApplicationDetail(application: ApplicationItem) {
  detailApplication.value = application;
  detailVisible.value = true;
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

async function handleShortlist(appId: number) {
  try {
    await showConfirmDialog({
      title: "加入候选队列？",
      message: "教员将进入该订单的候选排队，等待线下定金收取后确认。",
      confirmButtonText: "加入候选",
    });
    await applicationsApi.shortlist(appId);
    showSuccessToast("已加入候选队列");
    if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
    await refreshPendingSummary();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleStartTrial(appId: number) {
  const target = applications.value.find((a) => a.id === appId);
  try {
    await showConfirmDialog({
      title: "开始试课？",
      message: `开始后「${target?.teacher?.name || "该教员"}」将解锁家长联系方式，订单进入试课中。`,
      confirmButtonText: "开始试课",
    });
    await applicationsApi.startTrial(appId);
    showSuccessToast("已开始试课");
    if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
    await refreshPendingSummary();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleRestore(appId: number) {
  const target = applications.value.find((a) => a.id === appId);
  try {
    await showConfirmDialog({
      title: "恢复为待审核？",
      message: `「${target?.teacher?.name || "该教员"}」的投递将回到待审核列表（仅限未产生资金往来的误拒绝）。`,
      confirmButtonText: "恢复待审核",
    });
    await applicationsApi.restore(appId);
    showSuccessToast("已恢复为待审核");
    await refreshSelected();
    await refreshPendingSummary();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function refreshSelected() {
  if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
}


async function handleConfirmDeposit(appId: number) {
  try {
    await showConfirmDialog({ title: "确认定金？", message: "确认后会生成一条定金收入流水" });
    await applicationsApi.confirmDeposit(appId);
    showSuccessToast("定金已确认");
    await refreshSelected();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleConfirmBalance(appId: number) {
  try {
    await showConfirmDialog({ title: "确认尾款？", message: "确认后会生成一条尾款收入流水" });
    await applicationsApi.confirmBalance(appId);
    showSuccessToast("尾款已确认");
    await refreshSelected();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleComplete(appId: number) {
  try {
    await showConfirmDialog({ title: "确认完成？", message: "订单将标记为已完成" });
    await applicationsApi.complete(appId);
    showSuccessToast("订单已完成");
    await refreshSelected();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleTrialFailed(appId: number) {
  const target = applications.value.find((a) => a.id === appId);
  if (!target) return;
  trialFormApp.value = target;
  trialPaidByParent.value = "";
  isTeacherViolated.value = false;
  manualRefund.value = "";
  trialFormVisible.value = true;
}

// 与后端 services/calculator.py 的费率规则保持一致（寒暑假单暂取不到标记，按常规计算，最终以后端精算为准）
function infoFeeRate(weeklyFrequency: number): number {
  if (weeklyFrequency === 1) return 1.5;
  if (weeklyFrequency === 2) return 1.0;
  if (weeklyFrequency === 3) return 0.9;
  return 0.8;
}

function paidAmountFor(app: ApplicationItem): { paid: number; deposit: number; balance: number } {
  const order = orders.value.find((o) => o.id === app.order_id);
  let deposit = 0;
  let balance = 0;
  if (order) {
    if (app.proposed_price != null && Number(app.proposed_price) > 0) {
      const total = Math.round(Number(app.proposed_price) * infoFeeRate(order.weekly_frequency) * 100) / 100;
      deposit = 100;
      balance = Math.max(0, Math.round((total - 100) * 100) / 100);
    } else {
      deposit = Number(order.deposit_amount) || 0;
      balance = Number(order.balance_amount) || 0;
    }
  }
  const paid = deposit + (app.status === "balance_paid" ? balance : 0);
  return { paid: Math.round(paid * 100) / 100, deposit, balance };
}

const trialRefundPreview = computed(() => {
  if (!trialFormApp.value) return null;
  const { paid } = paidAmountFor(trialFormApp.value);
  if (isTeacherViolated.value) return 0;
  const trialPaid = Number(trialPaidByParent.value) || 0;
  if (trialPaid > 0) return Math.max(0, Math.round((paid - trialPaid * 0.7) * 100) / 100);
  return Math.max(0, Math.round((Number(manualRefund.value) || 0) * 100) / 100);
});

async function confirmTrialFailed() {
  const app = trialFormApp.value;
  if (!app) return;
  try {
    await applicationsApi.trialFailed(
      app.id,
      Number(manualRefund.value) || 0,
      Number(trialPaidByParent.value) || 0,
      isTeacherViolated.value,
    );
    showSuccessToast("订单已重新开放");
    trialFormVisible.value = false;
    await refreshSelected();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleReject(appId: number) {
  try {
    await showConfirmDialog({
      title: "拒绝该投递？",
      message: "拒绝后教员会从待处理列表移除，且无法再对该订单操作。",
      confirmButtonText: "确认拒绝",
    });
    await applicationsApi.reject(appId);
    showSuccessToast("已拒绝该投递");
    await refreshSelected();
    await refreshPendingSummary();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

async function handleForfeit(appId: number) {
  try {
    await showConfirmDialog({
      title: "没收定金？",
      message: "确认教员违约后，已交定金/尾款将登记为没收收入，订单重新开放。此操作不可撤销。",
      confirmButtonText: "确认没收",
    });
    await applicationsApi.forfeit(appId);
    showSuccessToast("已没收信息费");
    await refreshSelected();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="投递审核" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="mx-auto w-full max-w-5xl flex h-[calc(100vh-96px)]">
      <!-- 左侧订单列表 -->
      <div class="w-40 shrink-0 bg-white border-r overflow-y-auto">
        <div class="sticky top-0 z-10 flex gap-1 border-b bg-white px-1.5 py-1.5">
          <button
            v-for="opt in filterOptions" :key="opt.key"
            class="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
            :class="orderFilter === opt.key ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-500'"
            @click="orderFilter = opt.key"
          >
            {{ opt.label }}
          </button>
        </div>
        <div
          v-for="order in visibleOrders" :key="order.id"
          class="relative p-3 text-xs border-b cursor-pointer"
          :class="selectedOrderId === order.id ? 'bg-primary-50 text-primary-600 font-semibold' : 'text-gray-600'"
          @click="selectOrder(order.id)"
        >
          <span v-if="applicationCount(order.id)" class="admin-notification-badge absolute right-2 top-2">{{ applicationCount(order.id) > 99 ? "99+" : applicationCount(order.id) }}</span>
          <div class="truncate pr-5">{{ order.grade_subject }}</div>
          <div class="text-gray-400 text-[10px] mt-0.5 truncate">
            {{ order.raw_id }}
            <span v-if="order.status === 'completed'" class="font-medium text-emerald-600">· 已成交</span>
          </div>
        </div>
        <div v-if="visibleOrders.length === 0" class="p-4 text-gray-400 text-xs text-center">
          该状态下暂无订单
        </div>
      </div>

      <!-- 右侧投递详情 -->
      <div class="flex-1 overflow-y-auto p-3">
        <div v-if="!selectedOrderId" class="text-center py-20 text-gray-400 text-sm">
          ← 选择左侧订单查看投递
        </div>

        <div v-else-if="applications.length === 0" class="text-center py-20 text-gray-400 text-sm">
          暂无投递
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="app in applications" :key="app.id"
            class="cursor-pointer bg-white rounded-xl p-3 shadow-sm"
            @click="openApplicationDetail(app)"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 pr-2">
                <span class="font-semibold text-sm break-all">
                  {{ app.teacher?.name || `教员 #${app.teacher_id}` }}
                </span>
                <span
                  v-if="app.teacher?.is_985"
                  class="px-1.5 py-0.5 rounded-full text-[10px] bg-blue-50 text-blue-600 shrink-0"
                >
                  985
                </span>
                <span
                  v-if="app.teacher?.is_211"
                  class="px-1.5 py-0.5 rounded-full text-[10px] bg-sky-50 text-sky-700 shrink-0"
                >
                  211
                </span>
                <span
                  v-if="app.teacher?.is_double_first_class"
                  class="px-1.5 py-0.5 rounded-full text-[10px] bg-emerald-50 text-emerald-700 shrink-0"
                >
                  双一流
                </span>
                <span
                  v-if="app.teacher?.is_985_211 && !app.teacher?.is_985 && !app.teacher?.is_211"
                  class="px-1.5 py-0.5 rounded-full text-[10px] bg-blue-50 text-blue-600 shrink-0"
                >
                  985/211
                </span>
              </div>
              <span
                class="shrink-0 whitespace-nowrap rounded-full px-1.5 py-0.5 text-[11px] leading-4"
                :class="{
                  'bg-yellow-100 text-yellow-700': app.status === 'pending',
                  'bg-blue-100 text-blue-700': app.status === 'shortlisted',
                  'bg-cyan-100 text-cyan-700': app.status === 'deposit_paid',
                  'bg-emerald-100 text-emerald-700': app.status === 'trial_in_progress',
                  'bg-green-100 text-green-700': app.status === 'balance_paid',
                  'bg-emerald-600 text-white': app.status === 'completed',
                  'bg-amber-100 text-amber-700': app.status === 'forfeited',
                  'bg-gray-100 text-gray-500': ['rejected', 'refunded'].includes(app.status),
                }"
              >
                {{ APPLICATION_STATUS_LABELS[app.status] || app.status }}
              </span>
            </div>

            <div
              v-if="app.teacher"
              class="text-xs text-gray-500 bg-gray-50 rounded-lg p-2 mb-2 space-y-1"
            >
              <div class="font-medium text-gray-700">
                {{ app.teacher.school }}
                <span v-if="app.teacher.major" class="text-gray-400"> · {{ app.teacher.major }}</span>
                <span v-if="app.teacher.grade" class="text-gray-400"> · {{ app.teacher.grade }}</span>
              </div>
              <div class="text-gray-500">
                {{ app.teacher.gender === 'female' ? '女' : '男' }}
                <span v-if="app.teacher.highlights"> · {{ app.teacher.highlights }}</span>
              </div>
              <div class="flex flex-wrap items-center gap-2 pt-0.5">
                <span class="text-emerald-700">成交 {{ app.teacher.completed_count ?? 0 }} 单</span>
                <span
                  :class="(app.teacher.violation_count ?? 0) > 0 ? 'text-red-500' : 'text-gray-400'"
                >
                  违约 {{ app.teacher.violation_count ?? 0 }} 次
                </span>
                <span v-if="app.teacher.avg_rating != null" class="text-amber-600">
                  评分 {{ app.teacher.avg_rating }} ★
                </span>
              </div>
              <div
                v-if="app.teacher.phone || app.teacher.wechat_id"
                class="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-gray-100 pt-1"
              >
                <template v-if="app.teacher.phone">
                  <span class="text-gray-600">手机 {{ app.teacher.phone }}</span>
                  <button
                    class="text-primary-600"
                    @click.stop="copyContact(app.teacher.phone, '手机号已复制')"
                  >
                    复制
                  </button>
                </template>
                <template v-if="app.teacher.wechat_id">
                  <span class="text-gray-600">微信 {{ app.teacher.wechat_id }}</span>
                  <button
                    class="text-primary-600"
                    @click.stop="copyContact(app.teacher.wechat_id, '微信号已复制')"
                  >
                    复制
                  </button>
                </template>
              </div>
            </div>

            <div class="text-xs text-gray-400 mb-2">
              <div class="break-all">订单编号：<span class="text-gray-600 font-medium">{{ app.raw_order_id || `#${app.order_id}` }}</span></div>
              投递于 {{ new Date(app.applied_at).toLocaleString("zh-CN") }}
              <div v-if="app.proposed_price != null" class="mt-1 text-orange-600 font-medium">
                教员报价：¥{{ app.proposed_price }}/次
              </div>
            </div>

            <div v-if="app.status === 'pending'" class="grid grid-cols-2 gap-2">
              <button
                class="header-gradient text-white rounded-lg py-2 text-xs font-semibold"
                @click.stop="handleShortlist(app.id)"
              >
                加入候选队列
              </button>
              <button
                class="bg-red-50 text-red-500 rounded-lg py-2 text-xs font-semibold"
                @click.stop="handleReject(app.id)"
              >
                拒绝
              </button>
            </div>

            <div v-if="app.status === 'shortlisted'" class="space-y-2">
              <button
                class="w-full bg-[#1a365d] text-white rounded-lg py-2 text-xs font-semibold"
                @click.stop="handleConfirmDeposit(app.id)"
              >
                确认定金
              </button>
              <button
                class="w-full bg-red-50 text-red-500 rounded-lg py-2 text-xs font-semibold"
                @click.stop="handleReject(app.id)"
              >
                拒绝
              </button>
            </div>

            <button
              v-if="app.status === 'deposit_paid'"
              class="w-full bg-emerald-600 text-white rounded-lg py-2 text-xs font-semibold mb-2"
              @click.stop="handleStartTrial(app.id)"
            >
              开始试课
            </button>

            <div v-if="app.status === 'trial_in_progress'" class="space-y-2">
              <div class="text-xs text-emerald-700 bg-emerald-50 rounded-lg p-2">
                当前教员正在试课，可查看家长联系方式
              </div>
              <div class="grid grid-cols-2 gap-2">
                <button
                  class="bg-red-50 text-red-500 rounded-lg py-2 text-xs font-semibold"
                  @click.stop="handleTrialFailed(app.id)"
                >
                  试课失败
                </button>
                <button
                  class="bg-green-600 text-white rounded-lg py-2 text-xs font-semibold"
                  @click.stop="handleConfirmBalance(app.id)"
                >
                  确认尾款
                </button>
              </div>
            </div>

            <button
              v-if="['deposit_paid', 'trial_in_progress', 'balance_paid'].includes(app.status)"
              class="w-full bg-orange-50 text-orange-600 rounded-lg py-2 text-xs font-semibold mt-2"
              @click.stop="handleForfeit(app.id)"
            >
              没收定金（教员违约）
            </button>

            <div v-if="app.status === 'balance_paid'" class="space-y-2">
              <div class="text-xs text-green-600 bg-green-50 rounded-lg p-2">
                教员已付全款，可解锁联系方式
              </div>
              <button
                class="w-full bg-gray-900 text-white rounded-lg py-2 text-xs font-semibold"
                @click.stop="handleComplete(app.id)"
              >
                确认完成
              </button>
            </div>

            <button
              v-if="app.status === 'completed'"
              class="w-full bg-amber-50 text-amber-600 rounded-lg py-2 text-xs font-semibold mt-2"
              @click.stop="openReview(app)"
            >
              {{ app.teacher?.avg_rating != null ? "修改评价" : "评价教员" }}
            </button>

            <button
              v-if="app.status === 'rejected' && canRestore"
              class="w-full border border-slate-200 bg-white text-slate-600 rounded-lg py-2 text-xs font-semibold mt-2"
              @click.stop="handleRestore(app.id)"
            >
              恢复待审核（误拒绝回退）
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 评价教员弹窗 -->
    <van-popup v-model:show="reviewVisible" position="bottom" round close-on-click-overlay>
      <div v-if="reviewApp" class="p-5">
        <div class="mb-1 text-lg font-bold">
          评价教员：{{ reviewApp.teacher?.name || `#${reviewApp.teacher_id}` }}
        </div>
        <div class="mb-4 text-xs text-gray-400">
          评价会进入教员信用档案并影响推荐排序，一单一条，可修改
        </div>
        <div class="flex items-center justify-center py-2">
          <van-rate v-model="reviewRating" :size="30" color="#f59e0b" />
        </div>
        <van-field
          v-model="reviewComment"
          label="评语"
          type="textarea"
          rows="2"
          autosize
          maxlength="255"
          show-word-limit
          placeholder="如：守时负责，家长反馈很好"
        />
        <button
          class="mt-4 w-full header-gradient text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
          :disabled="reviewSubmitting"
          @click="submitReview"
        >
          {{ reviewSubmitting ? "提交中..." : "提交评价" }}
        </button>
      </div>
    </van-popup>

    <van-popup v-model:show="detailVisible" position="bottom" round>
      <div v-if="detailApplication" class="max-h-[78vh] overflow-y-auto p-5">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <div class="text-xl font-bold break-all">
              {{ detailApplication.teacher?.name || `教员 #${detailApplication.teacher_id}` }}
            </div>
            <div class="mt-1 text-xs text-gray-400">投递详情</div>
          </div>
          <span class="shrink-0 rounded-full bg-yellow-100 px-2 py-1 text-xs text-yellow-700">
            {{ detailApplication ? APPLICATION_STATUS_LABELS[detailApplication.status] || detailApplication.status : "" }}
          </span>
        </div>

        <div class="mb-3 rounded-xl bg-blue-50 p-3 text-sm text-blue-700">
          <div class="break-all">订单编号：<span class="font-semibold">{{ detailApplication.raw_order_id || `#${detailApplication.order_id}` }}</span></div>
        </div>

        <!-- 进度时间线 -->
        <div class="mb-3 rounded-xl border border-gray-100 p-3">
          <div class="mb-2 text-sm font-semibold text-gray-700">进度时间线</div>
          <div>
            <div v-for="(node, i) in appTimeline" :key="node.label" class="flex gap-3">
              <div class="flex flex-col items-center">
                <span
                  class="mt-1 h-2 w-2 shrink-0 rounded-full"
                  :class="{
                    'bg-emerald-500': node.state === 'done',
                    'bg-blue-500': node.state === 'current',
                    'bg-gray-200': node.state === 'pending',
                    'bg-gray-100': node.state === 'skipped',
                    'bg-red-400': node.state === 'terminal',
                  }"
                ></span>
                <span
                  v-if="i < appTimeline.length - 1"
                  class="my-0.5 w-px flex-1"
                  :class="node.state === 'done' ? 'bg-emerald-300' : 'bg-gray-100'"
                ></span>
              </div>
              <div class="flex flex-1 items-center justify-between gap-2 pb-2.5">
                <span
                  class="text-xs"
                  :class="{
                    'text-gray-700': node.state === 'done',
                    'font-semibold text-blue-600': node.state === 'current',
                    'text-gray-400': node.state === 'pending',
                    'text-gray-300 line-through': node.state === 'skipped',
                    'font-semibold text-red-500': node.state === 'terminal',
                  }"
                >
                  {{ node.label }}
                </span>
                <span class="shrink-0 text-[11px] text-gray-400">{{ nodeTimeLabel(node) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="detailApplication.teacher" class="space-y-3 rounded-xl bg-gray-50 p-3 text-sm text-gray-600">
          <div><span class="text-gray-400">学校：</span>{{ detailApplication.teacher.school || "未填写" }}</div>
          <div><span class="text-gray-400">专业：</span>{{ detailApplication.teacher.major || "未填写" }}</div>
          <div><span class="text-gray-400">年级：</span>{{ detailApplication.teacher.grade || "未填写" }}</div>
          <div><span class="text-gray-400">性别：</span>{{ detailApplication.teacher.gender === "female" ? "女" : "男" }}</div>
          <div><span class="text-gray-400">个人优势：</span>{{ detailApplication.teacher.highlights || "未填写" }}</div>
          <div v-if="detailApplication.teacher.phone || detailApplication.teacher.wechat_id" class="space-y-1 border-t border-gray-200 pt-2">
            <div v-if="detailApplication.teacher.phone" class="flex items-center justify-between gap-2">
              <span><span class="text-gray-400">手机：</span>{{ detailApplication.teacher.phone }}</span>
              <button
                class="text-xs text-primary-600"
                @click="copyContact(detailApplication.teacher.phone, '手机号已复制')"
              >
                复制
              </button>
            </div>
            <div v-if="detailApplication.teacher.wechat_id" class="flex items-center justify-between gap-2">
              <span><span class="text-gray-400">微信：</span>{{ detailApplication.teacher.wechat_id }}</span>
              <button
                class="text-xs text-primary-600"
                @click="copyContact(detailApplication.teacher.wechat_id, '微信号已复制')"
              >
                复制
              </button>
            </div>
            <div class="text-xs text-gray-400">确认候选后可线下联系教员收取定金</div>
          </div>
        </div>

        <button
          class="mt-3 w-full rounded-lg bg-red-50 py-2 text-xs font-semibold text-red-500"
          @click="quickBlacklist(detailApplication)"
        >
          拉黑该教员（仅对本中介生效）
        </button>

        <div v-if="detailApplication.resume" class="mt-3 rounded-xl border border-gray-100 p-3">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-semibold text-gray-700">投递简历</span>
            <span class="text-xs text-gray-400 break-all">{{ detailApplication.resume.title }}</span>
          </div>
          <div class="space-y-2 text-sm text-gray-600">
            <div>
              <span class="text-gray-400">可授科目：</span>{{ detailApplication.resume.teaching_subjects || "未填写" }}
            </div>
            <div>
              <span class="text-gray-400">可授年级：</span>{{ detailApplication.resume.teaching_grades || "未填写" }}
            </div>
            <div>
              <span class="text-gray-400">家教经历：</span>{{ detailApplication.resume.experience || "未填写" }}
            </div>
            <div v-if="detailApplication.resume.strengths">
              <span class="text-gray-400">个人优势：</span>{{ detailApplication.resume.strengths }}
            </div>
            <div v-if="detailApplication.resume.availability">
              <span class="text-gray-400">可授课时间：</span>{{ detailApplication.resume.availability }}
            </div>
            <div v-if="detailApplication.resume.expected_rate">
              <span class="text-gray-400">期望课酬：</span>{{ detailApplication.resume.expected_rate }}
            </div>
          </div>
        </div>
        <div v-else class="mt-3 rounded-xl bg-gray-50 p-3 text-xs text-gray-400">
          该教员投递时未选择简历（使用默认资料）
        </div>

        <div class="mt-3 space-y-1 text-sm text-gray-500">
          <div>投递时间：{{ new Date(detailApplication.applied_at).toLocaleString("zh-CN") }}</div>
          <div v-if="detailApplication.proposed_price != null">教员报价：¥{{ detailApplication.proposed_price }}/次</div>
        </div>
      </div>
    </van-popup>

    <!-- 试课失败退费精算弹窗 -->
    <van-popup v-model:show="trialFormVisible" position="bottom" round>
      <div v-if="trialFormApp" class="max-h-[80vh] overflow-y-auto p-5">
        <div class="mb-4 text-lg font-bold">试课失败 · 退费精算</div>

        <div class="mb-3 rounded-xl bg-gray-50 p-3 text-sm text-gray-600 space-y-1">
          <div>教员：<span class="font-medium">{{ trialFormApp.teacher?.name || `教员 #${trialFormApp.teacher_id}` }}</span></div>
          <div>已收信息费：<span class="font-medium text-gray-800">¥{{ paidAmountFor(trialFormApp).paid }}</span></div>
          <div class="text-xs text-gray-400">定金 ¥{{ paidAmountFor(trialFormApp).deposit }}<template v-if="trialFormApp.status === 'balance_paid'"> + 尾款 ¥{{ paidAmountFor(trialFormApp).balance }}</template></div>
        </div>

        <div class="space-y-3 text-sm">
          <div>
            <div class="mb-1 text-gray-600">家长已支付给教员的试课酬（元，选填）</div>
            <van-field
              v-model="trialPaidByParent"
              type="number"
              placeholder="填写后按公式自动精算退款"
              class="rounded-lg border border-gray-200"
            />
          </div>
          <div v-if="!trialPaidByParent">
            <div class="mb-1 text-gray-600">或手动指定退款金额（元）</div>
            <van-field
              v-model="manualRefund"
              type="number"
              placeholder="不填则默认 0 元退款"
              class="rounded-lg border border-gray-200"
            />
          </div>
          <div class="flex items-center justify-between rounded-lg bg-orange-50 p-3">
            <span class="text-gray-700">教员违约（没收全部信息费）</span>
            <van-switch v-model="isTeacherViolated" size="22px" />
          </div>
          <div class="rounded-lg bg-blue-50 p-3 text-blue-700">
            预计退款：<span class="text-lg font-bold">¥{{ trialRefundPreview ?? 0 }}</span>
            <div class="mt-1 text-xs text-blue-400">精算公式：退款 = max(0, 已收信息费 − 家长试课酬 × 70%)；实际以平台记录为准</div>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <button
            class="rounded-lg bg-gray-100 py-2.5 text-sm font-medium text-gray-600"
            @click="trialFormVisible = false"
          >
            取消
          </button>
          <button
            class="rounded-lg bg-red-500 py-2.5 text-sm font-semibold text-white"
            @click="confirmTrialFailed"
          >
            确认试课失败
          </button>
        </div>
      </div>
    </van-popup>
    <AdminTabbar :application-count="applicationTotal" />
  </div>
</template>