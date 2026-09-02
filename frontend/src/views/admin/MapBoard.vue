<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import { useRouter } from "vue-router";
import { showToast } from "vant";
import { useAuthStore } from "@/stores/auth";
import { publicApi } from "@/api/orders";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { createOrderMarker, initMap, loadAMap } from "@/utils/amap";

type BoardOrder = {
  id: number;
  grade_subject: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  fuzzy_address: string;
  subway_remark?: string | null;
  lng: number;
  lat: number;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  created_at: string;
};

const router = useRouter();
const auth = useAuthStore();

const mapRef = ref<HTMLElement | null>(null);
const loading = ref(true);
const mapReady = ref(false);
const mapError = ref("");
const boardTenantName = ref("");
const inviteCode = ref("");
const orders = ref<BoardOrder[]>([]);
const selectedOrderId = ref<number | null>(null);

let map: any = null;
let AMap: any = null;
let markers: any[] = [];

const selectedOrder = computed(() => orders.value.find((order) => order.id === selectedOrderId.value) || null);

const summary = computed(() => ({
  total: orders.value.length,
  highFee: orders.value.filter((order) => order.calculated_info_fee >= 200).length,
  manual: orders.value.filter((order) => order.needs_manual_price).length,
}));

onMounted(async () => {
  await loadBoard();
  await nextTick();
  await initBoardMap();
});

onBeforeUnmount(() => {
  if (map && typeof map.destroy === "function") {
    map.destroy();
  }
});

watch(
  () => auth.tenant?.invite_code,
  async () => {
    if (!mapReady.value) {
      return;
    }
    await loadBoard();
    renderMarkers();
  }
);

async function loadBoard() {
  const code = auth.tenant?.invite_code;
  if (!code) {
    showToast("缺少中介邀请码");
    router.push("/admin/dashboard");
    return;
  }

  loading.value = true;
  mapError.value = "";
  try {
    const res = await publicApi.getBoard(code);
    boardTenantName.value = res.tenant_name || auth.tenant?.tenant_name || "中介后台";
    inviteCode.value = res.invite_code || code;
    orders.value = (res.orders || []).slice().sort((a: BoardOrder, b: BoardOrder) => b.created_at.localeCompare(a.created_at));
    selectedOrderId.value = orders.value[0]?.id || null;
  } catch (error: any) {
    mapError.value = error?.response?.data?.detail || "地图数据加载失败";
    showToast(mapError.value);
  } finally {
    loading.value = false;
  }
}

async function initBoardMap() {
  if (!mapRef.value) return;

  try {
    AMap = await loadAMap();
    const center: [number, number] = orders.value.length
      ? [orders.value[0].lng, orders.value[0].lat]
      : [104.065735, 30.659462];
    map = initMap(AMap, mapRef.value.id, center, orders.value.length ? 12 : 11);
    mapReady.value = true;
    renderMarkers();
  } catch (error: any) {
    mapError.value = error?.message || "地图加载失败，请检查高德密钥";
    showToast(mapError.value);
  }
}

function renderMarkers() {
  if (!map || !AMap) return;

  markers.forEach((marker) => marker.setMap(null));
  markers = [];

  if (!orders.value.length) {
    return;
  }

  orders.value.forEach((order) => {
    const marker = createOrderMarker(AMap, order.lng, order.lat, `#${order.id}`, () => {
      focusOrder(order.id);
    });
    marker.setMap(map);
    markers.push(marker);
  });

  const bounds = new AMap.Bounds(
    [Math.min(...orders.value.map((order) => order.lng)), Math.min(...orders.value.map((order) => order.lat))],
    [Math.max(...orders.value.map((order) => order.lng)), Math.max(...orders.value.map((order) => order.lat))]
  );
  map.setBounds(bounds, true, [40, 40, 40, 40]);
}

