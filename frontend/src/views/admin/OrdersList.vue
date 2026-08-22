<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showConfirmDialog, showSuccessToast } from "vant";

const router = useRouter();
const orders = ref<any[]>([]);
const loading = ref(true);
const page = ref(1);
const statusFilter = ref("");
const searchKeyword = ref("");
const batchMode = ref(false);
const batchSaving = ref(false);
const checkedIds = ref<Set<number>>(new Set());
const showEdit = ref(false);
const saving = ref(false);
const editingOrder = ref<any | null>(null);
const editForm = ref<Record<string, any>>({});

onMounted(() => loadOrders());

async function loadOrders() {
  loading.value = true;
  try {
    const res: any = await ordersApi.listOrders(
      page.value,
      20,
      statusFilter.value || undefined,
      searchKeyword.value.trim() || undefined
    );
    orders.value = res.items || [];
    checkedIds.value = new Set([...checkedIds.value].filter((id) => orders.value.some((order) => order.id === id)));
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadOrders();
}

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
    loadOrders();
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "批量操作失败");
  } finally {
    batchSaving.value = false;
  }
}

async function handleArchive(orderId: number) {
  try {
    await showConfirmDialog({ title: "确认归档？", message: "归档后订单将不在橱窗展示" });
    await ordersApi.archive(orderId);
    showToast("已归档");
    loadOrders();
  } catch { /* cancelled */ }
}

async function handleRepublish(orderId: number) {
  try {
    await showConfirmDialog({
      title: "重新发布？",
      message: "订单会回到招聘中，并重新出现在教员橱窗",
    });
    await ordersApi.republish(orderId);
    showSuccessToast("已重新发布");
    loadOrders();
  } catch { /* cancelled */ }
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
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载订单失败");
  }
}

