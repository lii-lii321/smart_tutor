<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { getApiErrorMessage, getApiErrorStatus } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { useOrderStore } from "@/stores/order";
import { useAuthStore } from "@/stores/auth";
import { useAMap } from "@/composables/useAMap";
import {
  useBoardFilters,
  stageOptions,
  type EducationStage,
} from "@/composables/useBoardFilters";
import { publicApi } from "@/api/orders";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import CityPicker from "@/components/teacher/CityPicker.vue";
import RecommendList from "@/components/teacher/RecommendList.vue";
import OrderSheet from "@/components/teacher/OrderSheet.vue";
import AgentPicker from "@/components/teacher/AgentPicker.vue";
import { resolveInviteCode } from "@/utils/inviteCode";
import type { PublicOrderBrief, TeacherOrderRecommendationItem } from "@/api/types";
import { showToast, showLoadingToast, closeToast } from "vant";

const route = useRoute();
const router = useRouter();
const orderStore = useOrderStore();
const auth = useAuthStore();

const inviteCode = ref(resolveInviteCode(route.params.inviteCode as string));
const mapRef = ref<HTMLDivElement>();
// 地图生命周期/标记/高亮/定位收敛到 useAMap（P1-1）
const amap = useAMap({
  mapRef,
  containerId: "map-container",
  onMarkerClick: (order) => {
    sheetOrder.value = order;
    sheetVisible.value = true;
  },
});
const agentPickerVisible = ref(false);
const cityPickerVisible = ref(false);
const addAgentError = ref("");
const savedAgents = ref<string[]>([]);

// 筛选与城市归并逻辑收敛到 useBoardFilters（学段/科目/城市筛选、区县索引、坐标兜底）
const {
  selectedStage,
  selectedSubjects,
  selectedCity,
  selectedCityCenter,
  filterSheetVisible,
  availableSubjects,
  cityOptions,
  activeCityLabel,
  hasActiveFilters,
  activeFilterCount,
  filteredOrders,
  resetFilters,
  fetchCityContext,
  centerMapOnCity,
  mergeCityContext,
} = useBoardFilters({
  boardOrders: () => orderStore.boardOrders,
  getMap: () => amap.getMap(),
});

const recommendations = ref<TeacherOrderRecommendationItem[]>([]);
const recLoading = ref(false);
const recommendationsExpanded = ref(true);
// 403 = 被该中介拉黑或平台限制：与“暂无推荐”区分开，给出明确文案
const recommendationsBlocked = ref(false);
const recommendationsBlockReason = ref("");

const AGENT_STORAGE_KEY = "teacher_agent_invite_codes";

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

// 卸载守卫由 useAMap 内部管理（ensureMap 在已卸载时抛错，isDisposed 供视图跳过后续动作）

onMounted(async () => {
  readSavedAgents();
  showLoadingToast({ message: "加载中...", duration: 0 });

  try {
    await amap.ensureMap();
    if (amap.isDisposed()) return;

    // 加载订单数据 + 推荐
    await loadBoardByInvite(inviteCode.value, false);

    closeToast();
  } catch {
    closeToast();
    if (!amap.isDisposed()) {
      showToast("加载失败，请下拉刷新");
    }
  }
});

async function refreshBoard() {
  try {
    await loadBoardByInvite(inviteCode.value, false);
  } catch (e) {
    showToast(getApiErrorMessage(e, "刷新失败，请稍后重试"));
  }
}

async function loadBoardByInvite(code: string, updateRoute = true) {
  const normalized = code.trim();
  if (!normalized) {
    showToast("请输入中介邀请码");
    return;
  }

  await orderStore.loadBoard(normalized);
  inviteCode.value = normalized;
  if (selectedCity.value !== "all" && !cityOptions.value.includes(selectedCity.value)) {
    selectedCity.value = "all";
  }
  if (!savedAgents.value.includes(normalized)) {
    savedAgents.value.unshift(normalized);
    persistSavedAgents();
  }
  amap.renderMarkers(filteredOrders.value);
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
    recommendationsBlocked.value = false;
    return;
  }
  recLoading.value = true;
  try {
    const res = await publicApi.getRecommendations(inviteCode.value, 12);
    recommendations.value = res.items || [];
    recommendationsBlocked.value = false;
  } catch (e) {
    recommendations.value = [];
    if (getApiErrorStatus(e) === 403) {
      recommendationsBlocked.value = true;
      recommendationsBlockReason.value =
        getApiErrorMessage(e, "该中介暂不向您开放订单推荐");
    } else {
      recommendationsBlocked.value = false;
    }
  } finally {
    recLoading.value = false;
  }
}

