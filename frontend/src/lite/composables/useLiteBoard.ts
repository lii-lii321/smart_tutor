import { computed, ref } from "vue";
import type { PublicOrderBrief } from "@/api/types";
import { resolveInviteCode } from "@/utils/inviteCode";
import { useBoardFilters, type BoardSortMode, type EducationStage } from "@/composables/useBoardFilters";
import { isValidCoord } from "@/composables/useAMap";
import { nationwideRegions } from "@/data/regions";
import { liteApi, type LiteBoardResponse } from "@/lite/api";

/**
 * 轻薄版橱窗状态：board 拉取 + 筛选/排序（逻辑全复用 useBoardFilters）+
 * 距离装饰（免登录无推荐分，距离排序需要本地算 distance_km）+ 偏好持久化。
 */

/** 距离优先/课酬优先/最新发布：免登录没有推荐分，不提供「智能推荐」档 */
export const liteSortOptions: Array<{ value: BoardSortMode; label: string }> = [
  { value: "distance", label: "距离优先" },
  { value: "price", label: "课酬优先" },
  { value: "newest", label: "最新发布" },
];

/** lite 视图里的订单条目：board 数据 + 本地装饰的距离字段 */
export type LiteOrderItem = PublicOrderBrief & { distance_km?: number | null };

/** 订单是否有可上图钉的有效坐标（无效单列表标「位置待定」，地图不渲染） */
export function hasValidLocation(order: PublicOrderBrief): boolean {
  return isValidCoord(Number(order.lng), Number(order.lat));
}

const FILTER_STORAGE_KEY = "lite_filters_v1";

interface PersistedFilters {
  stage?: EducationStage;
  subjects?: string[];
  city?: string;
  sort?: BoardSortMode;
}

/** 读取持久化偏好；坏 JSON/非法值一律丢弃回默认，不让脏存储卡死页面 */
export function readPersistedFilters(): PersistedFilters | null {
  try {
    const raw = localStorage.getItem(FILTER_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedFilters;
    if (typeof parsed !== "object" || parsed === null) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function persistFilters(filters: PersistedFilters) {
  try {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
  } catch {
    // 隐私模式/存储满：偏好持久化失败不影响功能
  }
}

/** 距离装饰：免登录场景本地算 distance_km（参照点缺失时置 null 沉底）。纯函数，供单测 */
export function decorateWithDistance<T extends PublicOrderBrief>(
  orders: T[],
  refPoint: [number, number] | null,
): Array<T & { distance_km: number | null }> {
  if (!refPoint) {
    return orders.map((order) => ({ ...order, distance_km: null }));
  }
  const [lng, lat] = refPoint;
  return orders.map((order) => {
    const olng = Number(order.lng);
    const olat = Number(order.lat);
    if (!Number.isFinite(olng) || !Number.isFinite(olat) || (olng === 0 && olat === 0)) {
      return { ...order, distance_km: null };
    }
    return { ...order, distance_km: haversineKm(olat, olng, lat, lng) };
  });
}

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLng = (lng2 - lng1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) ** 2 * Math.cos(lat2 * rad) ** 2 * Math.sin(dLng / 2) ** 2;
  return Math.round(6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 10) / 10;
}

/** 邀请码解析：生产 /lite/{code} 路径 > ?inv= > hash（开发态 vite dev 会把 /lite/x 落回旧 SPA）> 通用兜底链 */
export function resolveLiteInviteCode(): string {
  const pathMatch = window.location.pathname.match(/^\/lite\/([A-Za-z0-9_-]{2,50})\/?$/);
  if (pathMatch) return pathMatch[1];
  const query = new URLSearchParams(window.location.search);
  const fromQuery = query.get("inv");
  if (fromQuery) return fromQuery.trim();
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash && /^[A-Za-z0-9_-]{2,50}$/.test(hash)) return hash;
  return resolveInviteCode();
}

export function useLiteBoard(options: { getMap: () => AMap.Map | null }) {
  const inviteCode = resolveLiteInviteCode();
  const board = ref<LiteBoardResponse | null>(null);
  const loading = ref(false);
  const loadError = ref(false);
  /** 最近一次成功拉取时间（HH:mm），列表页脚展示数据新鲜度 */
  const updatedAt = ref("");
  /** 距离参照点：浏览器定位成功才有 */
  const distanceRefPoint = ref<[number, number] | null>(null);
  const restored = readPersistedFilters();

  const decoratedOrders = computed(() => decorateWithDistance(board.value?.orders ?? [], distanceRefPoint.value));

  const filters = useBoardFilters({
    boardOrders: () => decoratedOrders.value,
    getMap: options.getMap,
  });

  // ── 省市级联：先省份后市，替代 300+ 城市一线滑 ──
  const selectedProvince = ref<string>("all");
  const provinceOptions = nationwideRegions.map((region) => region.name);
  /** 指定省份的城市列表；"all" 返回空（由调用方决定默认城市集） */
  function citiesForProvince(province: string): string[] {
    if (province === "all") return [];
    return [...(nationwideRegions.find((region) => region.name === province)?.cities ?? [])];
  }
  /** 从城市反推所属省份（持久化恢复用）；找不到（地址检测出的非常规城市）返回 all */
  function provinceOfCity(city: string): string {
    for (const region of nationwideRegions) {
      if (region.cities.includes(city)) return region.name;
    }
    return "all";
  }

  // 恢复持久化偏好（sortMode 默认最新发布，而非老橱窗的智能推荐——免登录无推荐分）
  if (restored) {
    if (restored.stage) filters.selectedStage.value = restored.stage;
    if (Array.isArray(restored.subjects)) filters.selectedSubjects.value = restored.subjects;
    if (restored.city) {
      filters.selectedCity.value = restored.city;
      selectedProvince.value = provinceOfCity(restored.city);
    }
    if (restored.sort && liteSortOptions.some((o) => o.value === restored.sort)) {
      filters.sortMode.value = restored.sort;
    }
  }

  const hasPersistedPrefs = !!restored;

  async function load() {
    loading.value = true;
    loadError.value = false;
    try {
      board.value = await liteApi.getBoard(inviteCode);
      updatedAt.value = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    } catch {
      loadError.value = true;
    } finally {
      loading.value = false;
    }
  }

  /** 筛选/排序变化时持久化（watch 由视图层接） */
  function saveFilters() {
    persistFilters({
      stage: filters.selectedStage.value,
      subjects: filters.selectedSubjects.value,
      city: filters.selectedCity.value,
      sort: filters.sortMode.value,
    });
  }

  return {
    inviteCode,
    board,
    loading,
    loadError,
    updatedAt,
    load,
    filters,
    decoratedOrders,
    distanceRefPoint,
    hasPersistedPrefs,
    saveFilters,
    selectedProvince,
    provinceOptions,
    citiesForProvince,
    provinceOfCity,
  };
}
