<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useOrderStore } from "@/stores/order";
import { useAuthStore } from "@/stores/auth";
import { loadAMap, initMap, createOrderMarker } from "@/utils/amap";
import { publicApi } from "@/api/orders";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { showToast, showLoadingToast, closeToast } from "vant";

const route = useRoute();
const router = useRouter();
const orderStore = useOrderStore();
const auth = useAuthStore();

const inviteCode = ref((route.params.inviteCode as string) || "tx886");
const mapRef = ref<HTMLDivElement>();
const agentPickerVisible = ref(false);
const agentFormVisible = ref(false);
const newInviteCode = ref("");
const savedAgents = ref<string[]>([]);
const selectedSubjects = ref<string[]>([]);
const recommendations = ref<any[]>([]);
const recLoading = ref(false);
const recommendationsExpanded = ref(true);
let map: any = null;
let markers: any[] = [];

const AGENT_STORAGE_KEY = "teacher_agent_invite_codes";
const subjectOptions = ["数学", "语文", "英语", "物理", "化学", "生物", "政治", "地理", "历史", "其他"];
const subjectAliases: Record<string, string[]> = {
  数学: ["数学", "奥数", "高数"],
  语文: ["语文", "阅读", "作文"],
  英语: ["英语", "英文"],
  物理: ["物理"],
  化学: ["化学"],
  生物: ["生物"],
  政治: ["政治", "道法", "思想品德"],
  地理: ["地理"],
  历史: ["历史"],
};

const filteredOrders = computed(() => {
  if (selectedSubjects.value.length === 0) {
    return orderStore.boardOrders;
  }
  return orderStore.boardOrders.filter((order) => {
    const subject = detectSubject(order);
    return selectedSubjects.value.includes(subject);
  });
});

function readSavedAgents() {
  try {
    const parsed = JSON.parse(localStorage.getItem(AGENT_STORAGE_KEY) || "[]");
    savedAgents.value = Array.isArray(parsed) ? parsed.filter(Boolean) : [];
  } catch {
    savedAgents.value = [];
  }
  if (!savedAgents.value.includes(inviteCode.value)) {
    savedAgents.value.unshift(inviteCode.value);
    persistSavedAgents();
  }
}

function persistSavedAgents() {
  localStorage.setItem(AGENT_STORAGE_KEY, JSON.stringify([...new Set(savedAgents.value)]));
}

onMounted(async () => {
  readSavedAgents();
  showLoadingToast({ message: "加载中...", duration: 0 });

  try {
    // 加载高德地图
    const AMap = await loadAMap();
    map = initMap(AMap, "map-container");
    // 地图容器高度变化后强制重算尺寸
    setTimeout(() => {
      try {
        map?.resize?.();
      } catch {
        /* ignore */
      }
    }, 100);

    // 加载订单数据 + 推荐
    await loadBoardByInvite(inviteCode.value, false);

    closeToast();
  } catch (e) {
    closeToast();
    showToast("加载失败，请下拉刷新");
  }
});

async function loadBoardByInvite(code: string, updateRoute = true) {
  const normalized = code.trim();
  if (!normalized) {
    showToast("请输入中介邀请码");
    return;
  }

  const AMap = await loadAMap();
  await orderStore.loadBoard(normalized);
  inviteCode.value = normalized;
  if (!savedAgents.value.includes(normalized)) {
    savedAgents.value.unshift(normalized);
    persistSavedAgents();
  }
  renderMarkers(AMap, filteredOrders.value);
  await loadRecommendations();
  if (updateRoute) {
    router.replace(`/teacher/board/${normalized}`);
  }
}

// 登录状态变化时同步推荐
watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      loadRecommendations();
    } else {
      recommendations.value = [];
    }
  }
);

async function loadRecommendations() {
  if (!auth.isLoggedIn || auth.role !== "teacher") {
    recommendations.value = [];
    return;
  }
  recLoading.value = true;
  try {
    const res = await publicApi.getRecommendations(inviteCode.value, 12);
    recommendations.value = res.items || [];
  } catch {
    recommendations.value = [];
  } finally {
    recLoading.value = false;
  }
}

function goOrder(order: any) {
  if (!auth.isLoggedIn) {
    goLogin();
    return;
  }
  router.push(`/teacher/orders/${order.id}`);
}

watch(selectedSubjects, async () => {
  if (!map) return;
  const AMap = await loadAMap();
  renderMarkers(AMap, filteredOrders.value);
});

function normalizeText(value: unknown) {
  return String(value || "").replace(/\s+/g, "").toLowerCase();
}

