import { ref, shallowRef, onBeforeUnmount, type Ref } from "vue";
import {
  loadAMap,
  initMap,
  createOrderMarker,
  createOrderCluster,
  locateCurrentPosition,
  type AMapNamespace,
  type OrderClusterLayer,
} from "@/utils/amap";
import type { PublicOrderBrief } from "@/api/types";
import { showToast } from "vant";

/**
 * 订单坐标有效性：中国境内粗框 + 排除 (0,0) 兜底值。
 * 导入链路已卡经纬度范围，但历史数据/地理编码失败仍可能产生无效点——
 * 这类单不上图钉（拖飞视野/掉海里），列表标「位置待定」。lite 与老版共用口径。
 */
export function isValidCoord(lng: number, lat: number): boolean {
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return false;
  if (lng === 0 && lat === 0) return false;
  return lng >= 73 && lng <= 136 && lat >= 3 && lat <= 54;
}

/**
 * 橱窗地图生命周期与标记管理（自 Board.vue 拆出，P1-1）：
 * 初始化/销毁、订单标记渲染与高亮、当前定位。
 * 城市上下文/地理编码属于业务层，留在视图（通过 getMap 操作地图实例）。
 *
 * cluster（可选，默认关）：聚合渲染模式——城市内隐私粗化坐标常堆叠在同点，
 * 聚合把堆叠单显示为数字气泡；老 Board 不传该选项，渲染路径逐字保持原样。
 */
