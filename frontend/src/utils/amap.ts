import AMapLoader from "@amap/amap-jsapi-loader";

/** AMap 命名空间的值类型（官方类型包以全局 namespace 声明） */
export type AMapNamespace = typeof AMap;

let AMapInstance: AMapNamespace | null = null;
let mapLoaded = false;

export async function loadAMap(): Promise<AMapNamespace> {
  if (AMapInstance) return AMapInstance;

  // JSAPI 2.0 起瓦片服务强制校验安全密钥：未配置时地图初始化成功但底图灰屏
  //（点标等 canvas 覆盖层仍渲染）。配了 VITE_AMAP_SECURITY_CODE 就在脚本加载前挂上。
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE;
  if (securityCode) {
    (window as unknown as Record<string, unknown>)._AMapSecurityConfig = {
      securityJsCode: securityCode,
    };
  }

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
      // 轻薄版橱窗聚合图层（useAMap cluster 选项 opt-in，老 Board 不传不加载逻辑）
      "AMap.MarkerCluster",
    ],
  })) as AMapNamespace;
  mapLoaded = true;
  return AMapInstance;
}

export function isMapReady() {
  return mapLoaded;
}

/**
 * 订单图钉 DOM 工厂：普通 Marker 与聚合图层（MarkerCluster renderMarker）共用，
 * 保证两种渲染路径视觉完全一致。
 */
function buildOrderMarkerContent(label: string): HTMLDivElement {
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
        background: rgba(51,65,85,0.92);
        border: 1px solid white;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        box-shadow: 0 1px 4px rgba(51,65,85,0.3);
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
  return content;
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
  const content = buildOrderMarkerContent(label);

  const marker = new AMap.Marker({
    position: [lng, lat],
    content: content,
    offset: new AMap.Pixel(0, 0),
    zIndex: 100,
  });

  content.onclick = onClick;
  return marker;
}

/** 聚合图层数据点：坐标 + 图钉文案 + 点击回调 */
export interface ClusterPointData {
  lng: number;
  lat: number;
  label: string;
  /** 单次课酬（元）；自带价单为 null（不参与价格区间） */
  price: number | null;
  onClick: () => void;
}

/**
 * 聚合气泡价格区间文案：老师不放大就要能看到价。
 * 空集/全自带价 → "自带价"；单价相同 → "¥80"；区间 → "¥80–300"。
 */
export function clusterPriceRange(prices: Array<number | null>): string {
  const valid = prices.filter((p): p is number => typeof p === "number" && Number.isFinite(p) && p > 0);
  if (valid.length === 0) return "自带价";
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  return min === max ? `¥${min}` : `¥${min}–${max}`;
}

/** MarkerCluster 插件最小结构（官方类型包未覆盖该插件，运行时为 AMap.MarkerCluster） */
export interface OrderClusterLayer {
  setMap: (map: AMap.Map | null) => void;
}

interface ClusterMarkerLike {
  setContent: (content: HTMLDivElement) => void;
  setOffset: (offset: unknown) => void;
  getExtData?: () => unknown;
}

interface ClusterRenderContext {
  count: number;
  marker: ClusterMarkerLike & {
    getPosition?: () => { lng?: number; lat?: number; getLng?: () => number; getLat?: () => number } | undefined;
  };
  /** 高德不同小版本命名不一：data / clusterData / cluster.data 三选一 */
  data?: Array<ClusterDatum>;
  clusterData?: Array<ClusterDatum>;
  cluster?: { data?: Array<ClusterDatum> };
}

/** 聚合簇内数据点：extData 嵌套与顶层平铺两种形态都兼容（版本差异实测） */
interface ClusterDatum {
  lnglat?: [number, number];
  extData?: ClusterPointData;
  price?: number | null;
}

interface ClusterCtorLike {
  new (
    map: AMap.Map,
    points: Array<{ lnglat: [number, number]; extData: ClusterPointData }>,
    opts: {
      grid: number;
      renderClusterMarker: (context: ClusterRenderContext) => void;
      renderMarker: (context: ClusterRenderContext) => void;
    },
  ): OrderClusterLayer;
}

/**
 * 创建订单聚合图层（轻薄版橱窗专用，opt-in）。
 * 城市内订单经隐私粗化后常堆叠在同一坐标（±110m），普通逐点渲染视觉上
 * "少了一大半"——聚合在低缩放显示数字气泡（把堆叠的单变成看得见的数量），
 * 放大自动散开为与老版一致的图钉。
 */
