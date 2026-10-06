<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import type { OrderBrief, OrderStatus } from "@/api/types";
import client from "@/api/client";
import { usePagedList } from "@/composables/usePagedList";
import { ORDER_STATUS_COLORS, ORDER_STATUS_LABELS } from "@/constants/orderStatus";
import { todayStr, parseDbTime } from "@/utils/format";
import AdminShell from "@/components/admin/AdminShell.vue";
import EditOrderPopup from "@/components/admin/EditOrderPopup.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import { showToast, showSuccessToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";
import { useSmartBack } from "@/composables/useSmartBack";

const router = useRouter();
const { goBack } = useSmartBack("/admin/dashboard");
const statusFilter = ref("");
const searchKeyword = ref("");
const batchMode = ref(false);
const batchSaving = ref(false);
const checkedIds = ref<Set<number>>(new Set());
const showEdit = ref(false);
const editingOrderId = ref<number | null>(null);

function openEdit(orderId: number) {
  editingOrderId.value = orderId;
  showEdit.value = true;
}

const route = useRoute();

const pagedList = usePagedList<OrderBrief>((page, pageSize) =>
  ordersApi.listOrders(page, pageSize, statusFilter.value || undefined, searchKeyword.value.trim() || undefined)
);
const { items: orders, total: totalCount, loading, loadingMore, hasMore } = pagedList;

async function loadOrders() {
  try {
    await pagedList.load();
  } catch (e) {
    showToast(getApiErrorMessage(e, "加载订单失败，请下拉重试"));
    return;
  }
  // 批量选择跟随最新列表：已不在列表中的订单自动移出勾选
  checkedIds.value = new Set([...checkedIds.value].filter((id) => orders.value.some((order) => order.id === id)));
}

async function loadMore() {
  try {
    await pagedList.loadMore();
  } catch {
    showToast("加载更多失败，请重试");
  }
}

function handleSearch() {
  router.replace({
    query: { ...route.query, status: statusFilter.value || undefined, q: searchKeyword.value.trim() || undefined },
  });
  loadOrders();
}

const exporting = ref(false);

