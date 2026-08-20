<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ordersApi } from "@/api/orders";
import { applicationsApi } from "@/api/applications";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showSuccessToast, showConfirmDialog, showDialog } from "vant";

const router = useRouter();
const orders = ref<any[]>([]);
const applications = ref<any[]>([]);
const selectedOrderId = ref<number | null>(null);
const loading = ref(true);

onMounted(async () => {
  await loadOrders();
});

async function loadOrders() {
  loading.value = true;
  try {
    const res: any = await ordersApi.listOrders(1, 50);
    orders.value = (res.items || []).filter((o: any) =>
      ["recruiting", "pending_deposit", "pending_balance", "trial_in_progress"].includes(o.status)
    );
  } finally {
    loading.value = false;
  }
}

async function selectOrder(orderId: number) {
  selectedOrderId.value = orderId;
  try {
    applications.value = (await applicationsApi.listByOrder(orderId)) as any[];
  } catch {
    showToast("加载投递列表失败");
  }
}

async function handleShortlist(appId: number) {
  try {
    await applicationsApi.shortlist(appId);
    showSuccessToast("已加入候选队列");
    if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "操作失败");
  }
}

async function handleStartTrial(appId: number) {
  try {
    await applicationsApi.startTrial(appId);
    showSuccessToast("已开始试课");
    if (selectedOrderId.value) await selectOrder(selectedOrderId.value);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "操作失败");
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
  } catch (e: any) {
    if (e?.response) showToast(e.response.data?.detail || "操作失败");
  }
}

async function handleConfirmBalance(appId: number) {
  try {
    await showConfirmDialog({ title: "确认尾款？", message: "确认后会生成一条尾款收入流水" });
    await applicationsApi.confirmBalance(appId);
    showSuccessToast("尾款已确认");
    await refreshSelected();
  } catch (e: any) {
    if (e?.response) showToast(e.response.data?.detail || "操作失败");
  }
}

async function handleComplete(appId: number) {
  try {
    await showConfirmDialog({ title: "确认完成？", message: "订单将标记为已完成" });
    await applicationsApi.complete(appId);
    showSuccessToast("订单已完成");
    await refreshSelected();
    await loadOrders();
  } catch (e: any) {
    if (e?.response) showToast(e.response.data?.detail || "操作失败");
  }
}

async function handleTrialFailed(appId: number) {
  try {
    await showDialog({
      title: "试课失败",
      message: "将按退费精算处理（默认不退款），订单会重新开放给其他教员。",
      showCancelButton: true,
    });
    await applicationsApi.trialFailed(appId, 0);
    showSuccessToast("订单已重新开放");
    await refreshSelected();
    await loadOrders();
  } catch (e: any) {
    if (e?.response) showToast(e.response.data?.detail || "操作失败");
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
    await loadOrders();
  } catch (e: any) {
    if (e?.response) showToast(e.response.data?.detail || "操作失败");
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="投递审核" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="flex h-[calc(100vh-96px)]">
      <!-- 左侧订单列表 -->
      <div class="w-32 bg-white border-r overflow-y-auto">
        <div
          v-for="order in orders" :key="order.id"
          class="p-3 text-xs border-b cursor-pointer"
          :class="selectedOrderId === order.id ? 'bg-primary-50 text-primary-600 font-semibold' : 'text-gray-600'"
          @click="selectOrder(order.id)"
        >
          <div class="truncate">{{ order.grade_subject }}</div>
          <div class="text-gray-400 text-[10px] mt-0.5">{{ order.raw_id }}</div>
        </div>
        <div v-if="orders.length === 0" class="p-4 text-gray-400 text-xs text-center">
          暂无活跃订单
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
            class="bg-white rounded-xl p-3 shadow-sm"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="font-semibold text-sm truncate">
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
                class="px-2 py-0.5 rounded-full text-xs"
                :class="{
                  'bg-yellow-100 text-yellow-700': app.status === 'pending',
                  'bg-blue-100 text-blue-700': app.status === 'shortlisted',
                  'bg-cyan-100 text-cyan-700': app.status === 'deposit_paid',
                  'bg-emerald-100 text-emerald-700': app.status === 'trial_in_progress',
                  'bg-green-100 text-green-700': app.status === 'balance_paid',
                  'bg-gray-100 text-gray-500': ['rejected', 'refunded'].includes(app.status),
                }"
              >
                {{ ({ pending: "待审核", shortlisted: "候选排队", trial_in_progress: "正在试课", deposit_paid: "定金已付", balance_paid: "尾款已付", rejected: "已拒绝", refunded: "已退款" } as any)[app.status] || app.status }}
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
            </div>

            <div class="text-xs text-gray-400 mb-2">
              投递于 {{ new Date(app.applied_at).toLocaleString("zh-CN") }}
              <div v-if="app.proposed_price != null" class="mt-1 text-orange-600 font-medium">
                教员报价：¥{{ app.proposed_price }}/次
              </div>
            </div>

            <button
              v-if="app.status === 'pending'"
              class="w-full header-gradient text-white rounded-lg py-2 text-xs font-semibold"
              @click="handleShortlist(app.id)"
            >
              加入候选队列
            </button>

            <button
              v-if="app.status === 'shortlisted'"
              class="w-full bg-[#1a365d] text-white rounded-lg py-2 text-xs font-semibold mb-2"
              @click="handleConfirmDeposit(app.id)"
            >
              确认定金
            </button>

            <button
              v-if="app.status === 'deposit_paid'"
              class="w-full bg-emerald-600 text-white rounded-lg py-2 text-xs font-semibold mb-2"
              @click="handleStartTrial(app.id)"
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
                  @click="handleTrialFailed(app.id)"
                >
                  试课失败
                </button>
                <button
                  class="bg-green-600 text-white rounded-lg py-2 text-xs font-semibold"
                  @click="handleConfirmBalance(app.id)"
                >
                  确认尾款
                </button>
              </div>
            </div>

            <button
              v-if="['deposit_paid', 'trial_in_progress', 'balance_paid'].includes(app.status)"
              class="w-full bg-orange-50 text-orange-600 rounded-lg py-2 text-xs font-semibold mt-2"
              @click="handleForfeit(app.id)"
            >
              没收定金（教员违约）
            </button>

            <div v-if="app.status === 'balance_paid'" class="space-y-2">
              <div class="text-xs text-green-600 bg-green-50 rounded-lg p-2">
                教员已付全款，可解锁联系方式
              </div>
              <button
                class="w-full bg-gray-900 text-white rounded-lg py-2 text-xs font-semibold"
                @click="handleComplete(app.id)"
              >
                确认完成
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <AdminTabbar />
  </div>
</template>
