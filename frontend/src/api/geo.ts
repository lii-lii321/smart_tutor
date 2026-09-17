import client from "./client";

export interface NearbyPoi {
  name: string;
  address: string;
  /** "城市·区"文本（如"成都·新都区"），点选后拼进常驻地 */
  area: string;
  lng: number;
  lat: number;
}

/**
 * 地理辅助：逆地理编码、附近 POI、关键字搜地点。
 * 走后端 REST 转发（Web服务 Key）——浏览器 JSAPI 的服务调用需要另一种 key 类型 + 安全密钥。
 */
export const geoApi = {
  reverseArea: (lng: number, lat: number) =>
    client
      .get<{ area: string }>("/geo/regeo", { params: { lng, lat } })
      .then((r) => r.data.area),

  nearbyPois: (lng: number, lat: number, radius = 1500) =>
    client
      .get<{ items: NearbyPoi[] }>("/geo/nearby-pois", { params: { lng, lat, radius } })
      .then((r) => r.data.items),

  /** 关键字搜地点。city 只用于提高相关性（可空）：多租户多城市产品下，
   *  调用方应从教员常驻地/当前城市推导（如 home_area 的"城市"前缀），
   *  不传时后端默认成都——仅为兜底，不应依赖。 */
  searchPois: (keywords: string, city?: string) =>
    client
      .get<{ items: NearbyPoi[] }>("/geo/search-pois", { params: { keywords, city: city || undefined } })
      .then((r) => r.data.items),
};
