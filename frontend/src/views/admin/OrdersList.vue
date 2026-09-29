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
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import { showToast, showSuccessToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";

const router = useRouter();
const statusFilter = ref("");
const searchKeyword = ref("");
const batchMode = ref(false);
const batchSaving = ref(false);
const checkedIds = ref<Set<number>>(new Set());
const showEdit = ref(false);
const saving = ref(false);
const editingOrder = ref<OrderBrief | null>(null);
/** 编辑表单字段集（与后端 OrderUpdateRequest 对齐的子集） */
interface OrderEditForm {
  grade_subject: string;
  requirements: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  is_summer_vacation: boolean;
  fuzzy_address: string;
  subway_remark: string;
  exact_address: string;
  parent_phone: string;
  lng: number;
  lat: number;
}
const editForm = ref<OrderEditForm | null>(null);

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
    ? "[28px_minmax(0,3fr)_96px_minmax(0,3fr)_64px_88px_56px_136px]"
    : "[minmax(0,3fr)_96px_minmax(0,3fr)_64px_88px_56px_136px]",
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
  const ok = await appConfirm({
    title: `批量设为${label}？`,
    message: `将处理 ${ids.length} 条订单`,
    confirmText: "确认",
  });
  if (!ok) return;

  batchSaving.value = true;
  try {
    const res = await ordersApi.batchStatus(ids, targetStatus);
    showSuccessToast(`已更新 ${res.updated || 0} 条订单`);
    checkedIds.value = new Set();
    batchMode.value = false;
    await loadOrders();
  } catch (e) {
    showToast(getApiErrorMessage(e, "批量操作失败"));
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

async function openEdit(orderId: number) {
  try {
    const detail = await ordersApi.getOrder(orderId);
    editingOrder.value = detail;
    editForm.value = {
      grade_subject: detail.grade_subject,
      requirements: detail.requirements || "",
      price_total: detail.price_total,
      base_price: detail.base_price,
      weekly_frequency: detail.weekly_frequency,
      is_summer_vacation: detail.is_summer_vacation,
      fuzzy_address: detail.fuzzy_address,
      subway_remark: detail.subway_remark || "",
      exact_address: detail.exact_address || "",
      parent_phone: detail.parent_phone || "",
      lng: detail.lng,
      lat: detail.lat,
    };
    showEdit.value = true;
  } catch (e) {
    showToast(getApiErrorMessage(e, "加载订单失败"));
  }
}

async function saveEdit() {
  if (!editingOrder.value || !editForm.value) return;
  const gradeSubject = String(editForm.value.grade_subject || "").trim();
  const priceTotal = String(editForm.value.price_total || "").trim();
  const fuzzyAddress = String(editForm.value.fuzzy_address || "").trim();
  if (!gradeSubject || !priceTotal || !fuzzyAddress) {
    showToast("请填写年级科目、课酬文本和展示地址");
    return;
  }
  editForm.value.grade_subject = gradeSubject;
  editForm.value.price_total = priceTotal;
  editForm.value.fuzzy_address = fuzzyAddress;
  saving.value = true;
  try {
    const updated = await ordersApi.updateOrder(editingOrder.value.id, editForm.value);
    editingOrder.value = updated;
    await loadOrders();
    showSuccessToast("已保存");
    showEdit.value = false;
  } catch (e) {
    showToast(getApiErrorMessage(e, "保存失败"));
  } finally {
    saving.value = false;
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
</script>

<template>
  <AdminShell fluid>
    <van-nav-bar
      title="订单管理"
      left-arrow
      :right-text="batchMode ? '取消' : '批量'"
      @click-left="router.push('/admin/dashboard')"
      @click-right="toggleBatchMode"
    />

    <!-- 工具栏：搜索 + 查找 + 导出 -->
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
        <button
          class="shrink-0 rounded-lg bg-brand-800 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
          :disabled="!searchKeyword.trim()"
          @click="handleSearch"
        >
          查找
        </button>
        <button
          class="flex shrink-0 items-center gap-1 rounded-lg border border-default px-3 py-2 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-50"
          :disabled="exporting"
          @click="exportOrders"
        >
          <van-icon name="description" size="13" />
          {{ exporting ? "导出中" : "导出" }}
        </button>
      </div>
    </div>

    <!-- 状态筛选 -->
    <div class="mt-3 flex items-center gap-2 px-4">
      <div class="flex flex-1 gap-2 overflow-x-auto pb-0.5">
        <button
          v-for="(label, key) in statusLabels" :key="key"
          class="shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors"
          :class="statusFilter === key
            ? 'border-brand-800 bg-brand-800 text-white'
            : 'border-default bg-white text-secondary hover:border-strong'"
          @click="statusFilter = statusFilter === key ? '' : key; checkedIds = new Set(); loadOrders()"
        >
          {{ label }}
        </button>
      </div>
      <span class="shrink-0 text-xs text-muted">共 {{ totalCount }} 条</span>
    </div>

    <div v-if="batchMode" class="px-4 pt-2">
      <button
        class="w-full rounded-lg border border-dashed border-strong bg-white py-2 text-xs font-medium text-brand-800"
        @click="toggleAllVisible"
      >
        {{ selectedCount === orders.length && orders.length ? "取消本页全选" : "本页全选" }}
      </button>
    </div>

    <van-pull-refresh v-model="loading" @refresh="loadOrders">
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
        <p class="mt-1 text-xs text-muted">去工作台「批量导入」，粘贴微信文本即可快速录单</p>
      </div>

      <template v-else>
      <div class="space-y-2.5 px-4 lg:hidden">
        <div
          v-for="order in orders" :key="order.id"
          class="order-card rounded-xl border bg-white px-3.5 py-3 transition-colors"
          :class="checkedIds.has(order.id)
            ? 'border-strong bg-surface-soft/40 ring-1 ring-default'
            : 'border-default hover:border-strong'"
        >
          <div class="flex items-baseline justify-between gap-3">
            <div class="flex min-w-0 items-baseline gap-2">
              <van-checkbox
                v-if="batchMode"
                :model-value="checkedIds.has(order.id)"
                class="shrink-0 self-center"
                @click.stop="toggleCheck(order.id)"
              />
              <button
                class="min-w-0 truncate text-left text-sm font-semibold text-primary hover:text-brand-800"
                @click.stop="router.push(`/admin/orders/${order.id}`)"
              >
                {{ order.grade_subject }}
              </button>
              <span class="shrink-0 text-xs text-secondary">{{ order.price_total }}</span>
            </div>
            <div class="text-brand-800 shrink-0 font-bold text-base leading-5 price-highlight">¥{{ order.calculated_info_fee }}</div>
          </div>

          <div class="mt-1.5 flex min-w-0 items-center gap-2 text-xs text-muted">
            <span
              class="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1"
              :class="statusColors[order.status]"
            >
              <span class="h-1 w-1 rounded-full bg-current"></span>
              {{ statusLabels[order.status] || order.status }}
            </span>
            <span class="shrink-0 text-[11px] tracking-wide text-muted">#{{ order.raw_id }}</span>
            <span class="flex min-w-0 items-center gap-1">
              <van-icon name="location-o" class="shrink-0" />
              <span class="truncate">{{ order.fuzzy_address }}</span>
            </span>
            <span v-if="order.weekly_frequency" class="hidden shrink-0 items-center gap-1 sm:flex">
              <van-icon name="clock-o" />每周{{ order.weekly_frequency }}次
            </span>
            <span class="ml-auto shrink-0 text-[11px] text-muted">{{ fmtCreated(order.created_at) }}</span>
          </div>

          <div class="mt-2.5 flex items-center gap-2 border-t border-default pt-2.5">
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 rounded-lg border border-default py-1 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
              :disabled="batchMode"
              @click="openEdit(order.id)"
            >
              编辑
            </button>
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 rounded-lg border border-danger-soft bg-danger-soft/60 py-1 text-xs font-medium text-danger-deep hover:bg-danger-mid/60 disabled:opacity-40"
              :disabled="batchMode"
              @click="handleArchive(order.id)"
            >
              归档
            </button>
            <button
              v-if="order.status === 'archived'"
              class="flex-1 rounded-lg border border-default bg-surface-soft/60 py-1 text-xs font-medium text-secondary hover:bg-surface-soft/60 disabled:opacity-40"
              :disabled="batchMode"
              @click="handleRepublish(order.id)"
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
          <span class="text-[12px] font-medium text-brand-800">
            已选 {{ checkedIds.size }} 条
          </span>
          <button
            class="rounded-lg bg-brand-800 px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-40"
            :disabled="batchSaving"
            @click="handleBatchStatus('recruiting')"
          >
            设为招聘中
          </button>
          <button
            class="rounded-lg border border-default bg-surface px-3 py-1.5 text-[12px] font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
            :disabled="batchSaving"
            @click="handleBatchStatus('archived')"
          >
            批量归档
          </button>
          <button
            class="ml-auto text-[12px] text-brand-700"
            @click="checkedIds = new Set()"
          >
            取消选择
          </button>
        </div>

        <div class="overflow-hidden rounded-2xl border border-default bg-surface shadow-card">
          <div
            class="grid items-center gap-3 border-b border-default bg-surface-soft px-4 py-2.5 text-[11px] font-medium text-muted"
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
              <div class="text-[11px] tracking-wide text-muted">#{{ order.raw_id }} · {{ order.price_total }}</div>
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
                class="rounded-lg border border-default px-2.5 py-1 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
                :disabled="batchMode"
                @click="openEdit(order.id)"
              >
                编辑
              </button>
              <button
                v-if="order.status === 'recruiting'"
                class="rounded-lg border border-danger-soft bg-danger-soft/60 px-2.5 py-1 text-xs font-medium text-danger-deep hover:bg-danger-mid/60 disabled:opacity-40"
                :disabled="batchMode"
                @click="handleArchive(order.id)"
              >
                归档
              </button>
              <button
                v-if="order.status === 'archived'"
                class="rounded-lg border border-default px-2.5 py-1 text-xs font-medium text-secondary hover:bg-surface-soft disabled:opacity-40"
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
          class="w-full rounded-xl border border-default bg-white py-2.5 text-sm font-medium text-brand-700 hover:bg-surface-soft disabled:opacity-50"
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

    <van-popup v-model:show="showEdit" position="bottom" round>
      <div v-if="editForm" class="p-4 max-h-[82vh] overflow-y-auto">
        <div class="mb-3 flex items-center justify-between">
          <div class="min-w-0">
            <div class="text-base font-semibold text-primary">编辑订单</div>
            <div class="mt-0.5 truncate text-xs text-muted">#{{ editingOrder?.raw_id }} · {{ editingOrder?.grade_subject }}</div>
          </div>
          <button
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-soft text-secondary"
            @click="showEdit = false"
          >
            <van-icon name="cross" />
          </button>
        </div>
        <van-cell-group inset>
          <van-field v-model="editForm.grade_subject" label="年级科目" />
          <van-field v-model="editForm.price_total" label="课酬文本" />
          <van-field v-model.number="editForm.base_price" label="单次课酬" type="number" />
          <van-field v-model.number="editForm.weekly_frequency" label="每周次数" type="number" />
          <van-field v-model="editForm.fuzzy_address" label="展示地址" />
          <van-field v-model="editForm.subway_remark" label="交通备注" />
          <van-field v-model="editForm.exact_address" label="真实地址" />
          <van-field v-model="editForm.parent_phone" label="家长电话" />
          <van-field v-model.number="editForm.lng" label="经度" type="number" />
          <van-field v-model.number="editForm.lat" label="纬度" type="number" />
          <van-field v-model="editForm.requirements" label="教员要求" type="textarea" rows="3" />
          <van-cell title="寒暑假单">
            <template #right-icon>
              <van-switch v-model="editForm.is_summer_vacation" size="20" />
            </template>
          </van-cell>
        </van-cell-group>
        <div class="mt-4 grid grid-cols-2 gap-3">
          <button class="rounded-xl border border-default bg-white py-2.5 text-sm font-medium text-secondary" @click="showEdit = false">取消</button>
          <button
            class="header-gradient rounded-xl py-2.5 text-sm font-semibold text-white disabled:opacity-60"
            :disabled="saving"
            @click="saveEdit"
          >
            保存
          </button>
        </div>
      </div>
    </van-popup>

    <div v-if="batchMode" class="fixed bottom-[50px] left-0 right-0 z-20 border-t border-default bg-white/95 p-3 shadow-[0_-4px_16px_rgba(23,24,28,0.06)] backdrop-blur">
      <div class="mb-2 text-center text-xs text-muted">已选择 {{ selectedCount }} 条（成交需在投递审核中确认）</div>
      <div class="grid grid-cols-2 gap-2">
        <button
          class="rounded-xl bg-brand-800 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('recruiting')"
        >
          设为招聘中
        </button>
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
