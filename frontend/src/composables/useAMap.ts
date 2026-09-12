import { ref, shallowRef, onBeforeUnmount, type Ref } from "vue";
import { loadAMap, initMap, createOrderMarker, locateCurrentPosition } from "@/utils/amap";
import { showToast } from "vant";

/**
 * 橱窗地图生命周期与标记管理（自 Board.vue 拆出，P1-1）：
 * 初始化/销毁、订单标记渲染与高亮、当前定位。
 * 城市上下文/地理编码属于业务层，留在视图（通过 getMap 操作地图实例）。
 */
export function useAMap(options: {
  mapRef: Ref<HTMLDivElement | undefined>;
  containerId: string;
  /** 点击订单标记时回调（打开订单操作面板） */
  onMarkerClick: (order: any) => void;
}) {
  const locating = ref(false);
  // shallowRef：地图实例无需深层代理，且 AMap 对象不适合被 Vue 代理
  const mapInstance = shallowRef<any>(null);
  let markers: any[] = [];
  const markerByOrderId = new Map<number, any>();
  let highlightedMarker: any = null;
  let disposed = false;

  /** 确保地图已初始化并返回 AMap 命名空间；卸载后调用会抛错。 */
  async function ensureMap(): Promise<any> {
    const AMap = await loadAMap();
    if (disposed) {
      throw new Error("map disposed");
    }
    if (!mapInstance.value) {
      mapInstance.value = initMap(AMap, options.containerId);
      // 地图容器高度变化后强制重算尺寸
      setTimeout(() => {
        try {
          mapInstance.value?.resize?.();
        } catch {
          /* ignore */
        }
      }, 100);
    }
    return AMap;
  }

  function getMap(): any {
    return mapInstance.value;
  }

  function isReady(): boolean {
    return !!mapInstance.value;
  }

  function isDisposed(): boolean {
    return disposed;
  }

  async function renderMarkers(orders: any[], fitView = true) {
    const map = mapInstance.value;
    if (!map) return;
    const AMap = await loadAMap();
    // 清除旧标记
    markers.forEach((m) => map.remove(m));
    markers = [];
    markerByOrderId.clear();
    highlightedMarker = null;

    orders.forEach((order) => {
      const priceText = String(order.price_total || "");
      const unit = priceText.includes("小时") || priceText.includes("/h") ? "小时" : "次";
      const label = order.needs_manual_price ? "自带价" : `¥${order.base_price}/${unit}`;
      const marker = createOrderMarker(AMap, order.lng, order.lat, label, () =>
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

  /** 推荐卡点击：放大到楼栋级并高亮目标标记。返回是否成功定位。 */
  function focusOrder(order: any): boolean {
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
        highlightedMarker.getContent()?.classList.remove("order-marker--active");
      }
      try {
        marker.setzIndex(300);
      } catch {
        /* 同上 */
      }
      marker.getContent()?.classList.add("order-marker--active");
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
      showToast("定位失败，请允许浏览器使用位置信息");
    } finally {
      locating.value = false;
    }
  }

  /** 卸载时必须销毁地图：否则每次进板都泄漏一份 AMap.Map + marker 及其闭包 */
  function destroy() {
    disposed = true;
    const map = mapInstance.value;
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
