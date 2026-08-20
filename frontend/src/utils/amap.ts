import AMapLoader from "@amap/amap-jsapi-loader";

let AMapInstance: any = null;
let mapLoaded = false;

export async function loadAMap(): Promise<any> {
  if (AMapInstance) return AMapInstance;

  AMapInstance = await AMapLoader.load({
    key: import.meta.env.VITE_AMAP_KEY,
    version: import.meta.env.VITE_AMAP_VERSION || "2.0",
    plugins: [
      "AMap.Geocoder",
      "AMap.Marker",
      "AMap.Polygon",
      "AMap.CircleMarker",
    ],
  });
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
  AMap: any,
  lng: number,
  lat: number,
  label: string,
  onClick: () => void
) {
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
        background: #1a365d;
        color: white;
        padding: 5px 11px;
        border-radius: 16px;
        font-size: 13px;
        font-weight: 600;
        white-space: nowrap;
        box-shadow: 0 2px 8px rgba(26,54,93,0.28);
        border: 2px solid white;
      ">${label}</div>
      <div style="
        width: 14px;
        height: 14px;
        margin-top: -2px;
        background: #2563eb;
        border: 2px solid white;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        box-shadow: 0 2px 5px rgba(37,99,235,0.35);
      ">
        <span style="
          display: block;
          width: 4px;
          height: 4px;
          margin: 3px;
          border-radius: 999px;
          background: white;
        "></span>
      </div>
    </div>
  `;

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
  AMap: any,
  containerId: string,
  center: [number, number] = [104.065735, 30.659462],
  zoom = 12
) {
  const map = new AMap.Map(containerId, {
    zoom,
    center,
    resizeEnable: true,
    viewMode: "2D",
    mapStyle: "amap://styles/light",
  });

  // 添加定位控件
  map.plugin("AMap.Geolocation", () => {
    const geolocation = new AMap.Geolocation({
      enableHighAccuracy: true,
      timeout: 10000,
    });
    map.addControl(geolocation);
  });

  return map;
}