function focusOrder(orderId: number) {
  const order = orders.value.find((item) => item.id === orderId);
  if (!order || !map) return;

  selectedOrderId.value = order.id;
  map.setZoomAndCenter(Math.max(map.getZoom() || 12, 14), [order.lng, order.lat]);
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="地图看单" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="px-4 pt-3">
      <div class="grid grid-cols-3 gap-3">
        <div class="bg-white rounded-2xl p-3 shadow-sm">
          <div class="text-xs text-gray-400">总单数</div>
          <div class="text-2xl font-bold mt-1">{{ summary.total }}</div>
        </div>
        <div class="bg-white rounded-2xl p-3 shadow-sm">
          <div class="text-xs text-gray-400">高信息费</div>
          <div class="text-2xl font-bold mt-1">{{ summary.highFee }}</div>
        </div>
        <div class="bg-white rounded-2xl p-3 shadow-sm">
          <div class="text-xs text-gray-400">待定价</div>
          <div class="text-2xl font-bold mt-1">{{ summary.manual }}</div>
        </div>
      </div>
    </div>

    <div class="px-4 pt-3">
      <div class="bg-white rounded-2xl p-3 shadow-sm">
        <div class="text-sm font-semibold text-slate-800">{{ boardTenantName || "中介后台" }}</div>
        <div class="text-xs text-gray-400 mt-1">邀请码 {{ inviteCode || auth.tenant?.invite_code || "-" }}</div>
      </div>
    </div>

    <div class="px-4 pt-3">
      <div class="bg-white rounded-2xl shadow-sm overflow-hidden">
        <div
          ref="mapRef"
          id="admin-order-map"
          class="w-full"
          style="height: 46vh; min-height: 340px;"
        ></div>
        <div v-if="loading || mapError" class="px-4 py-3 border-t border-gray-100">
          <div v-if="loading" class="text-sm text-gray-500">正在拉取地图数据...</div>
          <div v-else class="text-sm text-red-500">{{ mapError }}</div>
        </div>
      </div>
    </div>

    <div class="px-4 pt-3">
      <div class="bg-white rounded-2xl shadow-sm">
        <div class="px-4 py-3 border-b border-gray-100 font-semibold">订单列表</div>
        <div class="max-h-[26vh] overflow-y-auto">
          <button
            v-for="order in orders"
            :key="order.id"
            class="w-full text-left px-4 py-3 border-b border-gray-50"
            :class="selectedOrderId === order.id ? 'bg-blue-50' : 'bg-white'"
            @click="focusOrder(order.id)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-semibold text-slate-800 truncate">{{ order.grade_subject }}</div>
                <div class="text-xs text-gray-400 mt-1 truncate">{{ order.fuzzy_address }}</div>
              </div>
              <div class="text-right shrink-0">
                <div class="text-blue-600 font-bold">¥{{ order.base_price }}</div>
                <div class="text-[11px] text-gray-400 mt-1">#{{ order.id }}</div>
              </div>
            </div>
          </button>
          <div v-if="!orders.length && !loading" class="px-4 py-8 text-center text-gray-400">
            暂无可展示订单
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectedOrder" class="px-4 pt-3">
      <div class="bg-white rounded-2xl p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs text-gray-400">当前选中</div>
            <div class="font-semibold mt-1">{{ selectedOrder.grade_subject }}</div>
          </div>
          <div class="text-right">
            <div class="text-blue-600 font-bold text-lg">¥{{ selectedOrder.base_price }}</div>
            <div class="text-xs text-gray-400 mt-1">{{ selectedOrder.price_total }}</div>
          </div>
        </div>
        <div class="text-sm text-slate-600 mt-3 leading-6">
          {{ selectedOrder.fuzzy_address }}
        </div>
        <div v-if="selectedOrder.subway_remark" class="text-xs text-gray-400 mt-2">
          {{ selectedOrder.subway_remark }}
        </div>
      </div>
    </div>

    <AdminTabbar />
  </div>
</template>