async function saveEdit() {
  if (!editingOrder.value) return;
  saving.value = true;
  try {
    await ordersApi.updateOrder(editingOrder.value.id, editForm.value);
    showSuccessToast("已保存");
    showEdit.value = false;
    loadOrders();
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

const statusColors: Record<string, string> = {
  recruiting: "bg-blue-100 text-blue-700",
  trial_in_progress: "bg-green-100 text-green-700",
  completed: "bg-gray-100 text-gray-700",
  archived: "bg-red-50 text-red-400",
};

const statusLabels: Record<string, string> = {
  recruiting: "招聘中",
  trial_in_progress: "试课中",
  completed: "已完成",
  archived: "已归档",
};

const selectedCount = computed(() => checkedIds.value.size);
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-28">
    <van-nav-bar
      title="订单管理"
      left-arrow
      :right-text="batchMode ? '取消' : '批量'"
      @click-left="router.push('/admin/dashboard')"
      @click-right="toggleBatchMode"
    />

    <!-- 筛选栏 -->
    <div class="px-4 pt-3">
      <van-search
        v-model="searchKeyword"
        shape="round"
        placeholder="输入订单编号查找"
        background="transparent"
        class="mb-2 !p-0"
        @search="handleSearch"
        @clear="clearSearch"
      />
      <button
        v-if="searchKeyword.trim()"
        class="w-full bg-white text-primary-600 rounded-xl py-2 text-sm font-medium mb-3"
        @click="handleSearch"
      >
        查找订单
      </button>
    </div>

    <div class="px-4 pb-3 flex gap-2 overflow-x-auto">
      <button
        v-for="(label, key) in statusLabels" :key="key"
        class="px-3 py-1.5 rounded-full text-xs font-medium shrink-0"
        :class="statusFilter === key ? 'bg-primary-600 text-white' : 'bg-white text-gray-600'"
        @click="statusFilter = statusFilter === key ? '' : key; checkedIds = new Set(); loadOrders()"
      >
        {{ label }}
      </button>
    </div>

    <div v-if="batchMode" class="px-4 pb-3">
      <button
        class="w-full rounded-xl bg-white py-2 text-sm font-medium text-primary-600"
        @click="toggleAllVisible"
      >
        {{ selectedCount === orders.length && orders.length ? "取消本页全选" : "本页全选" }}
      </button>
    </div>

    <van-pull-refresh v-model="loading" @refresh="loadOrders">
      <div v-if="orders.length === 0" class="text-center py-20 text-gray-400">
        <van-icon name="orders-o" size="48" />
        <p class="mt-4">暂无订单</p>
      </div>

      <div v-else class="px-4 space-y-3">
        <div
          v-for="order in orders" :key="order.id"
          class="bg-white rounded-2xl p-4 shadow-sm"
          :class="{ 'ring-2 ring-primary-500': checkedIds.has(order.id) }"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2 min-w-0">
              <van-checkbox
                v-if="batchMode"
                :model-value="checkedIds.has(order.id)"
                class="shrink-0"
                @click.stop="toggleCheck(order.id)"
              />
              <div class="min-w-0">
              <span class="text-xs text-gray-400">#{{ order.raw_id }}</span>
              <span class="ml-2 px-2 py-0.5 rounded-full text-xs" :class="statusColors[order.status]">
                {{ statusLabels[order.status] || order.status }}
              </span>
              </div>
            </div>
            <div class="text-primary-600 font-bold text-lg price-highlight">¥{{ order.calculated_info_fee }}</div>
          </div>

          <div class="font-semibold mb-1">{{ order.grade_subject }} · {{ order.price_total }}</div>
          <div class="text-gray-400 text-xs">{{ order.fuzzy_address }}</div>

          <div class="flex gap-2 mt-3 pt-3 border-t border-gray-50">
            <button
              class="flex-1 bg-gray-50 text-gray-600 rounded-lg py-1.5 text-xs"
              :disabled="batchMode"
              @click="openEdit(order.id)"
            >
              编辑
            </button>
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 bg-red-50 text-red-500 rounded-lg py-1.5 text-xs"
              :disabled="batchMode"
              @click="handleArchive(order.id)"
            >
              归档
            </button>
            <button
              v-if="order.status === 'archived'"
              class="flex-1 bg-blue-50 text-blue-600 rounded-lg py-1.5 text-xs"
              :disabled="batchMode"
              @click="handleRepublish(order.id)"
            >
              重新发布
            </button>
          </div>
        </div>
      </div>
    </van-pull-refresh>

    <van-popup v-model:show="showEdit" position="bottom" round>
      <div class="p-4 max-h-[82vh] overflow-y-auto">
        <div class="font-semibold text-lg mb-3">编辑订单</div>
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
        <div class="grid grid-cols-2 gap-3 mt-4">
          <button class="bg-gray-100 rounded-xl py-2 text-sm" @click="showEdit = false">取消</button>
          <button
            class="bg-primary-600 text-white rounded-xl py-2 text-sm font-semibold disabled:opacity-60"
            :disabled="saving"
            @click="saveEdit"
          >
            保存
          </button>
        </div>
      </div>
    </van-popup>

    <div v-if="batchMode" class="fixed bottom-[50px] left-0 right-0 z-20 border-t bg-white p-3 shadow-lg">
      <div class="mb-2 text-center text-xs text-gray-400">已选择 {{ selectedCount }} 条</div>
      <div class="grid grid-cols-3 gap-2">
        <button
          class="rounded-xl bg-blue-50 py-2.5 text-sm font-semibold text-blue-600 disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('recruiting')"
        >
          招聘中
        </button>
        <button
          class="rounded-xl bg-gray-100 py-2.5 text-sm font-semibold text-gray-700 disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('completed')"
        >
          已完成
        </button>
        <button
          class="rounded-xl bg-red-50 py-2.5 text-sm font-semibold text-red-500 disabled:opacity-50"
          :disabled="batchSaving || !selectedCount"
          @click="handleBatchStatus('archived')"
        >
          已归档
        </button>
      </div>
    </div>
    <AdminTabbar />
  </div>
</template>
