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
import AdminTabbar from "@/components/AdminTabbar.vue";
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppEmpty from "@/components/ui/AppEmpty.vue";
import OrderTimeline from "@/components/business/OrderTimeline.vue";
import OrderFinancialSummary from "@/components/business/OrderFinancialSummary.vue";
import TeacherProfileCard from "@/components/business/TeacherProfileCard.vue";
import { buildOrderLifecycleSteps, buildApplicationLifecycleSteps } from "@/components/business/timeline";
import { buildAdminOrderActions, type OrderActionViewModel } from "@/components/business/order/orderActions";
import { buildOrderFinancialRows, pickDealApplication } from "@/components/business/order/financialRows";

/**
 * B 端 Order Workspace（Batch 04 核心）：
 * 与 C 端 Order Workspace 共享 Order Domain（OrderTimeline/财务行适配/状态口径），
 * 仅 Adapter 与布局不同——桌面 Main+Sidebar，移动单列。
 * 状态流转动作深链到 ApplicationsReview 工作流（?order= 深链已存在）；
 * 归档/重新发布为本页直接动作（二次确认 + 后端把关）。
 */
const route = useRoute();
const router = useRouter();

const order = ref<OrderDetailData | null>(null);
const applications = ref<ApplicationItem[]>([]);
const loading = ref(true);
const loadFailed = ref(false);
const acting = ref(false);

const lifecycleSteps = computed(() => (order.value ? buildOrderLifecycleSteps(order.value) : []));

// 资金状态所属投递：优先已进入资金流的那条（共享适配器，C 端同一套逻辑）
const dealApplication = computed(() => pickDealApplication(applications.value));
const financialRows = computed(() => {
  const o = order.value;
  if (!o) return [];
  return buildOrderFinancialRows(o, dealApplication.value, formatDateTime);
});

// 面向教员的投递进度：选中（成交主链）投递时展示其生命周期
const dealSteps = computed(() =>
  dealApplication.value ? buildApplicationLifecycleSteps(dealApplication.value) : []
);

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
  if (!order.value) return;
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
  if (!order.value) return;
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

onMounted(loadAll);

async function loadAll() {
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
    order.value = null;
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="admin-page min-h-screen bg-page pb-24">
    <van-nav-bar title="订单工作区" left-arrow @click-left="router.push('/admin/orders')" />

    <div
      v-if="loading"
      class="flex justify-center py-20"
    >
      <van-loading type="spinner" />
    </div>

    <div
      v-else-if="order"
      class="mx-auto w-full max-w-5xl px-4 pt-4 lg:px-6"
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

          <!-- 订单生命周期（复用 C 端 Order Domain，OrderStatus 驱动） -->
          <section class="rounded-2xl border border-default bg-surface p-5 shadow-card">
            <h3 class="text-sm font-semibold text-primary">订单生命周期</h3>
            <div class="mt-3">
              <OrderTimeline :steps="lifecycleSteps" />
            </div>

            <!-- 成交主链投递的进度（Application Status 辅助层，与订单层分离） -->
            <template v-if="dealApplication">
              <div class="my-4 border-t border-default" />
              <h3 class="text-sm font-semibold text-primary">
                当前教员进度 · {{ dealApplication.teacher?.name || `教员 #${dealApplication.teacher_id}` }}
              </h3>
              <div class="mt-3">
                <OrderTimeline
                  compact
                  :steps="dealSteps"
                />
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
            <div class="mt-2 text-right text-[11px] tracking-wide text-slate-400">订单编号 {{ order.raw_id }}</div>
          </section>
        </div>

        <!-- ── Sidebar ── -->
        <div class="space-y-4">
          <!-- 教员 / 投递（TeacherProfileCard：真实 TeacherSummary 字段） -->
          <section class="rounded-2xl border border-default bg-surface p-4 shadow-card">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold text-primary">教员投递</h3>
              <button
                class="text-xs font-medium text-brand-700"
                @click="router.push({ path: '/admin/applications', query: { order: String(order.id) } })"
              >
                去审核 →
              </button>
            </div>
            <div
              v-if="applications.length"
              class="mt-3 divide-y divide-slate-100"
            >
              <div
                v-for="app in applications"
                :key="app.id"
                class="py-3 first:pt-0 last:pb-0"
              >
                <div class="flex items-start justify-between gap-2">
                  <TeacherProfileCard
                    :teacher="app.teacher || { id: app.teacher_id, name: `教员 #${app.teacher_id}`, school: '', gender: '', is_985: false, is_211: false, is_985_211: false, is_double_first_class: false }"
                    compact
                  />
                  <span class="shrink-0 rounded-full bg-surface-soft px-2 py-0.5 text-[10px] text-secondary">
                    {{ formatDateTime(app.applied_at) }}
                  </span>
                </div>
                <div class="mt-1 text-[11px] text-muted">
                  投递状态：{{ app.status === 'pending' ? '待审核' : app.status === 'shortlisted' ? '候选中' : app.status === 'trial_in_progress' ? '试课中' : app.status === 'completed' ? '已成交' : app.status }}
                </div>
              </div>
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
      class="flex flex-col items-center justify-center py-20 text-slate-400"
    >
      <van-icon
        name="warning-o"
        size="48"
      />
      <p class="mt-4">{{ loadFailed ? "订单加载失败，请稍后重试" : "订单不存在或已下架" }}</p>
      <button
        class="mt-4 rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-600"
        @click="loadAll"
      >
        重新加载
      </button>
    </div>

    <AdminTabbar />
  </div>
</template>