function focusRecommendation(order: TeacherOrderRecommendationItem) {
  recommendationsExpanded.value = false;
  // 放大到楼栋级并高亮目标标记：88+ 点位密集时靠肉眼找针不现实
  if (!amap.focusOrder(order)) {
    showToast("该订单暂未提供可定位的位置");
  }
}

function goOrder(order: TeacherOrderRecommendationItem) {
  if (!auth.isLoggedIn) {
    goLogin();
    return;
  }
  router.push(`/teacher/orders/${order.id}`);
}

watch([selectedStage, selectedSubjects], () => {
  if (!amap.isReady()) return;
  amap.renderMarkers(filteredOrders.value, false);
});

watch(selectedCity, async (city) => {
  if (!amap.isReady()) return;
  if (city === "all") {
    selectedCityCenter.value = null;
    amap.renderMarkers(filteredOrders.value, true);
    return;
  }
  const context = await fetchCityContext(city);
  if (selectedCity.value !== city) return;
  mergeCityContext(city, context.districts);
  selectedCityCenter.value = context.center;
  amap.renderMarkers(filteredOrders.value, false);
  await centerMapOnCity(city);
});

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

function selectStage(stage: EducationStage) {
  selectedStage.value = stage;
  selectedSubjects.value = [];
}

// 点击 Marker → 弹 OrderSheet（状态由组件 v-model 管理）
const sheetVisible = ref(false);
const sheetOrder = ref<PublicOrderBrief | null>(null);

function goToOrder(order: PublicOrderBrief) {
  router.push(`/teacher/orders/${order.id}`);
}

async function handleApply(order: PublicOrderBrief) {
  if (!auth.isLoggedIn) {
    goLogin();
    return;
  }
  router.push(`/teacher/orders/${order.id}`);
}

function goLogin() {
  router.push({
    path: "/teacher/login",
    query: { inviteCode: inviteCode.value, redirect: route.fullPath },
  });
}

async function addAgent(code: string) {
  if (!code) {
    addAgentError.value = "请输入中介邀请码";
    return;
  }
  addAgentError.value = "";
  try {
    await loadBoardByInvite(code);
    showToast("已添加并切换");
  } catch (e) {
    addAgentError.value = getApiErrorMessage(e, "中介不存在或邀请码无效");
  }
}

async function copyAgentWechat() {
  const wechat = orderStore.boardContactWechat;
  if (!wechat) return;
  try {
    await navigator.clipboard.writeText(wechat);
    showToast("微信号已复制");
  } catch {
    showToast("复制失败，请手动复制");
  }
}

const locateUser = amap.locateUser;
const locating = amap.locating;

