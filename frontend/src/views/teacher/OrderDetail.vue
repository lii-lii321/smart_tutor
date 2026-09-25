<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { formatDateTime } from "@/utils/format";
import { getApiErrorMessage, getApiErrorStatus } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import { applicationsApi } from "@/api/applications";
import type { ApplicationItem, OrderDetail as OrderDetailData } from "@/api/types";
import { resumesApi, type TeacherResume } from "@/api/resumes";
import { showToast, showSuccessToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";
import { calcInfoFee } from "@/utils/fee";
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import OrderTimeline from "@/components/business/OrderTimeline.vue";
import OrderFinancialSummary, { type FinancialRow } from "@/components/business/OrderFinancialSummary.vue";
import {
  buildOrderLifecycleSteps,
  buildApplicationLifecycleSteps,
} from "@/components/business/timeline";
import {
  buildTeacherOrderActions,
  type OrderActionViewModel,
} from "@/components/business/order/orderActions";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const order = ref<OrderDetailData | null>(null);
const resumes = ref<TeacherResume[]>([]);
const myApplication = ref<ApplicationItem | null>(null);
const loading = ref(true);
const loadFailed = ref(false);
const applying = ref(false);
const resumePickerVisible = ref(false);
const selectedResumeId = ref<number | null>(null);
const proposedPrice = ref<number | null>(null);

const selectedResume = computed(() =>
  resumes.value.find((resume) => resume.id === selectedResumeId.value) || null
);

const selectedResumeCheck = computed(() =>
  selectedResume.value ? checkResumeFit(selectedResume.value) : { ok: false, reasons: ["请选择投递简历"] }
);

const canApply = computed(() => order.value?.status === "recruiting");

// 有活跃投递时不得再展示投递按钮：定金已付的单仍处于招聘中，按钮会误导重复投递（后端 409）
const hasActiveApplication = computed(() =>
  !!myApplication.value &&
  ["pending", "shortlisted", "deposit_paid", "trial_in_progress", "balance_paid", "completed"]
    .includes(myApplication.value.status),
);

/* ── Order Workspace 展示适配：状态/时间线/操作/财务全部由 API 状态映射，前端不做业务判断 ── */

// 订单生命周期（只由 OrderStatus 驱动）
const lifecycleSteps = computed(() =>
  order.value ? buildOrderLifecycleSteps(order.value) : []
);

// 我的投递进度（投递生命周期，辅助信息层）
const applicationSteps = computed(() =>
  myApplication.value ? buildApplicationLifecycleSteps(myApplication.value) : []
);

// 可用操作视图模型（后端仍是合法性唯一来源；403/409/422 由页面处理器兜底）
const teacherActions = computed(() =>
  order.value
    ? buildTeacherOrderActions(order.value, myApplication.value)
    : { primary: undefined, secondary: [] }
);

function dispatchAction(action: OrderActionViewModel | undefined) {
  if (!action) return;
  if (action.key === "apply") {
    openResumePicker();
    return;
  }
  if (action.key === "contact-agent") {
    copyApplyMessage();
    return;
  }
  router.push("/teacher/applications");
}

// 资金状态行（展示映射：金额取 API 下发的定金确认后快照 fee，快照缺失回退订单费用结构字段；
// 状态只读投递状态，前端不复算任何金额）
const financialRows = computed<FinancialRow[]>(() => {
  const o = order.value;
  if (!o || o.needs_manual_price) return [];
  const app = myApplication.value;
  const status = app?.status;
  const depositAmount = app?.fee?.deposit ?? o.deposit_amount;
  const balanceAmount = app?.fee?.balance ?? o.balance_amount;
  const rows: FinancialRow[] = [];

  if (status === "refunded") {
    rows.push({ key: "deposit", label: "定金", amount: `¥${depositAmount}`, state: "refunded", time: fmtTime(app?.refunded_at) });
  } else if (status === "forfeited") {
    rows.push({ key: "deposit", label: "定金", amount: `¥${depositAmount}`, state: "forfeited" });
  } else {
    const depositPaid = ["deposit_paid", "trial_in_progress", "balance_paid", "completed"].includes(status ?? "");
    rows.push({
      key: "deposit",
      label: "定金",
      amount: `¥${depositAmount}`,
      state: depositPaid ? "paid" : "pending",
      time: depositPaid ? fmtTime(app?.deposit_paid_at) : undefined,
    });
    const balancePaid = ["balance_paid", "completed"].includes(status ?? "");
    rows.push({
      key: "balance",
      label: "尾款",
      amount: `¥${balanceAmount}`,
      state: balancePaid ? "paid" : "pending",
      time: balancePaid ? fmtTime(app?.balance_paid_at) : undefined,
    });
  }
  return rows;
});

function fmtTime(iso: string | null | undefined): string | undefined {
  return iso ? formatDateTime(iso) : undefined;
}

// 一键复制投递消息：真实业务为教员微信联系对接中介推进（中介套中介），
// 复制一条自介绍消息到微信即可完成对接
const applyMessage = computed(() => {
  const o = order.value;
  if (!o) return "";
  const lines = [
    `您好，我在智派看到并投递了这单：`,
    `编号：${o.raw_id}`,
    `内容：${o.grade_subject} · ${o.price_total} · ${o.fuzzy_address}`,
  ];
  const name = auth.teacher?.name;
  if (name) lines.push(`我是${name}，麻烦对接，谢谢！`);
  return lines.join("\n");
});

async function copyApplyMessage() {
  try {
    await navigator.clipboard.writeText(applyMessage.value);
    showSuccessToast("投递消息已复制，去微信发送给对接中介吧");
  } catch {
    showToast("复制失败，请长按消息手动复制");
  }
}

async function copyContactWechat() {
  const wechat = order.value?.contact_wechat;
  if (!wechat) return;
  try {
    await navigator.clipboard.writeText(wechat);
    showSuccessToast("微信号已复制");
  } catch {
    showToast("复制失败，请手动复制");
  }
}

const myApplicationStatusLabel: Record<string, string> = {
  pending: "投递待审核",
  shortlisted: "已进入候选队列",
  deposit_paid: "定金已确认，等待中介安排试课",
  trial_in_progress: "试课进行中",
  balance_paid: "尾款已确认",
  completed: "已成交",
  rejected: "该投递未通过",
  refunded: "定金已退还",
  forfeited: "定金已没收",
};

const myApplicationStatusChip: Record<string, string> = {
  pending: "bg-yellow-50 text-yellow-700",
  shortlisted: "bg-slate-100 text-slate-700",
  deposit_paid: "bg-cyan-50 text-cyan-700",
  trial_in_progress: "bg-emerald-50 text-emerald-700",
  balance_paid: "bg-green-50 text-green-700",
  completed: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-50 text-red-500",
  refunded: "bg-gray-100 text-gray-500",
  forfeited: "bg-amber-50 text-amber-700",
};

// 信息费预览走 utils/fee.ts 单一费率源（与后端 calculator.py 对齐），寒暑假单按 2.5 倍口径
const proposedFeePreview = computed(() => {
  const price = Number(proposedPrice.value);
  if (!price || price <= 0) return null;
  return calcInfoFee(price, order.value?.weekly_frequency || 1, !!order.value?.is_summer_vacation);
});

function normalizeText(value?: string | null) {
  return (value || "").replace(/\s+/g, "").toLowerCase();
}

function extractOrderGrade() {
  const text = normalizeText(`${order.value?.grade_subject || ""}${order.value?.requirements || ""}${order.value?.raw_text || ""}`);
  const gradeTokens = ["高三", "高二", "高一", "高中", "初三", "初二", "初一", "初中", "小学"];
  return gradeTokens.find((token) => text.includes(token)) || "";
}

function extractOrderSubject() {
  const text = normalizeText(`${order.value?.grade_subject || ""}${order.value?.requirements || ""}${order.value?.raw_text || ""}`);
  const subjectTokens = ["英语", "数学", "物理", "化学", "语文", "生物", "历史", "地理", "政治"];
  return subjectTokens.find((token) => text.includes(token)) || "";
}

const GRADE_LEVELS: Record<string, number> = {
  小学: 0, 小一: 1, 小二: 2, 小三: 3, 小四: 4, 小五: 5, 小六: 6,
  初一: 7, 初二: 8, 初三: 9, 初中: 8,
  高一: 10, 高二: 11, 高三: 12, 高中: 11,
};

function isGradeCompatible(orderGrade: string, resumeText: string) {
  if (!orderGrade) return true;
  if (resumeText.includes(orderGrade)) return true;
  if (orderGrade.startsWith("高") && resumeText.includes("高中")) return true;
  if (orderGrade.startsWith("初") && resumeText.includes("初中")) return true;
  // 简历以范围表述（如 "初二-高三"）时按区间判断是否覆盖订单年级
  const orderLevel = GRADE_LEVELS[orderGrade];
  if (orderLevel !== undefined) {
    const rangeRe = /([高一高二高三初中小学小一二三四五六]{2})\s*[-—~至]\s*([高一高二高三初中小学小一二三四五六]{2})/g;
    let m: RegExpExecArray | null;
    while ((m = rangeRe.exec(resumeText)) !== null) {
      const lo = GRADE_LEVELS[m[1]];
      const hi = GRADE_LEVELS[m[2]];
      if (lo !== undefined && hi !== undefined && lo <= orderLevel && orderLevel <= hi) {
        return true;
      }
    }
  }
  return false;
}

function checkResumeFit(resume: TeacherResume) {
  const orderGrade = extractOrderGrade();
  const orderSubject = extractOrderSubject();
  const resumeGradeText = normalizeText(`${resume.title}${resume.teaching_grades}${resume.experience}${resume.strengths}`);
  const resumeSubjectText = normalizeText(`${resume.title}${resume.teaching_subjects}${resume.experience}${resume.strengths}`);
  const reasons: string[] = [];

  if (orderSubject && !resumeSubjectText.includes(orderSubject)) {
    reasons.push(`订单要求「${orderSubject}」，这份简历未体现可授该科目。`);
  }
  if (!isGradeCompatible(orderGrade, resumeGradeText)) {
    reasons.push(`订单年级为「${orderGrade}」，这份简历未体现匹配年级。`);
  }

  return { ok: reasons.length === 0, reasons };
}

function goEditResume(resume: TeacherResume) {
  router.push(`/teacher/profile?resumeId=${resume.id}`);
}

function goCreateResume() {
  router.push("/teacher/profile?action=create");
}

onMounted(async () => {
  await loadOrder();
  if (auth.isLoggedIn) {
    await loadResumes();
    await loadMyApplication();
  }
});

async function loadOrder() {
  loading.value = true;
  loadFailed.value = false;
  try {
    const id = Number(route.params.id);
    order.value = await ordersApi.getOrder(id);
  } catch {
    order.value = null;
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}

async function loadMyApplication() {
  if (!order.value) return;
  try {
    // 按单查询：后端 order_id 过滤，避免全量拉投递列表再内存 find
    const mine = await applicationsApi.listMine(1, 20, order.value.id);
    myApplication.value = mine[0] || null;
  } catch {
    myApplication.value = null;
  }
}

async function loadResumes() {
  try {
    resumes.value = await resumesApi.list();
    selectedResumeId.value =
      resumes.value.find((resume) => resume.is_default)?.id || resumes.value[0]?.id || null;
  } catch {
    resumes.value = [];
  }
}

async function openResumePicker() {
  if (!auth.isLoggedIn) {
    router.push("/teacher/login");
    return;
  }
  if (!order.value) return;

  if (order.value.needs_manual_price && (!proposedPrice.value || proposedPrice.value <= 0)) {
    showToast("请填写您的报价");
    return;
  }

  await loadResumes();
  if (resumes.value.length === 0) {
    const goCreate = await appConfirm({
      title: "还没有简历",
      message: "请先到个人中心创建一份简历，再投递给中介查看。",
      confirmText: "去创建",
    });
    if (!goCreate) return;
    router.push("/teacher/profile");
    return;
  }

  resumePickerVisible.value = true;
}

async function handleApply() {
  if (!order.value) return;
  if (!selectedResume.value) {
    showToast("请选择投递简历");
    return;
  }

  if (!selectedResumeCheck.value.ok) {
    return;
  }

  const orderSnapshot = order.value;
  const confirmMsg = orderSnapshot.needs_manual_price
    ? `将使用「${selectedResume.value.title}」投递，报价 ¥${proposedPrice.value}/次。投递成功后请按中介指引支付定金，中介确认定金后即可安排试课。`
    : `将使用「${selectedResume.value.title}」投递，需支付 ¥${orderSnapshot.deposit_amount} 定金锁定订单。投递成功后请按中介指引完成支付，中介确认后即可安排试课。`;

  const ok = await appConfirm({
    title: "确认投递",
    message: confirmMsg,
    confirmText: "确认投递",
  });
  if (!ok) return;

  applying.value = true;
  try {
    await applicationsApi.apply(orderSnapshot.id, proposedPrice.value ?? undefined, selectedResume.value.id);
    showSuccessToast("投递成功，请尽快微信联系对接中介");
    resumePickerVisible.value = false;
    router.push("/teacher/applications");
  } catch (e) {
    // 409 = 订单/投递状态已在后端发生变化（如重复投递）：引导刷新而非静默失败
    if (getApiErrorStatus(e) === 409) {
      showToast("订单状态已更新，请刷新页面后继续操作");
    } else {
      showToast(getApiErrorMessage(e, "投递失败"));
    }
  } finally {
    applying.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-page pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="订单详情" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="flex justify-center py-20">
      <van-loading type="spinner" />
    </div>

    <!-- ══ Order Workspace：围绕订单域组织（状态/操作/时间线/信息/投递/财务） ══ -->
    <div v-else-if="order" class="p-4 space-y-4">
      <!-- Header：一级信息（科目/价格/地点/状态），技术字段（编号）降为三级 -->
      <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
        <div class="flex items-start justify-between gap-3">
          <div class="flex min-w-0 items-start gap-3">
            <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-800 text-white">
              <van-icon name="notes-o" size="24" />
            </div>
            <div class="min-w-0">
              <div class="text-lg font-bold leading-6 text-slate-950">{{ order.grade_subject }}</div>
              <div class="mt-1 text-sm text-secondary">
                {{ order.price_total }}
                <span v-if="order.needs_manual_price" class="ml-1 text-warning">自带价</span>
              </div>
            </div>
          </div>
          <AppStatusBadge :status="order.status" />
        </div>

        <div class="mt-3 flex items-center gap-1 text-xs text-muted">
          <van-icon name="location-o" size="12" />
          <span class="min-w-0 truncate">{{ order.fuzzy_address }}</span>
          <span class="shrink-0">· 每周 {{ order.weekly_frequency }} 次</span>
        </div>

        <!-- 主要操作区：一个主 CTA + 次要操作（操作合法性由后端把关） -->
        <div
          v-if="teacherActions.primary"
          class="mt-4 border-t border-default pt-4"
        >
          <AppButton
            block
            size="lg"
            :variant="teacherActions.primary!.variant"
            :loading="teacherActions.primary!.key === 'apply' && applying"
            @click="dispatchAction(teacherActions.primary!)"
          >
            {{ teacherActions.primary!.label }}
          </AppButton>
          <div
            v-if="teacherActions.secondary.length"
            class="mt-2 flex flex-wrap gap-2"
          >
            <AppButton
              v-for="action in teacherActions.secondary"
              :key="action.key"
              size="sm"
              :variant="action.variant"
              @click="dispatchAction(action)"
            >
              {{ action.label }}
            </AppButton>
          </div>
        </div>
      </section>

      <!-- 订单生命周期（Order Status 驱动）+ 我的投递进度（Application Status 辅助层）：
           两条状态机分层展示，绝不混成一条 -->
      <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
        <h3 class="text-sm font-semibold text-primary">订单生命周期</h3>
        <div class="mt-3">
          <OrderTimeline :steps="lifecycleSteps" />
        </div>

        <template v-if="myApplication">
          <div class="my-4 border-t border-default" />
          <h3 class="text-sm font-semibold text-primary">我的投递进度</h3>
          <div class="mt-3">
            <OrderTimeline compact :steps="applicationSteps" />
          </div>
        </template>
        <p v-else-if="canApply" class="mt-4 rounded-lg bg-surface-soft p-3 text-xs leading-5 text-muted">
          订单已发布，正在等待教员投递；你投递后，这里会展示你的投递进度。
        </p>
      </section>

      <!-- 我的投递与对接：真实业务为微信联系中介推进（中介套中介），
           一键复制投递消息 + 复制中介微信号，家长联系方式不进入教员链路 -->
      <section
        v-if="myApplication"
        class="rounded-2xl border border-default bg-surface p-5 shadow-card"
      >
        <div class="mb-3 flex items-center justify-between">
          <div class="text-sm font-semibold text-primary">联系对接中介</div>
          <span
            class="rounded-full px-2 py-0.5 text-[11px] font-medium"
            :class="myApplicationStatusChip[myApplication.status] || 'bg-gray-100 text-gray-500'"
          >
            {{ myApplicationStatusLabel[myApplication.status] || myApplication.status }}
          </span>
        </div>

        <div
          v-if="order.contact_wechat"
          class="mb-3 flex items-center justify-between gap-2 rounded-lg bg-surface-soft px-3 py-2.5"
        >
          <div class="min-w-0 text-sm">
            <span class="text-muted">对接中介微信：</span>
            <span class="font-mono font-medium text-slate-900">{{ order.contact_wechat }}</span>
          </div>
          <button
            class="shrink-0 rounded-lg border border-default px-2.5 py-1 text-xs font-medium text-brand-800"
            @click="copyContactWechat"
          >
            复制
          </button>
        </div>
        <p v-else class="mb-3 text-xs leading-5 text-muted">
          对接中介的微信号在橱窗页顶部可以查看，添加后发送下方消息即可。
        </p>

        <!-- 投递消息预览 + 一键复制 -->
        <div class="whitespace-pre-line rounded-lg border border-default bg-surface-soft/60 p-3 text-sm leading-6 text-secondary">
          {{ applyMessage }}
        </div>
        <p class="mt-2 text-[11px] leading-4 text-muted">
          复制后打开微信发给对接中介，即可确认试课时间与课酬细节。投递于 {{ formatDateTime(myApplication.applied_at) }}。
        </p>
      </section>

      <!-- 订单信息 -->
      <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
        <div class="mb-3 text-sm font-semibold text-primary">教学要求</div>
        <p class="whitespace-pre-line text-sm leading-6 text-secondary">
          {{ order.requirements || "暂无额外要求" }}
        </p>
        <div class="my-3 border-t border-default" />
        <div class="mb-2 text-sm font-semibold text-primary">原始完整信息</div>
        <p class="whitespace-pre-line rounded-lg bg-surface-soft p-3 text-sm leading-6 text-secondary">
          {{ order.raw_text }}
        </p>
        <div class="mt-2 text-right text-[11px] tracking-wide text-slate-400">订单编号 {{ order.raw_id }}</div>
      </section>

      <!-- 资金状态：金额/状态/时间全部来自 API（定金确认后快照 fee，缺失回退订单字段），前端不复算 -->
      <OrderFinancialSummary v-if="financialRows.length" :rows="financialRows" />

      <!-- 自带价：报价表单（提交前输入，非财务展示） -->
      <section v-if="order.needs_manual_price && !hasActiveApplication" class="rounded-2xl border border-amber-200 bg-amber-50 p-5">
        <div class="mb-3 text-sm text-amber-700">该订单为自带价，请填写您的期望课酬。</div>
        <div class="flex items-center gap-3">
          <span class="text-sm text-secondary">¥ / 次</span>
          <input
            v-model.number="proposedPrice"
            type="number"
            class="flex-1 rounded-lg border border-amber-300 bg-white px-4 py-3 text-lg font-bold focus:border-amber-500 focus:outline-none"
            placeholder="如 200"
          />
        </div>
        <div v-if="proposedFeePreview" class="mt-3 text-xs text-secondary leading-5">
          参考信息费约 ¥{{ proposedFeePreview.total }}（每周 {{ order.weekly_frequency }} 次 × {{ proposedFeePreview.rate }} 倍）
          <span class="text-muted">定金 ¥{{ proposedFeePreview.deposit }} + 尾款 ¥{{ proposedFeePreview.balance }}</span>
        </div>
      </section>
    </div>

    <div v-else class="flex flex-col items-center justify-center py-20 text-slate-400">
      <!-- 显式整行居中：不依赖图标字体的字形宽度，字体回退时也不会偏 -->
      <div class="flex w-full justify-center">
        <van-icon name="warning-o" size="48" />
      </div>
      <p class="mt-4">{{ loadFailed ? "订单加载失败，请稍后重试" : "订单不存在或已下架" }}</p>
      <button class="mt-4 rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-600" @click="loadOrder">
        重新加载
      </button>
    </div>

    <van-popup v-model:show="resumePickerVisible" round position="bottom">
      <div class="max-h-[75vh] overflow-y-auto p-4">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <div class="text-base font-semibold text-slate-950">选择投递简历</div>
            <div class="mt-1 text-xs text-slate-500">中介会看到这份简历的完整内容</div>
          </div>
          <button class="text-sm text-slate-600" @click="router.push('/teacher/profile')">管理简历</button>
        </div>

        <div class="space-y-3">
          <div
            v-for="resume in resumes"
            :key="resume.id"
            class="w-full rounded-xl border bg-white p-4 text-left"
            :class="[
              selectedResumeId === resume.id ? 'border-slate-600 ring-1 ring-slate-600' : 'border-slate-200',
              !checkResumeFit(resume).ok ? 'bg-red-50/50' : '',
            ]"
            @click="selectedResumeId = resume.id"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="font-semibold text-slate-950">{{ resume.title }}</div>
              <div class="flex shrink-0 items-center gap-2">
                <van-tag v-if="!checkResumeFit(resume).ok" type="danger" plain>不匹配</van-tag>
                <van-tag v-if="resume.is_default" type="primary" plain>默认</van-tag>
              </div>
            </div>
            <div class="mt-2 text-sm text-slate-600">
              {{ resume.teaching_grades }} · {{ resume.teaching_subjects }}
            </div>
            <div class="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">
              {{ resume.experience }}
            </div>
            <div v-if="!checkResumeFit(resume).ok" class="mt-3 rounded-lg bg-red-50 p-3 text-xs leading-5 text-red-700">
              <div v-for="reason in checkResumeFit(resume).reasons" :key="reason">{{ reason }}</div>
              <div class="mt-3 flex gap-2">
                <button class="rounded-lg bg-white px-3 py-2 font-medium text-red-700" @click.stop="goEditResume(resume)">
                  修改这份简历
                </button>
                <button class="rounded-lg bg-white px-3 py-2 font-medium text-slate-700" @click.stop="goCreateResume">
                  新增简历
                </button>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="selectedResume && !selectedResumeCheck.ok"
          class="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm leading-6 text-red-700"
        >
          <div class="font-semibold">暂不能投递这份简历</div>
          <div v-for="reason in selectedResumeCheck.reasons" :key="reason">{{ reason }}</div>
        </div>

        <button
          class="mt-4 w-full rounded-xl bg-brand-800 py-3 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="applying || !selectedResume || !selectedResumeCheck.ok"
          @click="handleApply"
        >
          确认投递
        </button>
      </div>
    </van-popup>
  </div>
</template>