export function createOrderCluster(
  AMap: AMapNamespace,
  map: AMap.Map,
  points: ClusterPointData[],
): OrderClusterLayer {
  const ClusterCtor = (AMap as unknown as { MarkerCluster: ClusterCtorLike }).MarkerCluster;
  const cluster = new ClusterCtor(
    map,
    // 价格/回调平铺到顶层 + extData 双写：高德各版本回读簇数据时形态不一
    //（嵌套丢失时顶层仍在，线上实测 extData 路径拿不到 price 的教训 2026-11-15）
    points.map((p) => ({ lnglat: [p.lng, p.lat] as [number, number], extData: p, ...p })),
    {
      // 粒度收窄：隐私粗化后坐标完全相同的单必然合并（距离 0 < 任何 grid），
      // 200px 会把同城区不同地址的单也并掉——老师看不到各自单价。60px 只并
      // 真堆叠点，不同地址的单在市级缩放就散开为带价的图钉
      grid: 60,
      renderClusterMarker: (context) => {
        const count = context.count;
        const data: Array<ClusterDatum> = context.clusterData ?? context.cluster?.data ?? [];
        // 单价区间直接上气泡：老师不放大就能比价（顶层平铺优先，extData 兜底）
        const priceText = clusterPriceRange(
          data.map((d) => {
            const top = typeof d?.price === "number" ? d.price : null;
            return top ?? d?.extData?.price ?? null;
          })
        );
        const div = document.createElement("div");
        div.className = "lite-cluster-bubble";
        div.innerHTML = `
          <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 3px 10px;
            border-radius: 12px;
            background: rgba(26, 54, 93, 0.88);
            border: 2px solid rgba(255, 255, 255, 0.92);
            color: white;
            font-size: 11px;
            line-height: 1.25;
            font-weight: 700;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(26,54,93,0.35);
            cursor: pointer;
          "><span class="lite-cluster-count"></span><span class="lite-cluster-price" style="font-size:10px;opacity:.92"></span></div>
        `;
        const countEl = div.querySelector(".lite-cluster-count");
        if (countEl) countEl.textContent = `${count} 单`;
        const priceEl = div.querySelector(".lite-cluster-price");
        if (priceEl) priceEl.textContent = priceText;
        // 点击聚合 → 放大散开（以簇内点均值为中心）
        const lngs = data.map((d) => Number(d.lnglat?.[0])).filter(Number.isFinite);
        const lats = data.map((d) => Number(d.lnglat?.[1])).filter(Number.isFinite);
        let center: [number, number];
        if (lngs.length > 0) {
          center = [
            lngs.reduce((a: number, b: number) => a + b, 0) / lngs.length,
            lats.reduce((a: number, b: number) => a + b, 0) / lats.length,
          ];
        } else {
          const c = map.getCenter() as unknown as { lng?: number; lat?: number };
          center = [Number(c.lng), Number(c.lat)];
        }
        div.onclick = () => {
          map.setZoomAndCenter(Math.min(map.getZoom() + 3, 18), center);
        };
        context.marker.setContent(div);
        context.marker.setOffset(new AMap.Pixel(0, 0));
      },
      renderMarker: (context) => {
        // 数据回读三重兜底仍失败（线上实测 2026-11-15：getExtData/上下文 data 各版本
        // 形态不一，label 全空）后的确定性方案：marker 坐标与闭包内 points 精确匹配——
        // lnglat 是我们传入的原始浮点（气泡定位正确已证明该路径可靠）
        let pos: [number, number] | undefined;
        const ctxData = context.data ?? context.clusterData ?? context.cluster?.data ?? [];
        if (ctxData[0]?.lnglat) {
          pos = [Number(ctxData[0].lnglat[0]), Number(ctxData[0].lnglat[1])];
        } else {
          const p = context.marker.getPosition?.() as
            | { lng?: number; lat?: number; getLng?: () => number; getLat?: () => number }
            | undefined;
          if (p) pos = [Number(p.getLng?.() ?? p.lng), Number(p.getLat?.() ?? p.lat)];
        }
        let point: ClusterPointData | undefined;
        if (pos && Number.isFinite(pos[0]) && Number.isFinite(pos[1])) {
          point = points.find((pt) => pt.lng === pos![0] && pt.lat === pos![1]);
        }
        if (!point) {
          // 坐标匹配失手（理论上不应发生）再走数据回读，最后才空标签
          const raw = (context.marker.getExtData?.() ?? {}) as { extData?: ClusterPointData };
          point = (ctxData[0]?.extData ?? (ctxData[0] as ClusterPointData | undefined) ?? raw.extData ?? raw) as
            | ClusterPointData
            | undefined;
        }
        const label = typeof point?.label === "string" ? point.label : "";
        const content = buildOrderMarkerContent(label);
        if (typeof point?.onClick === "function") {
          content.onclick = point.onClick;
        }
        context.marker.setContent(content);
        context.marker.setOffset(new AMap.Pixel(0, 0));
      },
    }
  );
  return cluster;
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
    // 底图样式默认标准彩色（normal 内置于 SDK，无远端样式拉取）；要浅灰 light 等
    // 可用 VITE_AMAP_STYLE 覆盖。2026-10-03 用户拍板回彩色——浅灰底抢不过价格图钉
    // 的"地图感"被否，且 normal 是老 Key 时代用户一直看到的样式（无迁移突兀感）
    mapStyle: import.meta.env.VITE_AMAP_STYLE || "amap://styles/normal",
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

/**
 * 定位到当前位置（GCJ02，convert: true）。
 *
 * @param options.noIpLocate 禁用 IP 定位兜底：浏览器定位失败时高德默认退回
 *   城市级 IP 定位——"附近 N 公里"这类精确锚点场景应开启（宁失败不凑数，
 *   失败由调用方走各自的兜底），常驻地选点等粗粒度场景保持默认。
 */
export function locateCurrentPosition(
  AMap: AMapNamespace,
  { noIpLocate = false }: { noIpLocate?: boolean } = {},
): Promise<[number, number]> {
  return new Promise((resolve, reject) => {
    const geolocation = new AMap.Geolocation({
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
      convert: true,
      noIpLocate,
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
