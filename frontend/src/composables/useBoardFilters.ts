import { computed, ref } from "vue";
import { loadAMap } from "@/utils/amap";
import type { PublicOrderBrief } from "@/api/types";
import { cityDistricts, nationwideRegions } from "@/data/regions";
import { showToast } from "vant";

export type EducationStage = "all" | "primary" | "junior" | "senior" | "other";

export const stageOptions: Array<{ value: EducationStage; label: string }> = [
  { value: "all", label: "全部" },
  { value: "primary", label: "小学" },
  { value: "junior", label: "初中" },
  { value: "senior", label: "高中" },
  { value: "other", label: "其他" },
];
export const subjectOptions = ["数学", "语文", "英语", "物理", "化学", "生物", "政治", "地理", "历史", "其他"];
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

/** 地址完全无法识别城市时的坐标兜底半径（公里） */
const CITY_MATCH_RADIUS_KM = 50;

/** 高德坐标的多形态兼容：数组 / {lng,lat} / Getter */
type AMapLngLatLike =
  | number[]
  | { lng?: number; lat?: number; getLng?: () => number; getLat?: () => number };

/**
 * 橱窗筛选项与城市归并逻辑（自 Board.vue 拆出）：
 * 学段/科目/城市三维筛选、区县→城市索引（静态表 + 高德行政区划运行时合并）、
 * 无城市地址的坐标半径兜底。纯逻辑，不含地图渲染副作用。
 */
export function useBoardFilters(options: {
  boardOrders: () => PublicOrderBrief[];
  /** 城市居中需要操作地图实例 */
  getMap: () => AMap.Map | null;
}) {
  const selectedStage = ref<EducationStage>("all");
  const selectedSubjects = ref<string[]>([]);
  const selectedCity = ref("all");
  const selectedCityCenter = ref<[number, number] | null>(null);
  const districtCityIndex = ref<Record<string, string>>(buildDistrictIndex());

  // 筛选面板（电商式弹层）：工具栏按钮 + 底部弹层，替代地图上的悬浮筛选胶囊
  const filterSheetVisible = ref(false);

  const availableSubjects = computed(() => {
    if (selectedStage.value === "all") {
      return subjectOptions;
    }
    return subjectsByStage[selectedStage.value];
  });

  const cityOptions = computed(() => {
    const cities = new Set([...nationwideRegions.flatMap((region) => region.cities), ...options.boardOrders().map(detectOrderCity)]);
    return [...cities].filter((city) => city !== "未标注城市").sort((left, right) => left.localeCompare(right, "zh-CN"));
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

  const activeFilterCount = computed(
    () =>
      (selectedStage.value !== "all" ? 1 : 0) +
      selectedSubjects.value.length +
      (selectedCity.value !== "all" ? 1 : 0)
  );

  const filteredOrders = computed(() => {
    return options.boardOrders().filter((order) => {
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

  function resetFilters() {
    selectedStage.value = "all";
    selectedSubjects.value = [];
    selectedCity.value = "all";
  }

  function normalizeText(value: unknown) {
    return String(value || "").replace(/\s+/g, "").toLowerCase();
  }

  function detectOrderCity(order: PublicOrderBrief) {
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

  function orderInSelectedCity(order: PublicOrderBrief) {
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

  function detectEducationStage(order: PublicOrderBrief): Exclude<EducationStage, "all"> {
    const text = normalizeText(order.grade_subject);
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

  function detectSubject(order: PublicOrderBrief) {
    const text = normalizeText(order.grade_subject);
    for (const subject of subjectOptions) {
      if (subject === "其他") continue;
      const aliases = subjectAliases[subject] || [subject];
      if (aliases.some((alias) => text.includes(alias.toLowerCase()))) {
        return subject;
      }
    }
    return "其他";
  }

  function toLngLat(location: unknown): [number, number] | null {
    const loc = location as AMapLngLatLike | null;
    const [lng, lat] = Array.isArray(loc)
      ? loc.map(Number)
      : [Number(loc?.lng ?? loc?.getLng?.()), Number(loc?.lat ?? loc?.getLat?.())];
    return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
  }

  // 拉取城市的中心点与下属区县名，用于坐标兜底和区县归并；失败时不缓存以便重试。
  const cityContextCache = new Map<string, { center: [number, number] | null; districts: string[] }>();

  async function fetchCityContext(city: string) {
    const cached = cityContextCache.get(city);
    if (cached) {
      return cached;
    }
    const context = { center: null as [number, number] | null, districts: [] as string[] };
    const cityName = formatCityName(city);
    try {
      // REST 调用与 JSAPI Loader 的 key 类型不通用：优先用独立的 Web 服务 key
      const key = import.meta.env.VITE_AMAP_REST_KEY || import.meta.env.VITE_AMAP_KEY;
      const response = await fetch(
        "https://restapi.amap.com/v3/config/district?keywords=" + encodeURIComponent(cityName) + "&subdistrict=1&key=" + encodeURIComponent(key)
      );
      const payload = (await response.json()) as {
        status?: string;
        districts?: Array<{ center?: string; districts?: Array<{ name?: string }> }>;
      };
      const top = payload?.districts?.[0];
      if (payload?.status === "1" && top) {
        context.center = toLngLat(String(top.center || "").split(","));
        context.districts = (top.districts || [])
          .map((item) => String(item?.name || ""))
          .filter(Boolean);
        cityContextCache.set(city, context);
      }
    } catch {
      // 高德 REST 查询不可用时保持空上下文，城市匹配退回静态区县表。
    }
    return context;
  }

  async function centerMapOnCity(city: string) {
    const map = options.getMap();
    if (!map || city === "all") return;

    await loadAMap();
    const cityName = formatCityName(city);
    const context = await fetchCityContext(city);
    if (context.center) {
      map.setZoomAndCenter(10, context.center);
      return;
    }

    await new Promise<void>((resolve) => {
      const timer = window.setTimeout(resolve, 3000);
      const geocoder = new AMap.Geocoder({ city: cityName });
      geocoder.getLocation(cityName, (status, result) => {
        window.clearTimeout(timer);
        // 地理编码最长 3s：期间用户切换城市后，慢返回不得把视图拽回旧城市
        if (selectedCity.value !== city) {
          resolve();
          return;
        }
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

  return {
    // 状态
    selectedStage,
    selectedSubjects,
    selectedCity,
    selectedCityCenter,
    filterSheetVisible,
    // 计算属性
    availableSubjects,
    cityOptions,
    activeCityLabel,
    hasActiveFilters,
    activeFilterCount,
    filteredOrders,
    // 方法
    resetFilters,
    fetchCityContext,
    centerMapOnCity,
    mergeCityContext,
  };
}
