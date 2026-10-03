<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getApiErrorMessage, getApiErrorStatus } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import { applicationsApi } from "@/api/applications";
import type { ApplicationItem, OrderDetail as OrderDetailData } from "@/api/types";
import { formatDateTime } from "@/utils/format";
import { showToast, showSuccessToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";
import AdminShell from "@/components/admin/AdminShell.vue";
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppEmpty from "@/components/ui/AppEmpty.vue";
import OrderStageBar from "@/components/business/OrderStageBar.vue";
import ApplicationStepper from "@/components/business/ApplicationStepper.vue";
import ApplicationCard from "@/components/admin/ApplicationCard.vue";
import ApplicationDetailDialog from "@/components/admin/ApplicationDetailDialog.vue";
import TrialFailedPopup from "@/components/admin/TrialFailedPopup.vue";
import ReviewPopup from "@/components/admin/ReviewPopup.vue";
import { buildAdminOrderActions, type OrderActionViewModel } from "@/components/business/order/orderActions";
import { buildOrderFinancialRows, pickDealApplication } from "@/components/business/order/financialRows";

/**
 * B 端 Order Workspace（Batch 04 核心）：
 * 与 C 端 Order Workspace 共享 Order Domain（财务行适配/状态口径），
 * 仅 Adapter 与布局不同——桌面 Main+Sidebar，移动单列。
 * 状态流转动作深链到 ApplicationsReview 工作流（?order= 深链已存在）；
 * 归档/重新发布为本页直接动作（二次确认 + 后端把关）。
 * 2026-09-30：① 侧栏投递卡升格为可操作的 ApplicationCard——试课中订单的
 * 确认尾款/试课失败/没收/完成/评价等跟进动作在工作区原地可用；
 * ② 两条纵向时间线改为横条（OrderStageBar/ApplicationStepper），一屏收纳。
 */
const route = useRoute();
const router = useRouter();

const order = ref<OrderDetailData | null>(null);
const applications = ref<ApplicationItem[]>([]);
const loading = ref(true);
const loadFailed = ref(false);
const acting = ref(false);

// 资金状态所属投递：优先已进入资金流的那条（共享适配器，C 端同一套逻辑）
const dealApplication = computed(() => pickDealApplication(applications.value));
const financialRows = computed(() => {
  const o = order.value;
  if (!o) return [];
  return buildOrderFinancialRows(o, dealApplication.value, formatDateTime);
});

const adminActions = computed(() => (order.value ? buildAdminOrderActions(order.value) : { secondary: [] }));

function dispatchAction(action: OrderActionViewModel | undefined) {
  if (!action || !order.value) return;
  if (action.key === "review") {
    router.push({ path: "/admin/applications", query: { order: String(order.value.id) } });
    return;
  }
  if (action.key === "financial") {
    router.push("/admin/financial-records");
    return;
  }
  if (action.key === "archive") {
    void handleArchive();
    return;
  }
  if (action.key === "republish") {
    void handleRepublish();
  }
}

async function handleArchive() {
  if (!order.value || acting.value) return;
  const ok = await appConfirm({
    title: "确认归档？",
    message: "归档后订单将不在橱窗展示",
    confirmText: "归档",
    danger: true,
  });
  if (!ok) return;
  acting.value = true;
  try {
    await ordersApi.archive(order.value.id);
    showSuccessToast("已归档");
    await loadAll();
  } catch (e) {
    handleActionError(e, "归档失败");
  } finally {
    acting.value = false;
  }
}

async function handleRepublish() {
  if (!order.value || acting.value) return;
  const ok = await appConfirm({
    title: "重新发布？",
    message: "订单会回到招聘中，并重新出现在教员橱窗",
    confirmText: "重新发布",
  });
  if (!ok) return;
  acting.value = true;
  try {
    await ordersApi.republish(order.value.id);
    showSuccessToast("已重新发布");
    await loadAll();
  } catch (e) {
    handleActionError(e, "重新发布失败");
  } finally {
    acting.value = false;
  }
}

function handleActionError(e: unknown, fallback: string) {
  // 409 = 订单状态已在后端变化（如已被其他端归档/流转），引导刷新而非静默失败
  if (getApiErrorStatus(e) === 409) {
    showToast("订单状态已更新，请刷新后继续操作");
  } else {
    showToast(getApiErrorMessage(e, fallback));
  }
}

// ── 侧栏投递卡的跟进动作编排（与 ApplicationsReview 同一套口径与文案）──
// 仅招聘中的订单可恢复误拒投递（终态订单的落选不可回退）
const canRestore = computed(() => order.value?.status === "recruiting");

const reviewVisible = ref(false);
const reviewApp = ref<ApplicationItem | null>(null);
const trialFormVisible = ref(false);
const trialFormApp = ref<ApplicationItem | null>(null);
const detailVisible = ref(false);
const detailApplication = ref<ApplicationItem | null>(null);

async function runAppAction(
  appId: number,
  apiCall: (id: number) => Promise<unknown>,
  confirm: { title: string; message: string; confirmButtonText?: string; danger?: boolean },
  successToast = "操作成功",
) {
  if (acting.value) return; // 上一动作未落地前忽略再点击，防并发确认
  const ok = await appConfirm({
    title: confirm.title,
    message: confirm.message,
    confirmText: confirm.confirmButtonText,
    danger: confirm.danger,
  });
  if (!ok) return; // 用户在底部弹层取消
  acting.value = true;
  try {
    await apiCall(appId);
    showSuccessToast(successToast);
    await loadAll();
  } catch (e) {
    handleActionError(e, "操作失败");
  } finally {
    acting.value = false;
  }
}

function targetName(appId: number): string {
  return applications.value.find((a) => a.id === appId)?.teacher?.name || "该教员";
}

const handleShortlist = (appId: number) =>
  runAppAction(appId, applicationsApi.shortlist, {
    title: "加入候选队列？",
    message: "教员将进入该订单的候选排队，等待线下定金收取后确认。",
    confirmButtonText: "加入候选",
  }, "已加入候选队列");

const handleStartTrial = (appId: number) =>
  runAppAction(appId, applicationsApi.startTrial, {
    title: "开始试课？",
    message: `开始后「${targetName(appId)}」将解锁家长联系方式，订单进入试课中。`,
    confirmButtonText: "开始试课",
  }, "已开始试课");

const handleConfirmDeposit = (appId: number) =>
  runAppAction(appId, applicationsApi.confirmDeposit, {
    title: "确认定金？",
    message: "确认后会生成一条定金收入流水",
  }, "定金已确认");

const handleConfirmBalance = (appId: number) =>
  runAppAction(appId, applicationsApi.confirmBalance, {
    title: "确认尾款？",
    message: "确认后会生成一条尾款收入流水",
  }, "尾款已确认");

const handleComplete = (appId: number) =>
  runAppAction(appId, applicationsApi.complete, {
    title: "确认完成？",
    message: "订单将标记为已完成",
  }, "订单已完成");

const handleForfeit = (appId: number) =>
  runAppAction(appId, applicationsApi.forfeit, {
    title: "没收定金？",
    message: "确认教员违约后，已交定金/尾款将登记为没收收入，订单重新开放。此操作不可撤销。",
    confirmButtonText: "确认没收",
    danger: true,
  }, "已没收信息费");

const handleRestore = (appId: number) =>
  runAppAction(appId, applicationsApi.restore, {
    title: "恢复为待审核？",
    message: `「${targetName(appId)}」的投递将回到待审核列表（仅限未产生资金往来的误拒绝）。`,
    confirmButtonText: "恢复待审核",
  }, "已恢复为待审核");

const handleReject = (appId: number) =>
  runAppAction(appId, applicationsApi.reject, {
    title: "拒绝该投递？",
    message: "拒绝后教员会从待处理列表移除，且无法再对该订单操作。",
    confirmButtonText: "确认拒绝",
    danger: true,
  }, "已拒绝该投递");

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

onMounted(loadAll);

async function loadAll() {
  // 动作后的重拉失败不丢弃已有内容（409 等场景已有 toast 指引），只有首次加载失败才进错误态
  const isInitial = !order.value;
  loading.value = true;
  loadFailed.value = false;
  try {
    const id = Number(route.params.id);
    const [detail, apps] = await Promise.all([
      ordersApi.getOrder(id),
      applicationsApi.listByOrder(id, 1, 100).catch(() => [] as ApplicationItem[]),
    ]);
    order.value = detail;
    applications.value = apps;
  } catch {
    if (isInitial) {
      order.value = null;
      loadFailed.value = true;
    }
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <AdminShell fluid>
    <van-nav-bar title="订单工作区" left-arrow @click-left="router.push('/admin/orders')" />

    <!-- 转圈仅首屏（无数据时）；动作后的重拉保持整页旧内容渲染，不再闪白 -->
    <div
      v-if="loading && !order"
      class="flex justify-center py-20"
    >
      <van-loading type="spinner" />
    </div>

    <div
      v-else-if="order"
      class="mx-auto w-full max-w-5xl px-4 pt-2 lg:px-6"
    >
      <!-- 桌面双栏（≥1024px）：Main（生命周期/信息）+ Sidebar（投递/教员/资金）；移动单列 -->
      <div class="space-y-4 lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start lg:gap-4 lg:space-y-0">
        <!-- ── Main ── -->
        <div class="space-y-4 lg:min-w-0">
          <!-- Order Header：一级信息（科目/价格/地点/状态）+ 主操作；编号为三级信息 -->
          <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="text-lg font-bold leading-6 text-primary">{{ order.grade_subject }}</div>
                <div class="mt-1 text-sm text-secondary">
                  {{ order.price_total }}
                  <span
                    v-if="order.needs_manual_price"
                    class="ml-1 text-warning"
                  >自带价</span>
                </div>
              </div>
              <AppStatusBadge :status="order.status" />
            </div>
            <div class="mt-2 flex items-center gap-1 text-xs text-muted">
              <van-icon
                name="location-o"
                size="12"
              />
              <span class="min-w-0 truncate">{{ order.fuzzy_address }}</span>
              <span class="shrink-0">· 每周 {{ order.weekly_frequency }} 次</span>
            </div>

            <div
              v-if="adminActions.primary"
              class="mt-4 border-t border-default pt-4"
            >
              <div class="flex flex-wrap gap-2">
                <AppButton
                  size="md"
                  :variant="adminActions.primary.variant"
                  :loading="acting"
                  @click="dispatchAction(adminActions.primary)"
                >
                  {{ adminActions.primary.label }}
                </AppButton>
                <AppButton
                  v-for="action in adminActions.secondary"
                  :key="action.key"
                  size="md"
                  :variant="action.variant"
                  :disabled="acting"
                  @click="dispatchAction(action)"
                >
                  {{ action.label }}
                </AppButton>
              </div>
            </div>
          </section>

          <!-- 订单状态横条 + 成交主链投递进度（Application Status 辅助层，与订单层分离）：
               横条一屏收纳，替代纵向时间线；各步骤时间在悬停提示里 -->
          <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
            <h3 class="text-sm font-semibold text-primary">订单进度</h3>
            <div class="mt-3">
              <OrderStageBar :status="order.status" />
            </div>

            <template v-if="dealApplication">
              <div class="my-4 border-t border-default" />
              <h3 class="text-sm font-semibold text-primary">
                当前教员进度 · {{ dealApplication.teacher?.name || `教员 #${dealApplication.teacher_id}` }}
              </h3>
              <div class="mt-3">
                <ApplicationStepper :application="dealApplication" />
              </div>
            </template>
          </section>

          <!-- 订单信息 -->
          <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
            <h3 class="text-sm font-semibold text-primary">教学要求</h3>
            <p class="whitespace-pre-line text-sm leading-6 text-secondary">
              {{ order.requirements || "暂无额外要求" }}
            </p>
            <div class="my-3 border-t border-default" />
            <h3 class="text-sm font-semibold text-primary">原始完整信息</h3>
            <p class="mt-2 whitespace-pre-line rounded-lg bg-surface-soft p-3 text-sm leading-6 text-secondary">
              {{ order.raw_text }}
            </p>
            <div class="mt-2 text-right text-[11px] tracking-wide text-muted">订单编号 {{ order.raw_id }}</div>
          </section>
        </div>

        <!-- ── Sidebar ── -->
        <div class="space-y-4">
          <!-- 教员投递：可操作的 ApplicationCard——跟进动作（确认尾款/试课失败/没收/完成/评价）原地可用 -->
          <section class="space-y-3">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold text-primary">教员投递 · 跟进操作</h3>
              <button
                class="text-xs font-medium text-brand-700"
                @click="router.push({ path: '/admin/applications', query: { order: String(order.id) } })"
              >
                去审核 →
              </button>
            </div>
            <div
              v-if="applications.length"
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
            <AppEmpty
              v-else
              icon="📭"
              title="暂无教员投递"
              :description="order.status === 'recruiting' ? '订单已发布，等待合适的教员投递' : '该订单没有收到投递'"
            />
          </section>

          <!-- 资金状态：金额/状态/时间来自 API（共享 C 端适配器，前端不复算） -->
          <OrderFinancialSummary
            v-if="financialRows.length"
            :rows="financialRows"
          />
          <div
            v-else
            class="rounded-2xl border border-default bg-surface p-4 shadow-card"
          >
            <h3 class="text-sm font-semibold text-primary">资金状态</h3>
            <p class="mt-2 text-xs leading-5 text-muted">
              {{ order.needs_manual_price ? "自带价订单：待教员报价后生成费用结构。" : "暂无资金记录。" }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div
      v-else
      class="flex flex-col items-center justify-center py-20 text-muted"
    >
      <van-icon
        name="warning-o"
        size="48"
      />
      <p class="mt-4">{{ loadFailed ? "订单加载失败，请稍后重试" : "订单不存在或已下架" }}</p>
      <button
        class="mt-4 rounded-lg bg-surface-soft px-4 py-2 text-sm text-secondary"
        @click="loadAll"
      >
        重新加载
      </button>
    </div>

    <!-- 跟进弹层：与 ApplicationsReview 共用同一组组件（置于 v-if/v-else 链之外） -->
    <ReviewPopup
      v-model:show="reviewVisible"
      :app="reviewApp"
      @submitted="loadAll"
    />

    <ApplicationDetailDialog
      v-model:show="detailVisible"
      :application="detailApplication"
      @blacklisted="loadAll"
    />

    <TrialFailedPopup
      v-model:show="trialFormVisible"
      :app="trialFormApp"
      @confirmed="loadAll"
    />
  </AdminShell>
</template>

<style scoped>
/* 本页导航条压窄（Vant 默认 46px）：给内容多让一截纵向空间 */
:deep(.van-nav-bar) {
  --van-nav-bar-height: 40px;
}
</style>
