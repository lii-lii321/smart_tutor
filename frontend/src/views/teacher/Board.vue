<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useOrderStore } from "@/stores/order";
import { useAuthStore } from "@/stores/auth";
import { loadAMap, initMap, createOrderMarker, locateCurrentPosition } from "@/utils/amap";
import { publicApi } from "@/api/orders";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { cityDistricts, nationwideRegions } from "@/data/regions";
import { showToast, showLoadingToast, closeToast } from "vant";

const route = useRoute();
const router = useRouter();
const orderStore = useOrderStore();
const auth = useAuthStore();

const inviteCode = ref((route.params.inviteCode as string) || "tx886");
const mapRef = ref<HTMLDivElement>();
const agentPickerVisible = ref(false);
const agentFormVisible = ref(false);
const cityPickerVisible = ref(false);
const citySearch = ref("");
const selectedProvince = ref("");
const newInviteCode = ref("");
const addAgentError = ref("");
const savedAgents = ref<string[]>([]);
const selectedStage = ref<EducationStage>("all");
const selectedSubjects = ref<string[]>([]);
const selectedCity = ref("all");
const selectedCityCenter = ref<[number, number] | null>(null);
const districtCityIndex = ref<Record<string, string>>(buildDistrictIndex());
const cityContextCache = new Map<string, { center: [number, number] | null; districts: string[] }>();
const CITY_MATCH_RADIUS_KM = 50;
const recommendations = ref<any[]>([]);
const recLoading = ref(false);
const recommendationsExpanded = ref(true);
// 403 = 被该中介拉黑或平台限制：与“暂无推荐”区分开，给出明确文案
const recommendationsBlocked = ref(false);
const recommendationsBlockReason = ref("");
const locating = ref(false);
let map: any = null;
let markers: any[] = [];

const AGENT_STORAGE_KEY = "teacher_agent_invite_codes";
type EducationStage = "all" | "primary" | "junior" | "senior" | "other";

const stageOptions: Array<{ value: EducationStage; label: string }> = [
  { value: "all", label: "全部" },
  { value: "primary", label: "小学" },
  { value: "junior", label: "初中" },
  { value: "senior", label: "高中" },
  { value: "other", label: "其他" },
];
const subjectOptions = ["数学", "语文", "英语", "物理", "化学", "生物", "政治", "地理", "历史", "其他"];
const subjectsByStage: Record<Exclude<EducationStage, "all">, string[]> = {
  primary: subjectOptions,
  junior: subjectOptions,
  senior: subjectOptions,
  other: [],
};
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

const availableSubjects = computed(() => {
  if (selectedStage.value === "all") {
    return subjectOptions;
  }
  return subjectsByStage[selectedStage.value];
});

const provinceOptions = computed(() => nationwideRegions.map((region) => region.name));

const cityOptions = computed(() => {
  const cities = new Set([...nationwideRegions.flatMap((region) => region.cities), ...orderStore.boardOrders.map(detectOrderCity)]);
  return [...cities].filter((city) => city !== "未标注城市").sort((left, right) => left.localeCompare(right, "zh-CN"));
});

const selectedProvinceCities = computed(() => {
  return nationwideRegions.find((region) => region.name === selectedProvince.value)?.cities || [];
});

const visibleCityOptions = computed(() => {
  const keyword = normalizeText(citySearch.value);
  if (!keyword) return selectedProvinceCities.value;
  return selectedProvinceCities.value.filter((city) => normalizeText(formatCityName(city)).includes(keyword));
});

const activeCityLabel = computed(() => {
  if (selectedCity.value !== "all") {
    return formatCityName(selectedCity.value);
  }
  return cityOptions.value.length === 1 ? formatCityName(cityOptions.value[0]) : "全部城市";
});

const hasActiveFilters = computed(() =>
  selectedStage.value !== "all" || selectedSubjects.value.length > 0 || selectedCity.value !== "all"
);

