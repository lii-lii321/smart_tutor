<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import type { OrderBrief } from "@/api/types";
import client from "@/api/client";
import { usePagedList } from "@/composables/usePagedList";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showConfirmDialog, showSuccessToast } from "vant";

const router = useRouter();
const statusFilter = ref("");
const searchKeyword = ref("");
const batchMode = ref(false);
const batchSaving = ref(false);
const checkedIds = ref<Set<number>>(new Set());
const showEdit = ref(false);
const saving = ref(false);
const editingOrder = ref<OrderBrief | null>(null);
const editForm = ref<Record<string, any>>({});

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
    link.download = `订单列表_${new Date().toISOString().slice(0, 10)}.csv`;
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

async function handleBatchStatus(targetStatus: string) {
  const ids = [...checkedIds.value];
  if (!ids.length) {
    showToast("请先选择订单");
    return;
  }

  const label = statusLabels[targetStatus] || targetStatus;
  try {
    await showConfirmDialog({
      title: `批量设为${label}？`,
      message: `将处理 ${ids.length} 条订单`,
    });
  } catch {
    return;
  }

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
  try {
    await showConfirmDialog({ title: "确认归档？", message: "归档后订单将不在橱窗展示" });
  } catch {
    return;
  }
  try {
    await ordersApi.archive(orderId);
    showToast("已归档");
    await loadOrders();
  } catch (e) {
    showToast(getApiErrorMessage(e, "归档失败"));
  }
}

