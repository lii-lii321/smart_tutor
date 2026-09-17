import AMapLoader from "@amap/amap-jsapi-loader";

/** AMap 命名空间的值类型（官方类型包以全局 namespace 声明） */
export type AMapNamespace = typeof AMap;

let AMapInstance: AMapNamespace | null = null;
let mapLoaded = false;

export async function loadAMap(): Promise<AMapNamespace> {
  if (AMapInstance) return AMapInstance;

  // loader 声明为 Promise<any>，显式断言以保留非空收窄
  AMapInstance = (await AMapLoader.load({
    key: import.meta.env.VITE_AMAP_KEY,
    version: import.meta.env.VITE_AMAP_VERSION || "2.0",
    plugins: [
      "AMap.Geocoder",
      "AMap.DistrictSearch",
      "AMap.Marker",
      "AMap.Polygon",
      "AMap.CircleMarker",
      "AMap.Scale",
      "AMap.Geolocation",
    ],
  })) as AMapNamespace;
  mapLoaded = true;
  return AMapInstance;
}

export function isMapReady() {
  return mapLoaded;
}

/**
 * 创建自定义图钉 Marker
 */
export function createOrderMarker(
  AMap: AMapNamespace,
  lng: number,
  lat: number,
  label: string,
  onClick: () => void
): AMap.Marker {
  const content = document.createElement("div");
  content.className = "order-marker";
  content.innerHTML = `
    <div style="
      transform: translate(-50%, -100%);
      display: flex;
      flex-direction: column;
      align-items: center;
      cursor: pointer;
    ">
      <div style="
        background: rgba(26, 54, 93, 0.78);
        color: white;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        white-space: nowrap;
        box-shadow: 0 1px 5px rgba(26,54,93,0.22);
        border: 1px solid rgba(255,255,255,0.88);
        backdrop-filter: blur(2px);
      "></div>
      <div style="
        width: 11px;
        height: 11px;
        margin-top: -1px;
        background: rgba(37,99,235,0.88);
        border: 1px solid white;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        box-shadow: 0 1px 4px rgba(37,99,235,0.3);
      ">
        <span style="
          display: block;
          width: 3px;
          height: 3px;
          margin: 2px;
          border-radius: 999px;
          background: white;
        "></span>
      </div>
    </div>
  `;
  // label 可能包含订单数据派生文本：textContent 注入，杜绝 innerHTML 拼接的存储型 XSS
  const labelEl = content.querySelector<HTMLDivElement>(
    ".order-marker > div > div:first-child"
  );
  if (labelEl) labelEl.textContent = label;

  const marker = new AMap.Marker({
    position: [lng, lat],
    content: content,
    offset: new AMap.Pixel(0, 0),
    zIndex: 100,
  });

  content.onclick = onClick;
  return marker;
}

/**
 * 初始化地图实例
 */
export function initMap(
  AMap: AMapNamespace,
  containerId: string,
  center: [number, number] = [104.065735, 30.659462],
  zoom = 12
): AMap.Map {
  const map = new AMap.Map(containerId, {
    zoom,
    center,
    viewMode: "2D",
    mapStyle: "amap://styles/light",
  });

  // 刻度尺放在推荐面板上方，便于判断订单之间的大致距离。
  // Scale 已在 loader plugins 中预载，直接挂控件即可
  map.addControl(
    new AMap.Scale({
      position: "LB",
      offset: new AMap.Pixel(16, 0),
    })
  );

  return map;
}

export function locateCurrentPosition(AMap: AMapNamespace): Promise<[number, number]> {
  return new Promise((resolve, reject) => {
    const geolocation = new AMap.Geolocation({
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
      convert: true,
      showButton: false,
      showMarker: false,
      showCircle: false,
      panToLocation: false,
    });
    const timer = window.setTimeout(() => reject(new Error("定位超时")), 12000);
    geolocation.getCurrentPosition((status: string, result: AMap.GeolocationResult) => {
      window.clearTimeout(timer);
      if (status !== "complete") {
        reject(new Error(result?.message || "定位失败"));
        return;
      }
      const position = result?.position;
      const lng = Number(position?.lng ?? position?.getLng?.() ?? position?.[0]);
      const lat = Number(position?.lat ?? position?.getLat?.() ?? position?.[1]);
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
        reject(new Error("定位结果无效"));
        return;
      }
      resolve([lng, lat]);
    });
  });
}
