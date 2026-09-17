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

  searchPois: (keywords: string, city = "成都") =>
    client
      .get<{ items: NearbyPoi[] }>("/geo/search-pois", { params: { keywords, city } })
      .then((r) => r.data.items),
};
