<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { getApiErrorMessage, getApiErrorStatus } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { useOrderStore } from "@/stores/order";
import { useAuthStore } from "@/stores/auth";
import { useAMap } from "@/composables/useAMap";
import {
  useBoardFilters,
  stageOptions,
  boardSortOptions,
  type EducationStage,
} from "@/composables/useBoardFilters";
import { publicApi } from "@/api/orders";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import CityPicker from "@/components/teacher/CityPicker.vue";
import RecommendList from "@/components/teacher/RecommendList.vue";
import TeacherOrderCard from "@/components/teacher/TeacherOrderCard.vue";
import OrderSheet from "@/components/teacher/OrderSheet.vue";
import AgentPicker from "@/components/teacher/AgentPicker.vue";
import AppEmpty from "@/components/ui/AppEmpty.vue";
import AppButton from "@/components/ui/AppButton.vue";
import { resolveInviteCode } from "@/utils/inviteCode";
import type { PublicOrderBrief, TeacherOrderRecommendationItem } from "@/api/types";
import { showToast, showLoadingToast, closeToast } from "vant";

const route = useRoute();
const router = useRouter();
const orderStore = useOrderStore();
const auth = useAuthStore();

const inviteCode = ref(resolveInviteCode(route.params.inviteCode as string));
const mapRef = ref<HTMLDivElement>();
// 找单 = 首页的两种浏览模式：默认推荐列表（产品第一视觉层），地图降级为第二模式。
// 地图懒初始化：首次切到地图模式才 ensureMap，避免隐藏容器里初始化出零尺寸地图。
const viewMode = ref<"recommend" | "map">("recommend");
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
const addAgentLoading = ref(false);
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
  matchesFilters,
  sortMode,
  sortOrders,
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
// 推荐列表最近一次成功拉取的客户端时间：问候区"今日推荐"新鲜度信号的数据源
const recUpdatedAt = ref<Date | null>(null);
// 403 = 被该中介拉黑或平台限制：与"暂无推荐"区分开，给出明确文案
const recommendationsBlocked = ref(false);
const recommendationsBlockReason = ref("");
// 非 403 的拉取失败（H4）：旧内容渲染优先，仅在列表为空时显示错误态 + 重新加载
const recommendationsError = ref(false);

// 推荐列表与橱窗列表共用同一筛选口径：用户做了筛选后推荐同步收敛；
// 排序偏好同样生效（距离优先基于推荐携带的预计距离，橱窗公共单无此字段）
const filteredRecommendations = computed(() =>
  sortOrders(recommendations.value.filter(matchesFilters))
);