const filteredOrders = computed(() => {
  return orderStore.boardOrders.filter((order) => {
    if (selectedCity.value !== "all" && !orderInSelectedCity(order)) {
      return false;
    }
    if (selectedStage.value !== "all" && detectEducationStage(order) !== selectedStage.value) {
      return false;
    }
    if (selectedSubjects.value.length === 0) {
      return true;
    }
    return selectedSubjects.value.includes(detectSubject(order));
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
  if (selectedCity.value !== "all" && !cityOptions.value.includes(selectedCity.value)) {
    selectedCity.value = "all";
  }
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
    recommendationsBlocked.value = false;
    return;
  }
  recLoading.value = true;
  try {
    const res = await publicApi.getRecommendations(inviteCode.value, 12);
    recommendations.value = res.items || [];
    recommendationsBlocked.value = false;
  } catch (e: any) {
    recommendations.value = [];
    if (e?.response?.status === 403) {
      recommendationsBlocked.value = true;
      recommendationsBlockReason.value =
        e?.response?.data?.detail || "该中介暂不向您开放订单推荐";
    } else {
      recommendationsBlocked.value = false;
    }
  } finally {
    recLoading.value = false;
  }
}

function focusRecommendation(order: any) {
  const lng = Number(order.lng);
  const lat = Number(order.lat);
  if (!map || !Number.isFinite(lng) || !Number.isFinite(lat)) {
    showToast("该订单暂未提供可定位的位置");
    return;
  }

  recommendationsExpanded.value = false;
  map.setZoomAndCenter(15, [lng, lat]);
}

function goOrder(order: any) {
  if (!auth.isLoggedIn) {
    goLogin();
    return;
  }
  router.push(`/teacher/orders/${order.id}`);
}

watch([selectedStage, selectedSubjects], async () => {
  if (!map) return;
  const AMap = await loadAMap();
  renderMarkers(AMap, filteredOrders.value, false);
});

watch(selectedCity, async (city) => {
  if (!map) return;
  const AMap = await loadAMap();
  if (city === "all") {
    selectedCityCenter.value = null;
    renderMarkers(AMap, filteredOrders.value, true);
    return;
  }
  const context = await fetchCityContext(city);
  if (selectedCity.value !== city) return;
  mergeCityContext(city, context.districts);
  selectedCityCenter.value = context.center;
  renderMarkers(AMap, filteredOrders.value, false);
  await centerMapOnCity(AMap, city);
});

function normalizeText(value: unknown) {
  return String(value || "").replace(/\s+/g, "").toLowerCase();
}

function detectOrderCity(order: any) {
  const address = String(order.fuzzy_address || "").replace(/\s+/g, "");
  const municipality = address.match(/^(北京市|天津市|上海市|重庆市)/);
  if (municipality) {
    return municipality[1];
  }
  const provincialCity = address.match(/(?:省|自治区|特别行政区)([\u4e00-\u9fa5]{2,4}市)/);
  if (provincialCity) {
    return provincialCity[1];
  }
  const city = address.match(/^([\u4e00-\u9fa5]{2,4}市)/);
  if (city) {
    return city[1];
  }
  return matchDistrictCity(address) || "未标注城市";
}

// 地址常缺少“xx市”前缀（如“武侯区xx小区”“彭州沃尔玛”），用区县索引归并到所属城市。
function matchDistrictCity(address: string) {
  let bestPosition = -1;
  let bestCity = "";
  for (const [name, city] of Object.entries(districtCityIndex.value)) {
    const position = address.indexOf(name);
    if (position === -1 || (bestPosition !== -1 && position >= bestPosition)) {
      continue;
    }
    bestPosition = position;
    bestCity = city;
  }
  return bestCity;
}

function orderInSelectedCity(order: any) {
  const city = detectOrderCity(order);
  if (city === selectedCity.value) {
    return true;
  }
  if (city !== "未标注城市") {
    return false;
  }
  // 地址完全无法识别城市时，按坐标落在选中城市中心一定范围内兜底。
  const center = selectedCityCenter.value;
  if (!center) {
    return false;
  }
  const lng = Number(order.lng);
  const lat = Number(order.lat);
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || (lng === 0 && lat === 0)) {
    return false;
  }
  return haversineKm(lat, lng, center[1], center[0]) <= CITY_MATCH_RADIUS_KM;
}

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLng = (lng2 - lng1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function appendDistrictNames(index: Record<string, string>, city: string, names: readonly string[]) {
  for (const name of [city, ...names]) {
    if (!name || name === "市辖区") continue;
    if (!(name in index)) {
      index[name] = city;
    }
    const stripped = name.replace(/(特别行政区|自治区|盟|旗|地区|区|县|市)$/, "");
    if (stripped.length >= 2 && !(stripped in index)) {
      index[stripped] = city;
    }
  }
}

function buildDistrictIndex() {
  const index: Record<string, string> = {};
  for (const [city, districts] of Object.entries(cityDistricts)) {
    appendDistrictNames(index, city, districts);
  }
  return index;
}

function mergeCityContext(city: string, districtNames: readonly string[]) {
  const next = { ...districtCityIndex.value };
  appendDistrictNames(next, city, districtNames);
  if (Object.keys(next).length !== Object.keys(districtCityIndex.value).length) {
    districtCityIndex.value = next;
  }
}

function formatCityName(city: string) {
  return city.replace(/市$/, "");
}

function formatProvinceName(province: string) {
  return province.replace(/壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区|省|市$/, "");
}

function detectEducationStage(order: any): Exclude<EducationStage, "all"> {
  const text = normalizeText(`${order.grade_subject || ""}${order.requirements || ""}${order.raw_text || ""}`);
  if (/高中|高[一二三123]|高考/.test(text)) {
    return "senior";
  }
  if (/初中|初[一二三123]|[七八九789]年级|中考/.test(text)) {
    return "junior";
  }
  if (/小学|小[一二三四五六123456]|[一二三四五六123456]年级/.test(text)) {
    return "primary";
  }
  return "other";
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

function selectStage(stage: EducationStage) {
  selectedStage.value = stage;
  selectedSubjects.value = [];
}

function toLngLat(location: unknown): [number, number] | null {
  const [lng, lat] = Array.isArray(location)
    ? location.map(Number)
    : [Number((location as any)?.lng ?? (location as any)?.getLng?.()), Number((location as any)?.lat ?? (location as any)?.getLat?.())];
  return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
}

// 拉取城市的中心点与下属区县名，用于坐标兜底和区县归并；失败时不缓存以便重试。
async function fetchCityContext(city: string) {
  const cached = cityContextCache.get(city);
  if (cached) {
    return cached;
  }
  const context = { center: null as [number, number] | null, districts: [] as string[] };
  const cityName = formatCityName(city);
  try {
    const key = import.meta.env.VITE_AMAP_KEY;
    const response = await fetch(
      "https://restapi.amap.com/v3/config/district?keywords=" + encodeURIComponent(cityName) + "&subdistrict=1&key=" + encodeURIComponent(key)
    );
    const payload = await response.json();
    const top = payload?.districts?.[0];
    if (payload?.status === "1" && top) {
      context.center = toLngLat(String(top.center || "").split(","));
      context.districts = (top.districts || []).map((item: any) => String(item?.name || "")).filter(Boolean);
      cityContextCache.set(city, context);
    }
  } catch {
    // 高德 REST 查询不可用时保持空上下文，城市匹配退回静态区县表。
  }
  return context;
}

async function centerMapOnCity(AMap: any, city: string) {
  if (!map || city === "all") return;

  const cityName = formatCityName(city);
  const context = await fetchCityContext(city);
  if (context.center) {
    map.setZoomAndCenter(10, context.center);
    return;
  }

  await new Promise<void>((resolve) => {
    const timer = window.setTimeout(resolve, 3000);
    const geocoder = new AMap.Geocoder({ city: cityName });
    geocoder.getLocation(cityName, (status: string, result: any) => {
      window.clearTimeout(timer);
      const lngLat = status === "complete" ? toLngLat(result?.geocodes?.[0]?.location) : null;
      if (lngLat) {
        context.center = lngLat;
        selectedCityCenter.value = lngLat;
        map.setZoomAndCenter(10, lngLat);
      } else {
        showToast("暂时无法定位该城市");
      }
      resolve();
    });
  });
}
function openCityPicker() {
  citySearch.value = "";
  selectedProvince.value = nationwideRegions.find((region) => region.cities.includes(selectedCity.value))?.name || "";
  cityPickerVisible.value = true;
}

function selectProvince(province: string) {
  selectedProvince.value = province;
  citySearch.value = "";
}

function selectCity(city: string) {
  selectedCity.value = city;
  citySearch.value = "";
  cityPickerVisible.value = false;
}

function renderMarkers(AMap: any, orders: any[], fitView = true) {
  // 清除旧标记
  markers.forEach((m) => map.remove(m));
  markers = [];

  if (orders.length === 0) {
    return;
  }

  orders.forEach((order) => {
    const priceText = String(order.price_total || "");
    const unit = priceText.includes("小时") || priceText.includes("/h") ? "小时" : "次";
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
  if (fitView && orders.length > 0) {
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
  router.push({
    path: "/teacher/login",
    query: { inviteCode: inviteCode.value, redirect: route.fullPath },
  });
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

async function locateUser() {
  if (!map || locating.value) return;
  locating.value = true;
  try {
    const AMap = await loadAMap();
    const [lng, lat] = await locateCurrentPosition(AMap);
    map.setZoomAndCenter(15, [lng, lat]);
    showToast("已定位到当前位置");
  } catch {
    showToast("定位失败，请允许浏览器使用位置信息");
  } finally {
    locating.value = false;
  }
}

async function addAgent() {
  const code = newInviteCode.value.trim();
  if (!code) {
    addAgentError.value = "请输入中介邀请码";
    return;
  }
  addAgentError.value = "";
  try {
    await loadBoardByInvite(code);
    newInviteCode.value = "";
    agentFormVisible.value = false;
    showToast("已添加并切换");
  } catch (e: any) {
    addAgentError.value = e?.response?.data?.detail || "中介不存在或邀请码无效";
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
            <van-icon name="exchange" size="18" />
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
          <button class="shrink-0 font-medium text-blue-600" @click="copyAgentWechat">
            复制
          </button>
        </div>
      </div>

      <!-- 地图 -->
      <div id="map-container" ref="mapRef" class="w-full h-full" />

      <!-- 分层筛选：先学段，再学科；工具栏带中介微信条时下移避免遮挡 -->
      <div class="absolute left-0 right-0 z-10 px-2" :style="{ top: orderStore.boardContactWechat ? '68px' : '42px' }">
        <div class="space-y-1 rounded-lg bg-white/95 p-1 shadow-sm backdrop-blur">
          <div class="flex gap-1 overflow-x-auto">
            <button
              v-for="stage in stageOptions"
              :key="stage.value"
              class="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-medium"
              :class="selectedStage === stage.value ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
              @click="selectStage(stage.value)"
            >
              {{ stage.label }}
            </button>
          </div>
          <div v-if="availableSubjects.length" class="flex gap-1 overflow-x-auto border-t border-slate-100 pt-1">
            <button
              class="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-medium"
              :class="selectedSubjects.length === 0 ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
              @click="clearSubjects"
            >
              全部学科
            </button>
            <button
              v-for="subject in availableSubjects"
              :key="subject"
              class="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-medium"
              :class="selectedSubjects.includes(subject) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'"
              @click="toggleSubject(subject)"
            >
              {{ subject }}
            </button>
          </div>
        </div>
      </div>

      <!-- 城市筛选 -->
      <button
        class="absolute left-2 top-[132px] z-10 inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white/95 px-2.5 text-xs font-medium text-slate-700 shadow-sm backdrop-blur"
        aria-label="选择城市"
        @click="openCityPicker"
      >
        <van-icon name="location-o" size="14" color="#2563eb" />
        <span>{{ activeCityLabel }}</span>
        <van-icon name="arrow-down" size="12" />
      </button>

      <!-- 地图底部快捷操作 -->
      <div class="absolute bottom-[88px] left-4 z-10 text-xs font-semibold text-[#1a365d] drop-shadow-[0_1px_1px_rgba(255,255,255,0.9)]">
        {{ hasActiveFilters ? "符合筛选" : "活跃订单" }} {{ filteredOrders.length }} 单
      </div>
      <div class="absolute bottom-[124px] right-4 z-10 flex flex-col gap-2">
        <button
          class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white text-[#1a365d] shadow-lg ring-1 ring-slate-200"
          aria-label="定位当前位置"
          :disabled="locating"
          @click="locateUser"
        >
          <van-loading v-if="locating" color="#2563eb" size="16" />
          <van-icon v-else name="location-o" size="18" color="#2563eb" />
        </button>
        <button
          class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#1a365d] text-white shadow-lg"
          aria-label="刷新地图"
          @click="loadBoardByInvite(inviteCode, false)"
        >
          <van-icon name="replay" size="16" />
        </button>
      </div>
    </div>

    <!-- 为你推荐（地图下方） -->
    <section class="recommendation-drawer fixed bottom-[72px] left-0 right-0 z-20 px-2">
      <div class="recommendation-handle mb-1 flex items-center justify-between rounded-xl bg-white/95 px-3 py-1 shadow-lg backdrop-blur" @click="recommendationsExpanded = !recommendationsExpanded">
        <button class="flex min-w-0 items-center gap-2 text-left" aria-label="展开或收起推荐订单">
          <van-icon :name="recommendationsExpanded ? 'arrow-down' : 'arrow-up'" size="16" color="#1e3558" />
          <h2 class="text-[15px] font-bold text-slate-900">为你推荐</h2>
          <span v-if="recommendations.length" class="text-[11px] text-slate-400">{{ recommendations.length }} 条</span>
        </button>
        <button class="flex items-center gap-1 text-[11px] text-primary-600" :disabled="recLoading" @click.stop="loadRecommendations">
          <van-icon name="replay" size="13" />
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

      <div
        v-else-if="recommendationsExpanded && recommendationsBlocked"
        class="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-center text-sm text-amber-700 shadow-sm"
      >
        <van-icon name="warning-o" class="mb-1" size="20" />
        <div>{{ recommendationsBlockReason }}</div>
        <div class="mt-1 text-xs text-amber-600/80">如有疑问请联系对应中介沟通。</div>
      </div>

      <div v-else-if="recommendationsExpanded && recommendations.length === 0" class="rounded-2xl bg-white p-5 text-center text-sm text-slate-400 shadow-sm">
        暂无推荐订单，去地图上看看
      </div>

      <div v-else-if="recommendationsExpanded" class="recommendation-list max-h-[54vh] space-y-3 overflow-y-auto pb-2">
        <div
          v-for="item in recommendations"
          :key="item.id"
          class="cursor-pointer rounded-2xl bg-white p-4 shadow-sm"
          @click="focusRecommendation(item)"
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

          <div class="relative mt-3 min-h-12 border-t border-slate-100 pt-3">
            <div class="pr-20 text-sm leading-5 text-slate-500">
              <template v-if="item.needs_manual_price">自带价 · 报价后可算</template>
              <template v-else>
                信息费
                <span class="font-bold text-primary-600">¥{{ item.calculated_info_fee }}</span>
                <span class="text-xs text-slate-400">
                  （定金¥{{ item.deposit_amount }} + 尾款¥{{ item.balance_amount }}）
                </span>
              </template>
            </div>
            <button
              class="absolute bottom-0 right-0 rounded-lg px-3 py-1.5 text-[11px] font-semibold"
              :class="item.already_applied ? 'bg-gray-100 text-gray-400' : 'header-gradient text-white'"
              :disabled="item.already_applied"
              @click.stop="goOrder(item)"
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
          <template v-if="sheetOrder.needs_manual_price">自带价 · 报价后可算</template>
          <template v-else>
            信息费
            <span class="text-primary-600 font-bold text-lg ml-2">¥{{ sheetOrder.calculated_info_fee }}</span>
            <div class="text-xs text-gray-400 mt-1">
              定金 ¥{{ sheetOrder.deposit_amount }} + 尾款 ¥{{ sheetOrder.balance_amount }}
            </div>
          </template>
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

    <!-- 城市选择 -->
    <van-popup v-model:show="cityPickerVisible" round position="bottom">
      <div class="max-h-[78vh] overflow-y-auto p-4">
        <div class="mb-3 text-base font-semibold text-slate-950">选择城市</div>
        <button
          class="mb-3 rounded-lg px-3 py-2 text-sm font-medium"
          :class="selectedCity === 'all' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'"
          @click="selectCity('all')"
        >
          全部城市
        </button>

        <template v-if="selectedProvince">
          <div class="mb-2 text-xs font-medium text-slate-500">{{ selectedProvince }} · 选择城市</div>
          <van-field v-model="citySearch" class="mb-3 rounded-lg bg-slate-50" placeholder="搜索城市" clearable />
          <button class="mb-3 rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700" @click="selectProvince('')">
            更换省份
          </button>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="city in visibleCityOptions"
              :key="city"
              class="rounded-lg px-3 py-2 text-sm font-medium"
              :class="selectedCity === city ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'"
              @click="selectCity(city)"
            >
              {{ formatCityName(city) }}
            </button>
          </div>
          <div v-if="visibleCityOptions.length === 0" class="mt-3 text-xs text-slate-400">
            没有匹配的城市
          </div>
        </template>
        <template v-else>
          <div class="mb-2 text-xs font-medium text-slate-500">先选择省份</div>
          <div class="grid grid-cols-4 gap-2">
            <button
              v-for="province in provinceOptions"
              :key="province"
              class="min-w-0 rounded-lg bg-slate-100 px-1.5 py-2 text-sm font-medium text-slate-700"
              @click="selectProvince(province)"
            >
              {{ formatProvinceName(province) }}
            </button>
          </div>
        </template>
      </div>
    </van-popup>
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
          @update:model-value="addAgentError = ''"
        />
        <div v-if="addAgentError" class="mt-2 rounded-lg bg-red-50 px-3 py-2 text-xs leading-5 text-red-600">
          {{ addAgentError }}
        </div>
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