async function handleRepublish(orderId: number) {
  try {
    await showConfirmDialog({
      title: "重新发布？",
      message: "订单会回到招聘中，并重新出现在教员橱窗",
    });
  } catch {
    return;
  }
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
  if (!editingOrder.value) return;
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

const statusColors: Record<string, string> = {
  recruiting: "bg-blue-50 text-blue-600 ring-blue-100",
  trial_in_progress: "bg-violet-50 text-violet-600 ring-violet-100",
  completed: "bg-emerald-50 text-emerald-600 ring-emerald-100",
  archived: "bg-slate-100 text-slate-500 ring-slate-200",
};

const statusLabels: Record<string, string> = {
  recruiting: "招聘中",
  trial_in_progress: "试课中",
  completed: "已完成",
  archived: "已归档",
};

function fmtCreated(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
}

onMounted(() => {
  const initialStatus = String(route.query.status || "");
  if (initialStatus && statusLabels[initialStatus]) {
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
  <div class="min-h-screen bg-gray-50 pb-28 mx-auto max-w-2xl">
    <van-nav-bar
      title="订单管理"
      left-arrow
      :right-text="batchMode ? '取消' : '批量'"
      @click-left="router.push('/admin/dashboard')"
      @click-right="toggleBatchMode"
    />

    <!-- 工具栏：搜索 + 查找 + 导出 -->
    <div class="px-4 pt-3">
      <div class="flex items-center gap-1.5 rounded-xl border border-[#ece8e3] bg-white p-1 shadow-sm">
        <van-search
          v-model="searchKeyword"
          shape="round"
          placeholder="输入订单编号查找"
          background="transparent"
          class="min-w-0 flex-1 !p-0"
          @search="handleSearch"
          @clear="clearSearch"
        />
        <button
          class="shrink-0 rounded-lg bg-primary-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
          :disabled="!searchKeyword.trim()"
          @click="handleSearch"
        >
          查找
        </button>
        <button
          class="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
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
            ? 'border-primary-600 bg-primary-600 text-white'
            : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'"
          @click="statusFilter = statusFilter === key ? '' : key; checkedIds = new Set(); loadOrders()"
        >
          {{ label }}
        </button>
      </div>
      <span class="shrink-0 text-xs text-slate-400">共 {{ totalCount }} 条</span>
    </div>

    <div v-if="batchMode" class="px-4 pt-2">
      <button
        class="w-full rounded-lg border border-dashed border-slate-300 bg-white py-2 text-xs font-medium text-primary-600"
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
          class="rounded-xl border border-[#ece8e3] bg-white px-3.5 py-4"
        >
          <van-skeleton title :row="2" title-width="45%" row-width="90%" />
        </div>
      </div>

      <div v-else-if="orders.length === 0" class="mx-4 mt-4 flex min-h-[calc(100vh-260px)] flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white text-slate-400">
        <div class="flex h-12 w-12 items-center justify-center rounded-full bg-slate-50">
          <van-icon name="orders-o" size="22" />
        </div>
        <p class="mt-3 text-sm text-slate-500">暂无订单</p>
        <p class="mt-1 text-xs text-slate-400">去工作台「批量导入」，粘贴微信文本即可快速录单</p>
      </div>

      <div v-else class="space-y-2.5 px-4">
        <div
          v-for="order in orders" :key="order.id"
          class="order-card rounded-xl border bg-white px-3.5 py-3 transition-colors"
          :class="checkedIds.has(order.id)
            ? 'border-blue-400 bg-blue-50/40 ring-1 ring-blue-200'
            : 'border-[#ece8e3] hover:border-slate-300'"
        >
          <div class="flex items-baseline justify-between gap-3">
            <div class="flex min-w-0 items-baseline gap-2">
              <van-checkbox
                v-if="batchMode"
                :model-value="checkedIds.has(order.id)"
                class="shrink-0 self-center"
                @click.stop="toggleCheck(order.id)"
              />
              <span class="truncate text-sm font-semibold text-slate-900">{{ order.grade_subject }}</span>
              <span class="shrink-0 text-xs text-slate-500">{{ order.price_total }}</span>
            </div>
            <div class="text-primary-600 shrink-0 font-bold text-base leading-5 price-highlight">¥{{ order.calculated_info_fee }}</div>
          </div>

          <div class="mt-1.5 flex min-w-0 items-center gap-2 text-xs text-slate-400">
            <span
              class="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1"
              :class="statusColors[order.status]"
            >
              <span class="h-1 w-1 rounded-full bg-current"></span>
              {{ statusLabels[order.status] || order.status }}
            </span>
            <span class="shrink-0 text-[11px] tracking-wide text-slate-300">#{{ order.raw_id }}</span>
            <span class="flex min-w-0 items-center gap-1">
              <van-icon name="location-o" class="shrink-0" />
              <span class="truncate">{{ order.fuzzy_address }}</span>
            </span>
            <span v-if="order.weekly_frequency" class="hidden shrink-0 items-center gap-1 sm:flex">
              <van-icon name="clock-o" />每周{{ order.weekly_frequency }}次
            </span>
            <span class="ml-auto shrink-0 text-[11px] text-slate-300">{{ fmtCreated(order.created_at) }}</span>
          </div>

          <div class="mt-2.5 flex items-center gap-2 border-t border-slate-100 pt-2.5">
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 rounded-lg border border-slate-200 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
              :disabled="batchMode"
              @click="openEdit(order.id)"
            >
              编辑
            </button>
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 rounded-lg border border-red-100 bg-red-50/60 py-1 text-xs font-medium text-red-500 hover:bg-red-100/60 disabled:opacity-40"
              :disabled="batchMode"
              @click="handleArchive(order.id)"
            >
              归档
            </button>
            <button
              v-if="order.status === 'archived'"
              class="flex-1 rounded-lg border border-blue-100 bg-blue-50/60 py-1 text-xs font-medium text-blue-600 hover:bg-blue-100/60 disabled:opacity-40"
              :disabled="batchMode"
              @click="handleRepublish(order.id)"
            >
              重新发布
            </button>
          </div>
        </div>
      </div>

      <div v-if="orders.length > 0" class="px-4 pb-4">
        <button
          v-if="hasMore"
          class="w-full rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-primary-700 hover:bg-slate-50 disabled:opacity-50"
          :disabled="loadingMore"
          @click="loadMore"
        >
          <span v-if="loadingMore">加载中...</span>
          <span v-else>加载更多（{{ orders.length }}/{{ totalCount }}）</span>
        </button>
        <div v-else class="py-2 text-center text-xs text-slate-300">
          已显示全部 {{ totalCount }} 条订单
        </div>
      </div>
    </van-pull-refresh>

    <van-popup v-model:show="showEdit" position="bottom" round>
      <div class="p-4 max-h-[82vh] overflow-y-auto">
        <div class="mb-3 flex items-center justify-between">
          <div class="min-w-0">
            <div class="text-base font-semibold text-slate-900">编辑订单</div>
            <div class="mt-0.5 truncate text-xs text-slate-400">#{{ editingOrder?.raw_id }} · {{ editingOrder?.grade_subject }}</div>
          </div>
          <button
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500"
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
          <button class="rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-600" @click="showEdit = false">取消</button>
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

    <div v-if="batchMode" class="fixed bottom-[50px] left-0 right-0 z-20 border-t border-slate-200 bg-white/95 p-3 shadow-[0_-4px_16px_rgba(23,24,28,0.06)] backdrop-blur">
      <div class="mb-2 text-center text-xs text-slate-400">已选择 {{ selectedCount }} 条（成交需在投递审核中确认）</div>
      <div class="grid grid-cols-2 gap-2">
        <button
          class="rounded-xl bg-primary-600 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('recruiting')"
        >
          设为招聘中
        </button>
        <button
          class="rounded-xl border border-red-200 bg-red-50/70 py-2.5 text-sm font-semibold text-red-500 disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('archived')"
        >
          设为已归档
        </button>
      </div>
    </div>
    <AdminTabbar />
  </div>
</template>