// 新鲜度文案：当天显示"HH:mm 更新"，跨天带上日期，避免"今日推荐"名不副实
const isToday = (d: Date) => {
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
};
const recUpdatedLabel = computed(() => {
  const d = recUpdatedAt.value;
  if (!d) return "";
  const hhmm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return isToday(d) ? `${hhmm} 更新` : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hhmm} 更新`;
});
const recIsFreshToday = computed(() => !!recUpdatedAt.value && isToday(recUpdatedAt.value));
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

async function ensureMapReady() {
  if (amap.isReady() || amap.isDisposed()) return;
  await amap.ensureMap();
  amap.renderMarkers(filteredOrders.value);
  if (selectedCity.value !== "all") {
    await centerMapOnCity(selectedCity.value);
  }
}

async function switchViewMode(mode: "recommend" | "map") {
  if (viewMode.value === mode) return;
  viewMode.value = mode;
  if (mode === "map") {
    try {
      await ensureMapReady();
    } catch {
      showToast("地图加载失败，请检查网络后重试");
    }
  }
}

onMounted(async () => {
  readSavedAgents();
  showLoadingToast({ message: "加载中...", duration: 0 });

  try {
    // 推荐列表模式不依赖地图：数据先行，地图等首次切换再初始化
    await loadBoardByInvite(inviteCode.value, false);
    if (viewMode.value === "map") {
      await ensureMapReady();
    }

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
    recommendationsError.value = false;
    recUpdatedAt.value = null;
    return;
  }
  recLoading.value = true;
  try {
    const res = await publicApi.getRecommendations(inviteCode.value, 12);
    recommendations.value = res.items || [];
    recUpdatedAt.value = new Date();
    recommendationsBlocked.value = false;
    recommendationsError.value = false;
  } catch (e) {
    // 失败不清空旧内容（旧内容渲染优先，仅列表为空时显示错误态）；toast 保持既有口径
    if (getApiErrorStatus(e) === 403) {
      recommendationsBlocked.value = true;
      recommendationsBlockReason.value =
        getApiErrorMessage(e, "该中介暂不向您开放订单推荐");
      recommendationsError.value = false;
    } else {
      recommendationsBlocked.value = false;
      recommendationsError.value = true;
    }
    showToast(getApiErrorMessage(e, "推荐列表加载失败，请重试"));
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

function goOrder(order: TeacherOrderRecommendationItem | PublicOrderBrief) {
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

// 地图懒初始化的时序补画：若用户在订单数据返回前就切入地图模式，
// 首次 renderMarkers 会因地图未 ready 被跳过——数据到达时补画一次
watch(
  () => orderStore.boardOrders.length,
  () => {
    if (viewMode.value === "map" && amap.isReady()) {
      amap.renderMarkers(filteredOrders.value);
    }
  }
);

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
  // adding 下发 AgentPicker：按钮 loading 且禁点，防止重复提交并发加载
  addAgentLoading.value = true;
  try {
    await loadBoardByInvite(code);
    showToast("已添加并切换");
  } catch (e) {
    addAgentError.value = getApiErrorMessage(e, "中介不存在或邀请码无效");
  } finally {
    addAgentLoading.value = false;
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

const greetingName = () => auth.teacher?.name || "";

// 本周动态 banner 文案：只统计在招橱窗（filteredOrders），推荐列表是个人视角不宜混入
const weekBanner = computed(() => {
  const now = Date.now();
  const weekOrders = filteredOrders.value.filter((order) => {
    if (!order.created_at) return false;
    const t = new Date(order.created_at).getTime();
    return !Number.isNaN(t) && now - t <= 7 * 24 * 3600 * 1000;
  });
  if (!weekOrders.length) return "";
  const maxPrice = Math.max(...weekOrders.map((order) => Number(order.base_price) || 0));
  const priceHint = maxPrice > 0 ? ` · 最高 ¥${maxPrice}/时` : "";
  return `本周新增 ${weekOrders.length} 单${priceHint}，先到先得`;
});
</script>

<template>
  <div class="board-page flex h-screen flex-col bg-page pb-24">
    <!-- 顶部共享工具栏（推荐/地图两模式通用，不再覆盖在地图上） -->
    <header class="board-toolbar relative z-30 flex-none border-b border-default bg-white px-2 py-1.5">
      <div class="flex items-center gap-1.5">
        <!-- 中介来源：从"当前中介"标签 + flex-1 占位，降级为紧凑的来源 chip。
             邀请码/中介是 URL 层的分发机制，不是教员要做的选择，
             让它占据工具栏第一视觉位会挤掉真正要看的匹配结果。 -->
        <button
          class="agent-button min-w-0 max-w-[46%] shrink rounded-lg border border-default bg-surface-soft px-2.5 py-1.5 text-left"
          aria-label="切换中介橱窗"
          @click="agentPickerVisible = true"
        >
          <span class="flex min-w-0 items-center gap-1 leading-4">
            <van-icon name="shop-o" size="12" class="shrink-0 text-muted" />
            <span class="truncate text-body-sm font-medium text-secondary">
              {{ orderStore.boardTenantName || inviteCode }}
            </span>
            <van-icon name="arrow-down" size="10" class="shrink-0 text-muted" />
          </span>
        </button>
        <button
          class="relative inline-flex shrink-0 items-center gap-1 rounded-lg border border-default bg-surface-soft px-2.5 py-1.5 text-caption font-semibold text-secondary"
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
            class="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-800 px-1 text-caption font-bold text-white"
          >{{ activeFilterCount }}</span>
        </button>
        <!-- 模式切换：推荐找单（默认）/ 地图找单（UI 2.0 胶囊分段） -->
        <div class="flex shrink-0 items-center rounded-full border border-default bg-surface p-0.5">
          <button
            class="rounded-full px-2.5 py-1 text-caption font-semibold"
            :class="viewMode === 'recommend' ? 'bg-ink text-white' : 'text-secondary'"
            @click="switchViewMode('recommend')"
          >
            推荐
          </button>
          <button
            class="rounded-full px-2.5 py-1 text-caption font-semibold"
            :class="viewMode === 'map' ? 'bg-ink text-white' : 'text-secondary'"
            @click="switchViewMode('map')"
          >
            地图
          </button>
        </div>
        <button
          v-if="!auth.isLoggedIn"
          class="toolbar-login shrink-0 rounded-lg border border-default bg-surface-soft px-2.5 py-1 text-caption font-semibold text-secondary"
          @click="goLogin"
        >
          登录
        </button>
      </div>
      <div
        v-if="orderStore.boardContactWechat"
        class="mt-1 flex items-center justify-between gap-2 rounded-lg bg-surface-soft px-2 py-1 text-caption leading-4"
      >
        <span class="min-w-0 truncate text-secondary">
          中介微信：<span class="font-mono text-primary">{{ orderStore.boardContactWechat }}</span>
        </span>
        <button
          class="shrink-0 font-medium text-secondary"
          @click="copyAgentWechat"
        >
          复制
        </button>
      </div>
    </header>

    <main class="relative min-h-0 flex-1">
      <!-- ── 推荐模式（默认首页）：平台在帮我找适合我的订单 ── -->
      <div v-if="viewMode === 'recommend'" class="absolute inset-0 overflow-y-auto px-4 pb-6 pt-3">
        <!-- 问候与匹配概览（UI 2.0：大标题信息流，一句话讲清匹配多少单、凭什么） -->
        <section class="mb-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h1 class="text-display font-bold leading-9 text-ink">
                {{ auth.isLoggedIn && greetingName() ? `你好，${greetingName()}` : "找到适合你的家教订单" }}
              </h1>
              <p class="mt-1 text-pretty text-body leading-5 text-muted">
                <template v-if="auth.isLoggedIn">
                  为你匹配 <span class="font-semibold text-ink">{{ filteredRecommendations.length }}</span> 个订单
                  <template v-if="orderStore.boardTenantName">
                    · 来自 {{ orderStore.boardTenantName }}
                  </template>
                </template>
                <template v-else>
                  该橱窗共 <span class="font-semibold text-ink">{{ filteredOrders.length }}</span> 单在招
                  · 登录后按你的画像智能推荐
                </template>
              </p>
            </div>

            <!-- 右上角新鲜度卡：概念稿"今日推荐"位的收敛版，仅登录且有推荐时出现 -->
            <div
              v-if="auth.isLoggedIn && filteredRecommendations.length && recUpdatedAt"
              class="flex shrink-0 items-center gap-2.5 rounded-xl border border-default bg-surface py-2 pl-2.5 pr-3.5"
            >
              <span class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ai-soft text-ai-deep">
                <van-icon name="clock-o" size="17" />
              </span>
              <span class="min-w-0">
                <span class="block text-xs font-semibold leading-4 text-secondary">
                  {{ recIsFreshToday ? "今日推荐" : "推荐更新" }}
                </span>
                <span class="mt-0.5 block text-caption.5 text-muted">{{ recUpdatedLabel }}</span>
              </span>
            </div>
          </div>
        </section>

        <!-- 本周动态 banner（UI 2.0 明黄记忆点）：橱窗近 7 天新增与最高课酬，
             全部由 filteredOrders 的 created_at / base_price 派生，无新接口；无新增单整块隐藏 -->
        <div
          v-if="weekBanner"
          class="mb-4 flex items-start gap-2 rounded-2xl bg-accent-soft px-3.5 py-3"
        >
          <van-icon name="star" size="15" class="mt-0.5 shrink-0 text-accent-deep" />
          <p class="min-w-0 text-xs font-medium leading-5 text-accent-ink">
            {{ weekBanner }}
          </p>
        </div>

        <!-- 为你推荐（登录后按画像匹配，筛选联动收敛） -->
        <section class="mb-5">
          <div
            v-if="auth.isLoggedIn && !recommendationsBlocked && filteredRecommendations.length"
            class="mb-2 flex items-center justify-between"
          >
            <h2 class="text-sm font-bold text-primary">为你推荐</h2>
          </div>

          <!-- 排序快捷 chips：与筛选面板的排序共用同一 sortMode，不新增筛选语义 -->
          <div
            v-if="auth.isLoggedIn && !recommendationsBlocked && filteredRecommendations.length"
            class="mb-3 flex flex-wrap gap-1.5"
          >
            <button
              v-for="opt in boardSortOptions"
              :key="opt.value"
              class="rounded-full px-2.5 py-1 text-caption font-medium transition-colors"
              :class="sortMode === opt.value ? 'bg-ink text-white' : 'bg-surface-soft text-secondary'"
              @click="sortMode = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>

          <div v-if="auth.isLoggedIn && recLoading" class="space-y-3">
            <div
              v-for="i in 3"
              :key="i"
              class="rounded-2xl bg-surface p-4 shadow-card"
            >
              <van-skeleton
                title
                :row="2"
                title-width="55%"
                row-width="85%"
              />
            </div>
          </div>

          <div
            v-else-if="auth.isLoggedIn && recommendationsBlocked"
            class="rounded-2xl border border-warning-mid bg-warning-soft p-5 text-center text-sm text-warning-deep shadow-sm"
          >
            <van-icon
              name="warning-o"
              class="mb-1"
              size="20"
            />
            <div>{{ recommendationsBlockReason }}</div>
            <div class="mt-1 text-xs text-warning-deep/80">如有疑问请联系对应中介沟通。</div>
          </div>

          <div
            v-else-if="auth.isLoggedIn && filteredRecommendations.length"
            class="space-y-3"
          >
            <TeacherOrderCard
              v-for="item in filteredRecommendations"
              :key="item.id"
              :order="item"
              :recommendation="item"
              @open="goOrder"
              @apply="goOrder"
            />
          </div>

          <!-- 有推荐但被筛没了：给"重置筛选"出口 -->
          <AppEmpty
            v-else-if="auth.isLoggedIn && recommendations.length"
            icon="🔍"
            title="当前筛选下暂无推荐订单"
            description="调整筛选条件，或查看下方全部在招订单"
          >
            <template #action>
              <button
                v-if="hasActiveFilters"
                class="rounded-xl border border-default bg-surface px-4 py-2 text-xs font-medium text-secondary"
                @click="resetFilters"
              >
                重置筛选
              </button>
            </template>
          </AppEmpty>

          <!-- 拉取失败（非 403 拉黑）：参照 MyApplications 错误态范式——warning 图标+说明+重新加载；
               旧内容渲染优先，排在其后走到这里即列表为空 -->
          <div
            v-else-if="auth.isLoggedIn && recommendationsError"
            class="flex flex-col items-center rounded-2xl border border-default bg-surface p-6 text-center shadow-sm"
          >
            <van-icon name="warning-o" size="32" class="text-warning" />
            <p class="mt-3 text-sm font-medium text-primary">推荐列表加载失败</p>
            <p class="mt-1 text-xs leading-5 text-muted">网络或服务暂时不可用，在招订单不受影响</p>
            <div class="mt-4">
              <AppButton size="md" @click="loadRecommendations">重新加载</AppButton>
            </div>
          </div>

          <AppEmpty
            v-else-if="auth.isLoggedIn"
            icon="✨"
            title="暂无匹配的推荐订单"
            description="看看下面的在招订单，或切换右上角「地图」模式找单"
          />

          <!-- 未登录：推荐价值前置展示，登录动作就地完成 -->
          <AppEmpty
            v-else
            icon="✨"
            title="登录后按你的画像智能推荐"
            description="科目 / 年级 / 距离 / 院校多维匹配"
          >
            <template #action>
              <button
                class="rounded-full bg-ink px-6 py-2 text-sm font-semibold text-white"
                @click="goLogin"
              >
                登录查看推荐
              </button>
            </template>
          </AppEmpty>
        </section>

        <!-- 在招订单（橱窗公共数据，未登录也可浏览） -->
        <section>
          <div class="mb-2 flex items-center justify-between">
            <h2 class="text-sm font-bold text-primary">
              {{ hasActiveFilters ? "筛选结果" : "在招订单" }}
            </h2>
            <span class="text-caption text-muted">{{ filteredOrders.length }} 单</span>
          </div>

          <div
            v-if="filteredOrders.length"
            class="space-y-3"
          >
            <TeacherOrderCard
              v-for="order in filteredOrders"
              :key="order.id"
              :order="order"
              @open="goOrder"
            />
          </div>

          <AppEmpty
            v-else
            icon="🔍"
            title="暂无符合条件的订单"
            :description="hasActiveFilters ? '调整筛选条件，或重置后查看全部订单' : '该中介暂时没有在招订单，换个橱窗看看'"
          >
            <template #action>
              <button
                v-if="hasActiveFilters"
                class="rounded-xl border border-default bg-surface px-4 py-2 text-xs font-medium text-secondary"
                @click="resetFilters"
              >
                重置筛选
              </button>
            </template>
          </AppEmpty>
        </section>

        <button
          class="mx-auto mt-5 flex items-center gap-1 text-xs text-muted"
          @click="switchViewMode('map')"
        >
          <van-icon
            name="location-o"
            size="12"
          />
          想按位置找单？切换到「地图」模式
        </button>
      </div>

      <!-- ── 地图模式（第二浏览方式）：v-show 保住地图实例 ── -->
      <div
        v-show="viewMode === 'map'"
        class="absolute inset-0"
      >
        <div
          id="map-container"
          ref="mapRef"
          class="h-full w-full"
        />

        <!-- 地图底部订单计数 -->
        <div class="absolute bottom-[88px] left-4 z-10 text-xs font-semibold text-brand-800 drop-shadow-[0_1px_1px_rgba(255,255,255,0.9)]">
          {{ hasActiveFilters ? "符合筛选" : "活跃订单" }} {{ filteredOrders.length }} 单
        </div>
        <!-- 定位/刷新：固定定位与"为你推荐"抽屉同一坐标系，收起时位于抽屉把手上方，
             展开浏览推荐时隐藏（地图工具让位，收回抽屉即恢复） -->
        <div
          v-show="!recommendationsExpanded"
          class="fixed bottom-[118px] right-4 z-30 flex flex-col gap-2"
        >
          <button
            class="inline-flex h-10 w-10 items-center justify-center rounded-full bg-surface text-brand-800 shadow-lg ring-1 ring-default"
            aria-label="定位当前位置"
            :disabled="locating"
            @click="locateUser"
          >
            <van-loading
              v-if="locating"
              size="16"
            />
            <van-icon
              v-else
              name="location-o"
              size="18"
            />
          </button>
          <button
            class="inline-flex h-10 w-10 items-center justify-center rounded-full bg-surface text-brand-800 shadow-lg ring-1 ring-default"
            aria-label="刷新订单"
            @click="refreshBoard"
          >
            <van-icon
              name="replay"
              size="16"
            />
          </button>
        </div>

        <!-- 为你推荐（地图下方悬浮抽屉，与列表模式同一筛选口径） -->
        <RecommendList
          v-model:expanded="recommendationsExpanded"
          :items="filteredRecommendations"
          :loading="recLoading"
          :blocked="recommendationsBlocked"
          :block-reason="recommendationsBlockReason"
          :logged-in="auth.isLoggedIn"
          @focus="focusRecommendation"
          @go-order="goOrder"
          @login="goLogin"
        />
      </div>
    </main>

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
          <div class="text-base font-semibold text-primary">
            筛选订单
          </div>
          <button
            class="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-soft text-secondary"
            aria-label="关闭筛选"
            @click="filterSheetVisible = false"
          >
            <van-icon name="cross" />
          </button>
        </div>

        <div class="mb-1.5 text-xs font-medium text-secondary">
          学段
        </div>
        <div class="mb-4 flex flex-wrap gap-2">
          <button
            v-for="stage in stageOptions"
            :key="stage.value"
            class="rounded-full px-3 py-1.5 text-xs font-medium"
            :class="selectedStage === stage.value ? 'bg-ink text-white' : 'bg-surface-soft text-secondary'"
            @click="selectStage(stage.value)"
          >
            {{ stage.label }}
          </button>
        </div>

        <div class="mb-1.5 text-xs font-medium text-secondary">
          学科（可多选）
        </div>
        <div class="mb-4 flex flex-wrap gap-2">
          <button
            class="rounded-full px-3 py-1.5 text-xs font-medium"
            :class="selectedSubjects.length === 0 ? 'bg-ink text-white' : 'bg-surface-soft text-secondary'"
            @click="clearSubjects"
          >
            全部学科
          </button>
          <button
            v-for="subject in availableSubjects"
            :key="subject"
            class="rounded-full px-3 py-1.5 text-xs font-medium"
            :class="selectedSubjects.includes(subject) ? 'bg-ink text-white' : 'bg-surface-soft text-secondary'"
            @click="toggleSubject(subject)"
          >
            {{ subject }}
          </button>
        </div>

        <div class="mb-1.5 text-xs font-medium text-secondary">
          城市
        </div>
        <button
          class="mb-4 flex w-full items-center justify-between rounded-lg bg-surface-soft px-3 py-2.5 text-sm text-secondary"
          @click="cityPickerVisible = true"
        >
          <span class="flex items-center gap-1.5">
            <van-icon
              name="location-o"
              size="14"
            />
            {{ activeCityLabel }}
          </span>
          <van-icon
            name="arrow"
            size="14"
            color="var(--st-text-muted)"
          />
        </button>

        <div class="mb-1.5 text-xs font-medium text-secondary">
          排序
        </div>
        <div class="mb-2 flex flex-wrap gap-2">
          <button
            v-for="opt in boardSortOptions"
            :key="opt.value"
            class="rounded-full px-3 py-1.5 text-xs font-medium"
            :class="sortMode === opt.value ? 'bg-ink text-white' : 'bg-surface-soft text-secondary'"
            @click="sortMode = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
        <p class="mb-4 text-caption leading-4 text-muted">
          距离优先按推荐列表的预计距离排序（在招订单不含距离口径）。
        </p>

        <div class="mt-2 grid grid-cols-2 gap-3 pb-2">
          <AppButton
            size="md"
            variant="secondary"
            @click="resetFilters"
          >
            重置
          </AppButton>
          <AppButton
            size="md"
            @click="filterSheetVisible = false"
          >
            完成
          </AppButton>
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
      :adding="addAgentLoading"
      @switch="switchAgent"
      @remove="removeAgent"
      @add="addAgent"
    />

    <!-- 首屏 loading 反馈由 showLoadingToast + 推荐区骨架承担：
         此前的全屏 van-overlay 是黑闪硬规矩违例（半黑遮罩盖全屏），已移除 -->
  </div>
</template>

<style scoped>
#map-container {
  width: 100%;
  height: 100%;
}

.board-toolbar {
  min-height: 40px;
  box-shadow: 0 4px 12px rgba(23, 24, 28, 0.06);
}

.agent-button,
.toolbar-login {
  min-height: 32px;
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

/* 高德原生刻度尺固定在推荐栏上方，避开 Logo 与底部导航。 */
:deep(.amap-scalecontrol) {
  bottom: 68px !important;
  left: 16px !important;
}

@media (min-width: 640px) {
  .recommendation-drawer {
    left: auto;
    right: 16px;
    width: min(420px, calc(100vw - 32px));
  }
}
</style>