async function switchAgent(code: string) {
  agentPickerVisible.value = false;
  try {
    await loadBoardByInvite(code);
  } catch (e) {
    showToast(getApiErrorMessage(e, "切换失败"));
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
      <!-- 顶部中介栏 -->
      <div class="board-toolbar absolute left-0 right-0 top-0 z-10 border-b border-slate-200 bg-white/95 px-2 py-1 shadow-sm backdrop-blur">
        <div class="flex items-center gap-1.5">
          <button
            class="agent-button min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-100 px-2.5 py-1 text-left sm:flex-none sm:w-72"
            @click="agentPickerVisible = true"
          >
            <div class="flex min-w-0 items-center gap-1.5 leading-4">
              <span class="shrink-0 text-[10px] text-slate-500">当前中介</span>
              <span class="truncate text-[13px] font-semibold text-slate-900">
                {{ orderStore.boardTenantName || inviteCode }}
              </span>
            </div>
          </button>
          <button
            class="toolbar-icon inline-flex shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-100 p-1.5 text-slate-700"
            aria-label="切换中介"
            @click="agentPickerVisible = true"
          >
            <van-icon
              name="exchange"
              size="18"
            />
          </button>
          <button
            class="relative inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 px-2.5 py-1.5 text-[11px] font-semibold text-slate-700"
            aria-label="筛选订单"
            @click="filterSheetVisible = true"
          >
            <van-icon
              name="filter-o"
              size="14"
            />
            筛选
            <span
              v-if="activeFilterCount"
              class="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-600 px-1 text-[9px] font-bold text-white"
            >{{ activeFilterCount }}</span>
          </button>
          <button
            v-if="!auth.isLoggedIn"
            class="toolbar-login shrink-0 rounded-lg border border-slate-200 bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700"
            @click="goLogin"
          >
            登录
          </button>
        </div>
        <div
          v-if="orderStore.boardContactWechat"
          class="mt-1 flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-2 py-1 text-[11px] leading-4"
        >
          <span class="min-w-0 truncate text-slate-500">
            中介微信：<span class="font-mono text-slate-800">{{ orderStore.boardContactWechat }}</span>
          </span>
          <button
            class="shrink-0 font-medium text-blue-600"
            @click="copyAgentWechat"
          >
            复制
          </button>
        </div>
      </div>

      <!-- 地图 -->
      <div
        id="map-container"
        ref="mapRef"
        class="w-full h-full"
      />

      <!-- 地图底部快捷操作 -->
      <div class="absolute bottom-[88px] left-4 z-10 text-xs font-semibold text-[#1a365d] drop-shadow-[0_1px_1px_rgba(255,255,255,0.9)]">
        {{ hasActiveFilters ? "符合筛选" : "活跃订单" }} {{ filteredOrders.length }} 单
      </div>
      <!-- 定位/刷新：固定定位与"为你推荐"抽屉同一坐标系，收起时位于抽屉把手上方，
           展开浏览推荐时隐藏（地图工具让位，收回抽屉即恢复） -->
      <div
        v-show="!recommendationsExpanded"
        class="fixed bottom-[118px] right-4 z-30 flex flex-col gap-2"
      >
        <button
          class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white text-[#1a365d] shadow-lg ring-1 ring-slate-200"
          aria-label="定位当前位置"
          :disabled="locating"
          @click="locateUser"
        >
          <van-loading
            v-if="locating"
            color="#2563eb"
            size="16"
          />
          <van-icon
            v-else
            name="location-o"
            size="18"
            color="#2563eb"
          />
        </button>
        <button
          class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#1a365d] text-white shadow-lg"
          aria-label="刷新地图"
          @click="refreshBoard"
        >
          <van-icon
            name="replay"
            size="16"
          />
        </button>
      </div>
    </div>

    <!-- 为你推荐（地图下方悬浮抽屉） -->
    <RecommendList
      v-model:expanded="recommendationsExpanded"
      :items="recommendations"
      :loading="recLoading"
      :blocked="recommendationsBlocked"
      :block-reason="recommendationsBlockReason"
      :logged-in="auth.isLoggedIn"
      @focus="focusRecommendation"
      @go-order="goOrder"
      @login="goLogin"
    />

    <!-- 底部导航 -->
    <TeacherTabbar />

    <!-- 订单详情弹出层 -->
    <OrderSheet
      v-model:show="sheetVisible"
      :order="sheetOrder"
      @view="goToOrder"
      @apply="handleApply"
    />

    <!-- 筛选面板（电商式底部弹层：学段/学科/城市一次配齐） -->
    <van-popup
      v-model:show="filterSheetVisible"
      round
      position="bottom"
    >
      <div class="max-h-[75vh] overflow-y-auto p-4">
        <div class="mb-4 flex items-center justify-between">
          <div class="text-base font-semibold text-slate-950">
            筛选订单
          </div>
          <button
            class="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500"
            aria-label="关闭筛选"
            @click="filterSheetVisible = false"
          >
            <van-icon name="cross" />
          </button>
        </div>

        <div class="mb-1.5 text-xs font-medium text-slate-500">
          学段
        </div>
        <div class="mb-4 flex flex-wrap gap-2">
          <button
            v-for="stage in stageOptions"
            :key="stage.value"
            class="rounded-lg px-3 py-1.5 text-xs font-medium"
            :class="selectedStage === stage.value ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
            @click="selectStage(stage.value)"
          >
            {{ stage.label }}
          </button>
        </div>

        <div class="mb-1.5 text-xs font-medium text-slate-500">
          学科（可多选）
        </div>
        <div class="mb-4 flex flex-wrap gap-2">
          <button
            class="rounded-lg px-3 py-1.5 text-xs font-medium"
            :class="selectedSubjects.length === 0 ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
            @click="clearSubjects"
          >
            全部学科
          </button>
          <button
            v-for="subject in availableSubjects"
            :key="subject"
            class="rounded-lg px-3 py-1.5 text-xs font-medium"
            :class="selectedSubjects.includes(subject) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
            @click="toggleSubject(subject)"
          >
            {{ subject }}
          </button>
        </div>

        <div class="mb-1.5 text-xs font-medium text-slate-500">
          城市
        </div>
        <button
          class="mb-4 flex w-full items-center justify-between rounded-lg bg-slate-100 px-3 py-2.5 text-sm text-slate-700"
          @click="cityPickerVisible = true"
        >
          <span class="flex items-center gap-1.5">
            <van-icon
              name="location-o"
              size="14"
              color="#2563eb"
            />
            {{ activeCityLabel }}
          </span>
          <van-icon
            name="arrow"
            size="14"
            color="#94a3b8"
          />
        </button>

        <div class="mt-2 grid grid-cols-2 gap-3 pb-2">
          <button
            class="rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-600"
            @click="resetFilters"
          >
            重置
          </button>
          <button
            class="header-gradient rounded-xl py-2.5 text-sm font-semibold text-white"
            @click="filterSheetVisible = false"
          >
            完成
          </button>
        </div>
      </div>
    </van-popup>

    <!-- 城市选择 -->
    <CityPicker
      v-model:show="cityPickerVisible"
      v-model:city="selectedCity"
      :options="cityOptions"
    />
    <AgentPicker
      v-model:show="agentPickerVisible"
      v-model:add-error="addAgentError"
      :agents="savedAgents"
      :current-code="inviteCode"
      :tenant-name="orderStore.boardTenantName"
      @switch="switchAgent"
      @remove="removeAgent"
      @add="addAgent"
    />

    <!-- 加载中 -->
    <van-overlay :show="orderStore.loading">
      <div class="flex items-center justify-center h-full">
        <van-loading
          type="spinner"
          size="32"
          color="#2563eb"
        />
      </div>
    </van-overlay>
  </div>
</template>

<style scoped>
#map-container {
  width: 100%;
  height: 100%;
}

/* 筛选行横向滚动条隐藏：滚动手势/滚轮仍可用，避免 Windows 经典滚动条压在地图上 */
.no-scrollbar {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.no-scrollbar::-webkit-scrollbar {
  display: none;
}

.board-toolbar {
  min-height: 40px;
  box-shadow: 0 4px 12px rgba(22, 40, 68, 0.12);
}

.agent-button,
.toolbar-icon,
.toolbar-login {
  min-height: 32px;
}

.toolbar-icon {
  width: 32px;
  height: 32px;
}

.recommendation-drawer {
  pointer-events: none;
}

:deep(.teacher-tabbar) {
  z-index: 50 !important;
}

.recommendation-drawer > * {
  pointer-events: auto;
}

.recommendation-handle {
  width: min(280px, calc(100vw - 32px));
  min-height: 34px;
  margin-left: auto;
  margin-right: auto;
  padding: 0 10px;
  border-radius: 10px;
}

/* 高德原生刻度尺固定在推荐栏上方，避开 Logo 与底部导航。 */
:deep(.amap-scalecontrol) {
  bottom: 68px !important;
  left: 16px !important;
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