export function useAMap(options: {
  mapRef: Ref<HTMLDivElement | undefined>;
  containerId: string;
  /** 点击订单标记时回调（打开订单操作面板） */
  onMarkerClick: (order: PublicOrderBrief) => void;
  /** 聚合模式（轻薄版 opt-in）：低缩放数字气泡，放大散开为图钉 */
  cluster?: boolean;
}) {
  const locating = ref(false);
  // shallowRef：地图实例无需深层代理，且 AMap 对象不适合被 Vue 代理
  const mapInstance = shallowRef<AMap.Map | null>(null);
  let markers: AMap.Marker[] = [];
  let clusterLayer: OrderClusterLayer | null = null;
  const markerByOrderId = new Map<number, AMap.Marker>();
  let highlightedMarker: AMap.Marker | null = null;
  let disposed = false;

  /** 确保地图已初始化并返回 AMap 命名空间；卸载后调用会抛错。 */
  async function ensureMap(): Promise<AMapNamespace> {
    const AMap = await loadAMap();
    if (disposed) {
      throw new Error("map disposed");
    }
    if (!mapInstance.value) {
      mapInstance.value = initMap(AMap, options.containerId);
    }
    return AMap;
  }

  function getMap(): AMap.Map | null {
    return mapInstance.value;
  }

  function isReady(): boolean {
    return !!mapInstance.value;
  }

  function isDisposed(): boolean {
    return disposed;
  }

  async function renderMarkers(orders: PublicOrderBrief[], fitView = true) {
    const map = mapInstance.value;
    if (!map) return;
    const AMap = await loadAMap();
    // 清除旧标记/聚合层
    markers.forEach((m) => map.remove(m));
    markers = [];
    markerByOrderId.clear();
    highlightedMarker = null;
    if (clusterLayer) {
      clusterLayer.setMap(null);
      clusterLayer = null;
    }

    const buildLabel = (order: PublicOrderBrief) => {
      const priceText = String(order.price_total || "");
      const unit = priceText.includes("小时") || priceText.includes("/h") ? "小时" : "次";
      return order.needs_manual_price ? "自带价" : `¥${order.base_price}/${unit}`;
    };

    if (options.cluster) {
      // 聚合模式：整层托管点位，不维护逐点 marker 映射（focusOrder 退化为纯定位）
      clusterLayer = createOrderCluster(
        AMap,
        map,
        orders.map((order) => ({
          lng: Number(order.lng),
          lat: Number(order.lat),
          label: buildLabel(order),
          onClick: () => options.onMarkerClick(order),
        }))
      );
      if (fitView && orders.length > 0) {
        fitMapToBounds(AMap, map, orders);
      }
      return;
    }

    orders.forEach((order) => {
      const marker = createOrderMarker(AMap, order.lng, order.lat, buildLabel(order), () =>
        options.onMarkerClick(order)
      );
      map.add(marker);
      markers.push(marker);
      markerByOrderId.set(order.id, marker);
    });

    // 自动适配视野
    if (fitView && orders.length > 0) {
      map.setFitView(markers);
    }
  }

  /** 聚合模式下 setFitView 不可用（点位由图层托管）：按有效点外包框适配视野 */
  function fitMapToBounds(AMap: AMapNamespace, map: AMap.Map, orders: PublicOrderBrief[]) {
    const valid = orders.filter((o) => isValidCoord(Number(o.lng), Number(o.lat)));
    if (valid.length === 0) return;
    const lngs = valid.map((o) => Number(o.lng));
    const lats = valid.map((o) => Number(o.lat));
    const bounds = new AMap.Bounds(
      [Math.min(...lngs), Math.min(...lats)],
      [Math.max(...lngs), Math.max(...lats)]
    );
    map.setBounds(bounds, false, [60, 60, 60, 60]);
  }

  /** 高亮/取消高亮都要动 Marker 的 DOM 内容：getContent 可能是字符串，先收窄 */
  function setMarkerActive(marker: AMap.Marker, active: boolean) {
    const content = marker.getContent();
    if (content instanceof HTMLElement) {
      content.classList.toggle("order-marker--active", active);
    }
  }

  /** 推荐卡点击/详情「在地图上查看」：放大到楼栋级并高亮目标标记（聚合模式下退化为纯定位）。 */
  function focusOrder(order: Pick<PublicOrderBrief, "id" | "lng" | "lat">): boolean {
    const lng = Number(order.lng);
    const lat = Number(order.lat);
    if (!mapInstance.value || !Number.isFinite(lng) || !Number.isFinite(lat)) {
      return false;
    }
    mapInstance.value.setZoomAndCenter(16, [lng, lat]);
    const marker = markerByOrderId.get(order.id);
    if (marker) {
      if (highlightedMarker) {
        try {
          highlightedMarker.setzIndex(100);
        } catch {
          /* 旧版本 API 兼容 */
        }
        setMarkerActive(highlightedMarker, false);
      }
      try {
        marker.setzIndex(300);
      } catch {
        /* 同上 */
      }
      setMarkerActive(marker, true);
      highlightedMarker = marker;
    }
    return true;
  }

  async function locateUser() {
    if (!mapInstance.value || locating.value) return;
    locating.value = true;
    try {
      const AMap = await loadAMap();
      const [lng, lat] = await locateCurrentPosition(AMap);
      mapInstance.value.setZoomAndCenter(15, [lng, lat]);
      showToast("已定位到当前位置");
    } catch {
      // 浏览器只在 HTTPS（或 localhost）开放定位 API：HTTP 访问时连权限弹窗都不会出现，
      // 提示语按真实原因区分，避免引导用户去找不存在的权限开关
      if (window.isSecureContext === false) {
        showToast("定位需 HTTPS 环境，正式部署后可用；可按城市手动找单");
      } else {
        showToast("定位失败，请检查浏览器定位权限或稍后再试");
      }
    } finally {
      locating.value = false;
    }
  }

  /** 卸载时必须销毁地图：否则每次进板都泄漏一份 AMap.Map + marker 及其闭包 */
  function destroy() {
    disposed = true;
    const map = mapInstance.value;
    if (clusterLayer) {
      clusterLayer.setMap(null);
      clusterLayer = null;
    }
    if (map && typeof map.destroy === "function") {
      try {
        map.destroy();
      } catch {
        /* 旧版本 SDK destroy 缺失时忽略 */
      }
    }
    mapInstance.value = null;
    markers = [];
    highlightedMarker = null;
  }

  onBeforeUnmount(destroy);

  return {
    locating,
    ensureMap,
    getMap,
    isReady,
    isDisposed,
    renderMarkers,
    focusOrder,
    locateUser,
    destroy,
  };
}