function detectSubject(order: any) {
  const text = normalizeText(`${order.grade_subject || ""}${order.requirements || ""}${order.raw_text || ""}`);
  for (const subject of subjectOptions) {
    if (subject === "其他") continue;
    const aliases = subjectAliases[subject] || [subject];
    if (aliases.some((alias) => text.includes(alias.toLowerCase()))) {
      return subject;
    }
  }
  return "其他";
}

function toggleSubject(subject: string) {
  if (selectedSubjects.value.includes(subject)) {
    selectedSubjects.value = selectedSubjects.value.filter((item) => item !== subject);
    return;
  }
  selectedSubjects.value = [...selectedSubjects.value, subject];
}

function clearSubjects() {
  selectedSubjects.value = [];
}

function renderMarkers(AMap: any, orders: any[]) {
  // 清除旧标记
  markers.forEach((m) => map.remove(m));
  markers = [];

  if (orders.length === 0) {
    showToast(selectedSubjects.value.length ? "当前筛选下暂无订单" : "该中介暂无活跃订单");
    return;
  }

  orders.forEach((order) => {
    const unit = order.price_total.includes("小时") || order.price_total.includes("/h") ? "小时" : "次";
    const label = order.needs_manual_price ? "自带价" : `¥${order.base_price}/${unit}`;
    const marker = createOrderMarker(
      AMap,
      order.lng,
      order.lat,
      label,
      () => onMarkerClick(order)
    );
    map.add(marker);
    markers.push(marker);
  });

  // 自动适配视野
  if (orders.length > 0) {
    map.setFitView(markers);
  }
}

// 点击 Marker → 弹 ActionSheet
const sheetVisible = ref(false);
const sheetOrder = ref<any>(null);

function onMarkerClick(order: any) {
  sheetOrder.value = order;
  sheetVisible.value = true;
}

async function handleApply(order: any) {
  if (!auth.isLoggedIn) {
    goLogin();
    return;
  }
  router.push(`/teacher/orders/${order.id}`);
}

function goLogin() {
  router.push({ path: "/teacher/login", query: { inviteCode: inviteCode.value } });
}

async function addAgent() {
  const code = newInviteCode.value.trim();
  if (!code) {
    showToast("请输入中介邀请码");
    return;
  }
  try {
    await loadBoardByInvite(code);
    newInviteCode.value = "";
    agentFormVisible.value = false;
    showToast("已添加并切换");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "邀请码无效");
  }
}

async function switchAgent(code: string) {
  agentPickerVisible.value = false;
  try {
    await loadBoardByInvite(code);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "切换失败");
  }
}

function removeAgent(code: string) {
  if (savedAgents.value.length <= 1) {
    showToast("至少保留一个中介");
    return;
  }
  savedAgents.value = savedAgents.value.filter((item) => item !== code);
  persistSavedAgents();
  if (inviteCode.value === code) {
    switchAgent(savedAgents.value[0]);
  }
}
</script>