async function exportOrders() {
  exporting.value = true;
  try {
    // 导出与所见一致：带上当前的状态筛选与搜索关键字
    const res = await client.get(
      ordersApi.ordersExportUrl(statusFilter.value || undefined, searchKeyword.value.trim() || undefined),
      { responseType: "blob" },
    );
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `订单列表_${todayStr()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast(getApiErrorMessage(e, "导出失败"));
  } finally {
    exporting.value = false;
  }
}

// 筛选状态与关键字同步到 URL：刷新/分享链接不丢参
watch(statusFilter, (value) => {
  router.replace({
    query: { ...route.query, status: value || undefined, q: searchKeyword.value.trim() || undefined },
  });
});

function clearSearch() {
  searchKeyword.value = "";
  handleSearch();
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value;
  checkedIds.value = new Set();
}

function toggleCheck(orderId: number) {
  const next = new Set(checkedIds.value);
  if (next.has(orderId)) {
    next.delete(orderId);
  } else {
    next.add(orderId);
  }
  checkedIds.value = next;
}

function toggleAllVisible() {
  if (checkedIds.value.size === orders.value.length) {
    checkedIds.value = new Set();
    return;
  }
  checkedIds.value = new Set(orders.value.map((order) => order.id));
}

/* ── 桌面表格增强：全选态 + 快捷键 ─────────────────────────────
   中介每天要处理几十单，桌面端必须比移动端快。移动端卡片流无物理键盘，
   因此快捷键只在 ≥1024px 生效；焦点在输入框时全部让路。
     /        聚焦搜索
     b        进出批量模式
     Ctrl/⌘+A  全选当前页
     Esc      退出批量 / 清空选择
     r        刷新                                              */
const tableCols = computed(() =>
  batchMode.value
    ? "grid-cols-[28px_minmax(0,3fr)_96px_minmax(0,3fr)_64px_88px_56px_136px]"
    : "grid-cols-[minmax(0,3fr)_96px_minmax(0,3fr)_64px_88px_56px_136px]",
);

const allVisibleChecked = computed(
  () => orders.value.length > 0 && orders.value.every((o) => checkedIds.value.has(o.id)),
);
const someVisibleChecked = computed(
  () => !allVisibleChecked.value && orders.value.some((o) => checkedIds.value.has(o.id)),
);

/** `/` 聚焦搜索：Vant Search 的内部 input 无稳定 ref，改用带类名的原生聚焦。
 *  类名限定在本页，避免命中 AdminShell 顶栏的搜索。 */
function focusSearch() {
  const el = document.querySelector<HTMLInputElement>(".orders-search-input .van-search__input");
  el?.focus();
}


function isTypingTarget(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  return t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable;
}

function onKeydown(e: KeyboardEvent) {
  if (typeof window !== "undefined" && !window.matchMedia("(min-width: 1024px)").matches) return;
  if (isTypingTarget(e)) {
    if (e.key === "Escape") (e.target as HTMLElement).blur();
    return;
  }
  const mod = e.ctrlKey || e.metaKey;

  if (mod && e.key.toLowerCase() === "a") {
    e.preventDefault();
    if (!batchMode.value) toggleBatchMode();
    toggleAllVisible();
    return;
  }
  if (e.key === "Escape") {
    if (batchMode.value) toggleBatchMode();
    else if (checkedIds.value.size) checkedIds.value = new Set();
    return;
  }
  if (e.key === "/") {
    e.preventDefault();
    focusSearch();
    return;
  }
  if (e.key.toLowerCase() === "b") {
    e.preventDefault();
    toggleBatchMode();
    return;
  }
  if (e.key.toLowerCase() === "r") {
    e.preventDefault();
    void loadOrders();
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));

async function handleBatchStatus(targetStatus: string) {
  const ids = [...checkedIds.value];
  if (!ids.length) {
    showToast("请先选择订单");
    return;
  }

  const label = statusLabels[targetStatus as OrderStatus] || targetStatus;
  // 影响预告：列出勾选单当前状态分布，混状态批量不再盲确认
  const distribution = Object.entries(
    orders.value
      .filter((order) => ids.includes(order.id))
      .reduce<Record<string, number>>((acc, order) => {
        acc[order.status] = (acc[order.status] || 0) + 1;
        return acc;
      }, {})
  )
    .map(([status, count]) => `${statusLabels[status as OrderStatus] || status} ${count} 条`)
    .join("、");
  const ok = await appConfirm({
    title: `批量设为${label}？`,
    message: `选中 ${ids.length} 条：${distribution}。确认后统一设为「${label}」。`,
    confirmText: "确认",
  });
  if (!ok) return;

  batchSaving.value = true;
  try {
    const res = await ordersApi.batchStatus(ids, targetStatus);
    const skipped = res.skipped || 0;
    if (skipped > 0) {
      // 后端 skipped 为纯计数（已是目标状态或 id 不存在，无明细）——
      // 分解汇报消掉"批量黑洞"：用户知道哪些没动、原因是什么、无需重试
      await appConfirm({
        title: `已更新 ${res.updated || 0} 条，跳过 ${skipped} 条`,
        message: "跳过的订单已是目标状态（或已不存在），无需处理。",
        confirmText: "知道了",
      });
    } else {
      showSuccessToast(`已更新 ${res.updated || 0} 条订单`);
    }
    checkedIds.value = new Set();
    batchMode.value = false;
    await loadOrders();
  } catch (e) {
    showToast(getApiErrorMessage(e, "批量操作未完成：网络异常，请检查网络后重试"));
  } finally {
    batchSaving.value = false;
  }
}

async function handleArchive(orderId: number) {
  const ok = await appConfirm({
    title: "确认归档？",
    message: "归档后订单将不在橱窗展示",
    confirmText: "归档",
    danger: true,
  });
  if (!ok) return;
  try {
    await ordersApi.archive(orderId);
    showToast("已归档");
    await loadOrders();
  } catch (e) {
    showToast(getApiErrorMessage(e, "归档失败"));
  }
}

async function handleRepublish(orderId: number) {
  const ok = await appConfirm({
    title: "重新发布？",
    message: "订单会回到招聘中，并重新出现在教员橱窗",
    confirmText: "重新发布",
  });
  if (!ok) return;
  try {
    await ordersApi.republish(orderId);
    showSuccessToast("已重新发布");
    await loadOrders();
  } catch (e) {
    showToast(getApiErrorMessage(e, "重新发布失败"));
  }
}

// 状态文案/配色唯一口径在 constants/orderStatus.ts（与仪表盘共用）
const statusColors = ORDER_STATUS_COLORS;

const statusLabels = ORDER_STATUS_LABELS;

function fmtCreated(value?: string | null) {
  if (!value) return "";
  // 后端 naive UTC：补 Z 按 UTC 解析再取本地月/日
  const d = parseDbTime(value);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
}

onMounted(() => {
  const initialStatus = String(route.query.status || "");
  if (initialStatus && statusLabels[initialStatus as OrderStatus]) {
    statusFilter.value = initialStatus;
  }
  const initialKeyword = String(route.query.q || "");
  if (initialKeyword) {
    searchKeyword.value = initialKeyword;
  }
  loadOrders();
});

const selectedCount = computed(() => checkedIds.value.size);

// ── 看板视图（UI 2.0）：四列状态流总览，仅展示 + 点击进工作区（拖拽不在本期）──
// 每列独立调用既有列表接口拿真实 total + 前 20 张卡：分页列表前端分组会算错列数，
// 故按状态并行拉取（无新后端）；带搜索关键字、不带状态筛选（看板本身就是全状态总览）
const viewMode = ref<"list" | "kanban">("list");
const KANBAN_COLUMNS: { status: OrderStatus }[] = [
  { status: "recruiting" },
  { status: "trial_in_progress" },
  { status: "completed" },
  { status: "archived" },
];
const kanbanLoading = ref(false);
const kanbanLoaded = ref(false);
const kanban = ref<Record<OrderStatus, { items: OrderBrief[]; total: number; failed?: boolean }>>({
  recruiting: { items: [], total: 0 },
  trial_in_progress: { items: [], total: 0 },
  completed: { items: [], total: 0 },
  archived: { items: [], total: 0 },
});

// 列级加载与重试：单列失败不再连坐整板（此前 Promise.all 一挂全空白、只剩一句 toast）
async function loadKanbanColumn(status: OrderStatus, keyword?: string) {
  try {
    const res = await ordersApi.listOrders(1, 20, status, keyword);
    kanban.value[status] = { items: res.items || [], total: res.total };
  } catch {
    kanban.value[status] = { items: [], total: 0, failed: true };
  }
}

async function loadKanban() {
  kanbanLoading.value = true;
  const keyword = searchKeyword.value.trim() || undefined;
  await Promise.all(KANBAN_COLUMNS.map((col) => loadKanbanColumn(col.status, keyword)));
  kanbanLoaded.value = true;
  kanbanLoading.value = false;
}

function retryKanbanColumn(status: OrderStatus) {
  void loadKanbanColumn(status, searchKeyword.value.trim() || undefined);
}

watch(viewMode, (mode) => {
  if (mode === "kanban") void loadKanban();
});

/** 移动端看板「查看全部 N 单」：跳到对应状态筛选的列表视图（列表承担翻页/搜索） */
function jumpToList(status: OrderStatus) {
  statusFilter.value = status;
  viewMode.value = "list";
  checkedIds.value = new Set();
  void loadOrders();
}
</script>

<template>
  <AdminShell fluid>
    <van-nav-bar
      title="订单管理"
      left-arrow
      :right-text="batchMode ? '取消' : '批量'"
      @click-left="goBack"
      @click-right="toggleBatchMode"
    />

    <!-- 工具栏：搜索 + 查找 + 录单（导入入口自底栏下沉至此） + 导出 -->
    <div class="px-4 pt-3">
      <div class="flex items-center gap-1.5 rounded-xl border border-default bg-white p-1 shadow-sm">
        <van-search
          v-model="searchKeyword"
          class="orders-search-input min-w-0 flex-1 !p-0"
          shape="round"
          placeholder="输入订单编号查找"
          background="transparent"
          @search="handleSearch"
          @clear="clearSearch"
        />
        <AppButton
          size="sm"
          class="shrink-0"
          :disabled="!searchKeyword.trim()"
          @click="handleSearch"
        >
          查找
        </AppButton>
        <AppButton size="sm" class="shrink-0" @click="router.push('/admin/batch-import')">
          <van-icon name="add-o" size="13" />
          录单
        </AppButton>
        <button
          class="flex shrink-0 items-center gap-1 rounded-full border border-default px-3 py-2 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-50"
          :disabled="exporting"
          @click="exportOrders"
        >
          <van-icon name="description" size="13" />
          {{ exporting ? "导出中" : "导出" }}
        </button>
      </div>
    </div>

    <!-- 状态筛选 + 视图切换（看板/列表，UI 2.0 胶囊分段）。
         两端不同适配：移动端单行——chips 可横滑、切换钮右钉、计数收起（底部"加载更多 N/总"已示总数）；
         桌面端单行——chips + 切换 + 计数齐排 -->
    <div class="mb-3 mt-3 flex items-center gap-2 px-4">
      <div v-show="viewMode === 'list'" class="flex flex-1 gap-2 overflow-x-auto pb-0.5">
        <button
          v-for="(label, key) in statusLabels" :key="key"
          class="shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors"
          :class="statusFilter === key
            ? 'border-ink bg-ink text-white'
            : 'border-default bg-white text-secondary hover:border-strong'"
          @click="statusFilter = statusFilter === key ? '' : key; checkedIds = new Set(); loadOrders()"
        >
          {{ label }}
        </button>
      </div>
      <div class="ml-auto flex shrink-0 items-center rounded-full border border-default bg-surface p-0.5">
        <button
          class="rounded-full px-2.5 py-1 text-caption font-semibold"
          :class="viewMode === 'kanban' ? 'bg-ink text-white' : 'text-secondary'"
          @click="viewMode = 'kanban'"
        >
          看板
        </button>
        <button
          class="rounded-full px-2.5 py-1 text-caption font-semibold"
          :class="viewMode === 'list' ? 'bg-ink text-white' : 'text-secondary'"
          @click="viewMode = 'list'"
        >
          列表
        </button>
      </div>
      <span v-if="viewMode === 'list'" class="hidden shrink-0 text-xs text-muted lg:inline">共 {{ totalCount }} 条</span>
    </div>

    <div v-if="batchMode" class="px-4 pt-2">
        <button
          class="w-full rounded-full border border-dashed border-strong bg-white py-2 text-xs font-medium text-ink"
          @click="toggleAllVisible"
        >
        {{ selectedCount === orders.length && orders.length ? "取消本页全选" : "本页全选" }}
      </button>
    </div>

    <!-- 看板视图：两端不同形态。
         移动端 = 纵向状态分组（横滑窄列在手机上难用）：每状态一节、节内最近 5 单，
         超出给「查看全部 N 单 →」一键跳到对应筛选的列表；桌面 = 四列网格总览（保持不动） -->
    <div v-if="viewMode === 'kanban'" class="mt-3 px-4 pb-6">
      <div v-if="kanbanLoading && !kanbanLoaded" class="flex justify-center py-16">
        <van-loading type="spinner" />
      </div>
      <template v-else>
        <!-- 移动端：纵向分组 -->
        <div class="space-y-5 lg:hidden">
          <section v-for="col in KANBAN_COLUMNS" :key="col.status">
            <header class="mb-2 flex items-center gap-2">
              <AppStatusBadge :status="col.status" />
              <span class="text-caption tabular-nums text-muted">{{ kanban[col.status].total }}</span>
            </header>
            <div class="space-y-2">
              <button
                v-for="order in kanban[col.status].items.slice(0, 5)"
                :key="order.id"
                class="w-full rounded-xl border border-default bg-surface px-3 py-2.5 text-left transition-colors hover:bg-surface-soft"
                @click="router.push(`/admin/orders/${order.id}`)"
              >
                <div class="flex items-baseline justify-between gap-2">
                  <span class="min-w-0 truncate text-body font-semibold text-primary">{{ order.grade_subject }}</span>
                  <span class="shrink-0 text-body font-bold tabular-nums text-ink">¥{{ order.calculated_info_fee }}</span>
                </div>
                <div class="mt-0.5 truncate text-caption text-muted">#{{ order.raw_id }} · {{ order.fuzzy_address }}</div>
              </button>
              <button
                v-if="kanban[col.status].failed"
                class="w-full rounded-xl border border-dashed border-default px-2 py-4 text-center text-caption text-muted transition-colors hover:bg-surface-soft"
                @click="retryKanbanColumn(col.status)"
              >
                本列加载失败：网络波动，<span class="font-medium text-link">点击重试</span>
              </button>
              <p
                v-else-if="!kanban[col.status].items.length"
                class="rounded-xl border border-dashed border-default px-2 py-4 text-center text-caption text-muted"
              >
                暂无{{ statusLabels[col.status] }}订单
              </p>
              <button
                v-if="kanban[col.status].total > kanban[col.status].items.length || kanban[col.status].items.length > 5"
                class="w-full rounded-xl border border-dashed border-default py-2 text-center text-caption font-medium text-secondary transition-colors hover:bg-surface-soft"
                @click="jumpToList(col.status)"
              >
                查看全部 {{ kanban[col.status].total }} 单 →
              </button>
            </div>
          </section>
        </div>

        <!-- 桌面：四列状态流（列头色点+名称+真实总数；每列最多展示 20 单） -->
        <div class="hidden gap-3 lg:grid lg:grid-cols-4">
          <section
            v-for="col in KANBAN_COLUMNS"
            :key="col.status"
            class="rounded-2xl border border-default bg-surface p-3 shadow-card"
          >
            <header class="flex items-center gap-2 px-1 pb-2.5">
              <AppStatusBadge :status="col.status" />
              <span class="ml-auto text-caption tabular-nums text-muted">{{ kanban[col.status].total }}</span>
            </header>
            <div class="space-y-2">
              <button
                v-for="order in kanban[col.status].items"
                :key="order.id"
                class="w-full rounded-xl border border-default bg-surface px-3 py-2.5 text-left transition-colors hover:bg-surface-soft"
                @click="router.push(`/admin/orders/${order.id}`)"
              >
                <div class="truncate text-body font-semibold text-primary">{{ order.grade_subject }}</div>
                <div class="mt-0.5 flex items-baseline gap-1.5">
                  <span class="text-body font-bold tabular-nums text-ink">¥{{ order.calculated_info_fee }}</span>
                  <span class="text-caption text-muted">信息费</span>
                </div>
                <div class="mt-0.5 truncate text-caption text-muted">#{{ order.raw_id }} · {{ order.fuzzy_address }}</div>
              </button>
              <button
                v-if="kanban[col.status].failed"
                class="w-full rounded-xl border border-dashed border-default px-2 py-5 text-center text-caption text-muted transition-colors hover:bg-surface-soft"
                @click="retryKanbanColumn(col.status)"
              >
                本列加载失败：网络波动，<span class="font-medium text-link">点击重试</span>
              </button>
              <p
                v-else-if="!kanban[col.status].items.length"
                class="rounded-xl border border-dashed border-default px-2 py-5 text-center text-caption text-muted"
              >
                暂无{{ statusLabels[col.status] }}订单
              </p>
            </div>
          </section>
        </div>
      </template>
    </div>

    <van-pull-refresh v-else v-model="loading" @refresh="loadOrders">
      <!-- 首屏骨架：仅在列表尚无内容时占位，下拉刷新/翻页不闪骨架 -->
      <div v-if="loading && orders.length === 0" class="mx-4 mt-4 space-y-2.5">
        <div
          v-for="i in 3" :key="i"
          class="rounded-xl border border-default bg-white px-3.5 py-4"
        >
          <van-skeleton title :row="2" title-width="45%" row-width="90%" />
        </div>
      </div>

      <div v-else-if="orders.length === 0" class="mx-4 mt-4 flex min-h-[calc(100vh-260px)] flex-col items-center justify-center rounded-xl border border-dashed border-default bg-white text-muted">
        <div class="flex h-12 w-12 items-center justify-center rounded-full bg-surface-soft">
          <van-icon name="orders-o" size="22" />
        </div>
        <p class="mt-3 text-sm text-secondary">暂无订单</p>
        <p class="mt-1 text-xs text-muted">粘贴微信文本，AI 自动解析成可上架订单</p>
        <AppButton size="md" class="mt-3" @click="router.push('/admin/batch-import')">
          去批量录单
        </AppButton>
      </div>

      <template v-else>
      <div class="space-y-2.5 px-4 lg:hidden">
        <div
          v-for="order in orders" :key="order.id"
          class="order-card cursor-pointer rounded-xl border bg-white px-3.5 py-3 transition-colors"
          :class="checkedIds.has(order.id)
            ? 'border-strong bg-surface-soft/40 ring-1 ring-default'
            : 'border-default hover:border-strong'"
          @click="batchMode ? toggleCheck(order.id) : router.push(`/admin/orders/${order.id}`)"
        >
          <div class="flex items-baseline justify-between gap-3">
            <div class="flex min-w-0 items-baseline gap-2">
              <van-checkbox
                v-if="batchMode"
                :model-value="checkedIds.has(order.id)"
                class="shrink-0 self-center"
                @click.stop="toggleCheck(order.id)"
              />
              <span class="min-w-0 truncate text-left text-sm font-semibold text-primary">
                {{ order.grade_subject }}
              </span>
              <span class="shrink-0 text-xs text-secondary">{{ order.price_total }}</span>
            </div>
            <div class="text-brand-800 shrink-0 font-bold text-base leading-5 price-highlight">¥{{ order.calculated_info_fee }}</div>
          </div>

          <div class="mt-1.5 flex min-w-0 items-center gap-2 text-xs text-muted">
            <span
              class="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-caption font-medium ring-1"
              :class="statusColors[order.status]"
            >
              <span class="h-1 w-1 rounded-full bg-current"></span>
              {{ statusLabels[order.status] || order.status }}
            </span>
            <span class="shrink-0 text-caption tracking-wide text-muted">#{{ order.raw_id }}</span>
            <span class="flex min-w-0 items-center gap-1">
              <van-icon name="location-o" class="shrink-0" />
              <span class="truncate">{{ order.fuzzy_address }}</span>
            </span>
            <span v-if="order.weekly_frequency" class="hidden shrink-0 items-center gap-1 sm:flex">
              <van-icon name="clock-o" />每周{{ order.weekly_frequency }}次
            </span>
            <span class="ml-auto shrink-0 text-caption text-muted">{{ fmtCreated(order.created_at) }}</span>
          </div>

          <div class="mt-2.5 flex items-center gap-2 border-t border-default pt-2.5">
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 rounded-full border border-default py-1 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
              :disabled="batchMode"
              @click.stop="openEdit(order.id)"
            >
              编辑
            </button>
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 rounded-full border border-danger-soft bg-danger-soft/60 py-1 text-xs font-medium text-danger-deep hover:bg-danger-mid/60 disabled:opacity-40"
              :disabled="batchMode"
              @click.stop="handleArchive(order.id)"
            >
              归档
            </button>
            <button
              v-if="order.status === 'archived'"
              class="flex-1 rounded-full border border-default bg-surface-soft/60 py-1 text-xs font-medium text-secondary hover:bg-surface-soft/60 disabled:opacity-40"
              :disabled="batchMode"
              @click.stop="handleRepublish(order.id)"
            >
              重新发布
            </button>
          </div>
        </div>
      </div>

      <!-- 桌面列表（≥1024px）：宽屏工作台形态，一行一单、列对齐，不再沿用 H5 卡片流 -->
      <div class="hidden px-4 lg:block">
        <!-- 批量操作栏：桌面端选中即现，不必先切模式 -->
        <div
          v-if="checkedIds.size"
          class="mb-2 flex flex-wrap items-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2"
        >
          <span class="text-body-sm font-medium text-brand-800">
            已选 {{ checkedIds.size }} 条
          </span>
          <AppButton
            size="sm"
            :disabled="batchSaving"
            @click="handleBatchStatus('recruiting')"
          >
            设为招聘中
          </AppButton>
          <button
            class="rounded-full border border-default bg-surface px-3 py-1.5 text-body-sm font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
            :disabled="batchSaving"
            @click="handleBatchStatus('archived')"
          >
            批量归档
          </button>
          <button
            class="ml-auto text-body-sm text-brand-700"
            @click="checkedIds = new Set()"
          >
            取消选择
          </button>
        </div>

        <div class="overflow-hidden rounded-2xl border border-default bg-surface shadow-card">
          <div
            class="grid items-center gap-3 border-b border-default bg-surface-soft px-4 py-2.5 text-caption font-medium text-muted"
            :class="tableCols"
          >
            <span v-if="batchMode">
              <van-checkbox
                :model-value="allVisibleChecked"
                :indeterminate="someVisibleChecked"
                aria-label="全选本页"
                @click.stop="toggleAllVisible"
              />
            </span>
            <span>订单</span>
            <span>状态</span>
            <span>地址</span>
            <span>频次</span>
            <span class="text-right">信息费</span>
            <span>发布</span>
            <span class="text-right">操作</span>
          </div>
          <div
            v-for="order in orders" :key="order.id"
            class="grid items-center gap-3 border-b border-default px-4 py-3 text-sm text-secondary transition-colors last:border-b-0"
            :class="[tableCols, checkedIds.has(order.id) ? 'bg-brand-50/60' : 'hover:bg-surface-soft/70']"
          >
            <div v-if="batchMode">
              <van-checkbox
                :model-value="checkedIds.has(order.id)"
                :aria-label="`选择订单 ${order.raw_id}`"
                @click.stop="toggleCheck(order.id)"
              />
            </div>
            <div class="min-w-0">
              <button
                class="block w-full truncate text-left font-semibold text-primary hover:text-brand-700"
                @click.stop="router.push(`/admin/orders/${order.id}`)"
              >
                {{ order.grade_subject }}
              </button>
              <div class="text-caption tracking-wide text-muted">#{{ order.raw_id }} · {{ order.price_total }}</div>
            </div>
            <div><AppStatusBadge :status="order.status" /></div>
            <div class="flex min-w-0 items-center gap-1 text-xs text-secondary">
              <van-icon name="location-o" class="shrink-0" />
              <span class="truncate">{{ order.fuzzy_address }}</span>
            </div>
            <div class="text-xs text-secondary">{{ order.weekly_frequency ? `每周${order.weekly_frequency}次` : "—" }}</div>
            <div class="price-highlight text-right font-bold text-brand-800">¥{{ order.calculated_info_fee }}</div>
            <div class="text-xs text-muted">{{ fmtCreated(order.created_at) }}</div>
            <div class="flex items-center justify-end gap-1.5">
              <button
                v-if="order.status === 'recruiting'"
                class="rounded-full border border-default px-2.5 py-1 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
                :disabled="batchMode"
                @click="openEdit(order.id)"
              >
                编辑
              </button>
              <button
                v-if="order.status === 'recruiting'"
                class="rounded-full border border-danger-soft bg-danger-soft/60 px-2.5 py-1 text-xs font-medium text-danger-deep hover:bg-danger-mid/60 disabled:opacity-40"
                :disabled="batchMode"
                @click="handleArchive(order.id)"
              >
                归档
              </button>
              <button
                v-if="order.status === 'archived'"
                class="rounded-full border border-default px-2.5 py-1 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
                :disabled="batchMode"
                @click="handleRepublish(order.id)"
              >
                重新发布
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="px-4 pb-4">
        <button
          v-if="hasMore"
          class="w-full rounded-full border border-default bg-white py-2.5 text-sm font-medium text-brand-700 hover:bg-surface-soft disabled:opacity-50"
          :disabled="loadingMore"
          @click="loadMore"
        >
          <span v-if="loadingMore">加载中...</span>
          <span v-else>加载更多（{{ orders.length }}/{{ totalCount }}）</span>
        </button>
        <div v-else class="py-2 text-center text-xs text-muted">
          已显示全部 {{ totalCount }} 条订单
        </div>
      </div>
      </template>
    </van-pull-refresh>

    <EditOrderPopup v-model:show="showEdit" :order-id="editingOrderId" @saved="loadOrders" />

    <div v-if="batchMode" class="fixed bottom-[50px] left-0 right-0 z-20 border-t border-default bg-white p-3 shadow-[0_-4px_16px_rgba(23,24,28,0.06)]">
      <div class="mb-2 text-center text-xs text-muted">已选择 {{ selectedCount }} 条（成交需在投递审核中确认）</div>
      <div class="grid grid-cols-2 gap-2">
        <AppButton
          size="md"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('recruiting')"
        >
          设为招聘中
        </AppButton>
        <button
          class="rounded-xl border border-danger-mid bg-danger-soft/70 py-2.5 text-sm font-semibold text-danger-deep disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('archived')"
        >
          设为已归档
        </button>
      </div>
    </div>
  </AdminShell>
</template>
