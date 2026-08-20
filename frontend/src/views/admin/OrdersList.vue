<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import { showToast, showConfirmDialog, showSuccessToast } from "vant";

const router = useRouter();
const orders = ref<any[]>([]);
const loading = ref(true);
const page = ref(1);
const statusFilter = ref("");
const showEdit = ref(false);
const saving = ref(false);
const editingOrder = ref<any | null>(null);
const editForm = ref<Record<string, any>>({});

onMounted(() => loadOrders());

async function loadOrders() {
  loading.value = true;
  try {
    const res: any = await ordersApi.listOrders(page.value, 20, statusFilter.value || undefined);
    orders.value = res.items || [];
  } finally {
    loading.value = false;
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

async function handleExpireStale() {
  const res = await ordersApi.expireStale();
  showSuccessToast(`已整理 ${res.archived || 0} 个过期订单`);
  loadOrders();
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
  pending_deposit: "bg-yellow-100 text-yellow-700",
  pending_approval: "bg-orange-100 text-orange-700",
  pending_balance: "bg-sky-100 text-sky-700",
  trial_in_progress: "bg-green-100 text-green-700",
  completed: "bg-gray-100 text-gray-700",
  archived: "bg-red-50 text-red-400",
};

const statusLabels: Record<string, string> = {
  recruiting: "招聘中",
  pending_deposit: "待付定金",
  pending_approval: "待确认",
  pending_balance: "待补尾款",
  trial_in_progress: "试课中",
  completed: "已完成",
  archived: "已归档",
};
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="订单管理" left-arrow @click-left="router.push('/admin/dashboard')" />

    <!-- 筛选栏 -->
    <div class="px-4 pt-3">
      <button
        class="w-full bg-white text-primary-600 rounded-xl py-2 text-sm font-medium mb-3"
        @click="handleExpireStale"
      >
        整理过期订单
      </button>
    </div>

    <div class="px-4 pb-3 flex gap-2 overflow-x-auto">
      <button
        v-for="(label, key) in statusLabels" :key="key"
        class="px-3 py-1.5 rounded-full text-xs font-medium shrink-0"
        :class="statusFilter === key ? 'bg-primary-600 text-white' : 'bg-white text-gray-600'"
        @click="statusFilter = statusFilter === key ? '' : key; loadOrders()"
      >
        {{ label }}
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
        >
          <div class="flex items-center justify-between mb-2">
            <div>
              <span class="text-xs text-gray-400">#{{ order.raw_id }}</span>
              <span class="ml-2 px-2 py-0.5 rounded-full text-xs" :class="statusColors[order.status]">
                {{ statusLabels[order.status] || order.status }}
              </span>
            </div>
            <div class="text-primary-600 font-bold text-lg price-highlight">¥{{ order.calculated_info_fee }}</div>
          </div>

          <div class="font-semibold mb-1">{{ order.grade_subject }} · {{ order.price_total }}</div>
          <div class="text-gray-400 text-xs">{{ order.fuzzy_address }}</div>

          <div class="flex gap-2 mt-3 pt-3 border-t border-gray-50">
            <button
              class="flex-1 bg-gray-50 text-gray-600 rounded-lg py-1.5 text-xs"
              @click="openEdit(order.id)"
            >
              编辑
            </button>
            <button
              v-if="order.status === 'recruiting'"
              class="flex-1 bg-red-50 text-red-500 rounded-lg py-1.5 text-xs"
              @click="handleArchive(order.id)"
            >
              归档
            </button>
            <button
              v-if="['archived', 'pending_deposit', 'pending_approval', 'pending_balance'].includes(order.status)"
              class="flex-1 bg-blue-50 text-blue-600 rounded-lg py-1.5 text-xs"
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
  </div>
</template>