<template>
  <div class="board-page min-h-screen bg-slate-50 pb-16">
    <!-- 地图区（上半屏） -->
    <div class="relative h-[calc(100vh-56px)] min-h-[560px]">
      <!-- 顶部搜索栏 -->
      <div class="board-toolbar absolute top-0 left-0 right-0 z-10 px-2 py-2 header-gradient">
        <div class="flex items-center gap-3">
          <button
            class="agent-button min-w-0 flex-1 bg-white/20 backdrop-blur rounded-xl px-3 py-2 text-left sm:flex-none sm:w-72"
            @click="agentPickerVisible = true"
          >
            <div class="text-white/70 text-[10px] leading-4">当前中介</div>
            <div class="truncate text-white font-semibold text-sm leading-5">
              {{ orderStore.boardTenantName || inviteCode }}
            </div>
          </button>
          <button
            class="toolbar-icon bg-white/20 backdrop-blur rounded-xl p-2 text-white shrink-0"
            @click="agentPickerVisible = true"
          >
            <van-icon name="exchange" size="20" />
          </button>
          <button
            class="toolbar-icon bg-white/20 backdrop-blur rounded-xl p-2 text-white shrink-0"
            @click="agentFormVisible = true"
          >
            <van-icon name="plus" size="20" />
          </button>
          <button
            v-if="!auth.isLoggedIn"
            class="toolbar-login bg-white text-primary-600 rounded-xl px-3 py-2 text-xs font-semibold shrink-0"
            @click="goLogin"
          >
            登录
          </button>
          <template v-else>
            <button
              class="toolbar-icon bg-white/20 backdrop-blur rounded-xl p-2 text-white shrink-0"
              @click="router.push('/teacher/applications')"
            >
              <van-icon name="orders-o" size="20" />
            </button>
            <button
              class="toolbar-icon bg-white/20 backdrop-blur rounded-xl p-2 text-white shrink-0"
              @click="router.push('/teacher/profile')"
            >
              <van-icon name="user-o" size="20" />
            </button>
          </template>
        </div>
      </div>

      <!-- 地图 -->
      <div id="map-container" ref="mapRef" class="w-full h-full" />

      <!-- 科目筛选 -->
      <div class="absolute left-0 right-0 top-[72px] z-10 px-2">
        <div class="flex gap-2 overflow-x-auto rounded-xl bg-white/95 p-2 shadow-sm">
          <button
            class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium"
            :class="selectedSubjects.length === 0 ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
            @click="clearSubjects"
          >
            全部
          </button>
          <button
            v-for="subject in subjectOptions"
            :key="subject"
            class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium"
            :class="selectedSubjects.includes(subject) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
            @click="toggleSubject(subject)"
          >
            {{ subject }}
          </button>
        </div>
      </div>

      <!-- 地图底部快捷操作 -->
      <div class="absolute bottom-3 left-4 right-4 z-10 flex items-center justify-between gap-3">
        <div class="rounded-full bg-white/95 px-4 py-2 text-sm font-semibold text-primary-600 shadow-lg backdrop-blur">
          {{ selectedSubjects.length ? "符合筛选" : "活跃订单" }} {{ filteredOrders.length }} 单
        </div>
        <button
          class="rounded-full bg-[#1a365d] p-3 text-white shadow-lg"
          aria-label="刷新地图"
          @click="loadBoardByInvite(inviteCode, false)"
        >
          <van-icon name="replay" size="20" />
        </button>
      </div>
    </div>

    <!-- 为你推荐（地图下方） -->
    <section class="recommendation-drawer fixed bottom-[56px] left-0 right-0 z-20 px-2">
      <div class="recommendation-handle mb-1 flex items-center justify-between rounded-2xl bg-white/95 px-4 py-2 shadow-lg backdrop-blur" @click="recommendationsExpanded = !recommendationsExpanded">
        <button class="flex min-w-0 items-center gap-2 text-left" aria-label="展开或收起推荐订单">
          <van-icon :name="recommendationsExpanded ? 'arrow-down' : 'arrow-up'" size="16" color="#1e3558" />
          <h2 class="text-base font-bold text-slate-900">为你推荐</h2>
          <span v-if="recommendations.length" class="text-xs text-slate-400">{{ recommendations.length }} 条</span>
        </button>
        <button class="flex items-center gap-1 text-xs text-primary-600" :disabled="recLoading" @click.stop="loadRecommendations">
          <van-icon name="replay" size="14" />
          {{ recLoading ? "加载中" : "换一批" }}
        </button>
      </div>

      <div v-if="recommendationsExpanded && !auth.isLoggedIn" class="rounded-2xl bg-white p-5 text-center shadow-sm">
        <p class="text-sm text-slate-400">登录后按你的画像（科目/年级/距离/院校）智能推荐订单</p>
        <button
          class="mt-3 rounded-xl bg-blue-600 px-6 py-2 text-sm font-semibold text-white"
          @click="goLogin"
        >
          登录查看推荐
        </button>
      </div>

      <div v-else-if="recommendationsExpanded && recLoading" class="rounded-2xl bg-white p-6 text-center shadow-sm">
        <van-loading color="#2563eb" size="24" />
      </div>

      <div v-else-if="recommendationsExpanded && recommendations.length === 0" class="rounded-2xl bg-white p-5 text-center text-sm text-slate-400 shadow-sm">
        暂无推荐订单，去地图上看看
      </div>

      <div v-else-if="recommendationsExpanded" class="recommendation-list max-h-[54vh] space-y-3 overflow-y-auto pb-2">
        <div
          v-for="item in recommendations"
          :key="item.id"
          class="rounded-2xl bg-white p-4 shadow-sm"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="min-w-0">
              <span class="font-semibold text-slate-900">{{ item.grade_subject }}</span>
              <span class="ml-2 text-xs font-medium text-primary-600">{{ item.price_total }}</span>
            </div>
            <span class="shrink-0 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-600">
              匹配 {{ item.total_score }}%
            </span>
          </div>

          <div class="mt-2 space-y-1 text-xs text-slate-500">
            <div>
              {{ item.fuzzy_address }}
              <template v-if="item.distance_km != null"> · 距你约 {{ item.distance_km }}km</template>
            </div>
            <div v-if="item.reasons?.length" class="text-slate-400">
              {{ item.reasons.slice(0, 2).join(" · ") }}
            </div>
            <div v-if="item.score_breakdown" class="text-[11px] text-slate-400">
              科目 {{ item.score_breakdown.subject }} · 年级 {{ item.score_breakdown.grade }} · 距离 {{ item.score_breakdown.distance }}
            </div>
          </div>

          <div class="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
            <div class="text-sm text-slate-500">
              信息费
              <span class="font-bold text-primary-600">¥{{ item.calculated_info_fee }}</span>
              <span class="text-xs text-slate-400">
                （定金¥{{ item.deposit_amount }} + 尾款¥{{ item.balance_amount }}）
              </span>
            </div>
            <button
              class="rounded-xl px-5 py-2 text-xs font-semibold"
              :class="item.already_applied ? 'bg-gray-100 text-gray-400' : 'header-gradient text-white'"
              :disabled="item.already_applied"
              @click="goOrder(item)"
            >
              {{ item.already_applied ? "已投递" : "去投递" }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 底部导航 -->
    <TeacherTabbar />

    <!-- 订单详情弹出层 -->
    <van-action-sheet
      v-model:show="sheetVisible"
      :title="sheetOrder?.grade_subject || ''"
      :description="sheetOrder ? `${sheetOrder.fuzzy_address}${sheetOrder.subway_remark ? ' · ' + sheetOrder.subway_remark : ''}` : ''"
    >
      <div v-if="sheetOrder" class="p-4">
        <div class="bg-gray-50 rounded-xl p-3 mb-3 text-sm">
          信息费
          <span class="text-primary-600 font-bold text-lg ml-2">¥{{ sheetOrder.calculated_info_fee }}</span>
          <div class="text-xs text-gray-400 mt-1">
            定金 ¥{{ sheetOrder.deposit_amount }} + 尾款 ¥{{ sheetOrder.balance_amount }}
          </div>
        </div>
        <button
          class="w-full bg-gray-50 rounded-xl py-3 mb-2 text-sm font-medium"
          @click="sheetVisible = false; router.push(`/teacher/orders/${sheetOrder.id}`)"
        >
          查看详情
        </button>
        <button
          class="w-full header-gradient text-white rounded-xl py-3 text-sm font-semibold"
          @click="sheetVisible = false; handleApply(sheetOrder)"
        >
          一键投递
        </button>
      </div>
    </van-action-sheet>

    <!-- 中介切换 -->
    <van-popup v-model:show="agentPickerVisible" round position="bottom">
      <div class="max-h-[70vh] overflow-y-auto p-4">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <div class="text-base font-semibold text-slate-950">选择中介橱窗</div>
            <div class="mt-1 text-xs text-slate-500">切换后地图会展示对应中介的订单</div>
          </div>
          <button class="rounded-lg bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700" @click="agentFormVisible = true">
            添加
          </button>
        </div>

        <div class="space-y-2">
          <div
            v-for="code in savedAgents"
            :key="code"
            class="flex items-center gap-3 rounded-xl border p-3"
            :class="code === inviteCode ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
          >
            <button class="min-w-0 flex-1 text-left" @click="switchAgent(code)">
              <div class="truncate text-sm font-semibold text-slate-950">
                {{ code === inviteCode ? (orderStore.boardTenantName || '当前中介') : '中介橱窗' }}
              </div>
              <div class="mt-1 text-xs text-slate-500">邀请码：{{ code }}</div>
            </button>
            <button
              class="rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-600"
              @click="removeAgent(code)"
            >
              移除
            </button>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- 添加中介 -->
    <van-popup v-model:show="agentFormVisible" round position="bottom">
      <div class="p-4">
        <div class="mb-4 text-base font-semibold text-slate-950">添加中介橱窗</div>
        <van-field
          v-model="newInviteCode"
          label="邀请码"
          placeholder="输入中介给你的邀请码"
          clearable
        />
        <button
          class="mt-4 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white"
          @click="addAgent"
        >
          添加并查看
        </button>
      </div>
    </van-popup>

    <!-- 加载中 -->
    <van-overlay :show="orderStore.loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
  </div>
</template>

<style scoped>
#map-container {
  width: 100%;
  height: 100%;
}

.board-toolbar {
  min-height: 56px;
  box-shadow: 0 6px 18px rgba(22, 40, 68, 0.14);
}

.agent-button,
.toolbar-icon,
.toolbar-login {
  min-height: 40px;
}

.toolbar-icon {
  width: 42px;
  height: 42px;
}

.recommendation-drawer {
  pointer-events: none;
}

.recommendation-drawer > * {
  pointer-events: auto;
}

.recommendation-handle {
  min-height: 48px;
}

.recommendation-list {
  overscroll-behavior: contain;
}

@media (min-width: 640px) {
  .recommendation-drawer {
    left: auto;
    right: 16px;
    width: min(420px, calc(100vw - 32px));
  }
}
</style>
