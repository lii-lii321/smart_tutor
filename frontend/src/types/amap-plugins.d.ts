/**
 * 高德 JSAPI 插件类型补齐。
 *
 * @amap/amap-jsapi-types 覆盖了 Map/Marker/Overlay 等，但未包含本项目用到的
 * Geolocation / Geocoder / Scale 插件。这里按实际用到的 API 面做最小声明，
 * 字段形态放宽（官方 SDK 回调结果在不同版本间存在对象/Getter 差异）。
 */
declare global {
  namespace AMap {
    interface GeolocationOptions {
      enableHighAccuracy?: boolean;
      timeout?: number;
      maximumAge?: number;
      convert?: boolean;
      showButton?: boolean;
      showMarker?: boolean;
      showCircle?: boolean;
      panToLocation?: boolean;
    }
    /** 定位结果坐标：兼容 {lng,lat} 对象与 getLng()/getLat() Getter 两种形态 */
    interface GeolocationPosition {
      lng?: number;
      lat?: number;
      getLng?: () => number;
      getLat?: () => number;
      [index: number]: unknown;
    }
    interface GeolocationResult {
      message?: string;
      position?: GeolocationPosition;
    }
    interface Geolocation {
      getCurrentPosition(callback: (status: string, result: GeolocationResult) => void): void;
    }
    interface GeolocationConstructor {
      new (options?: GeolocationOptions): Geolocation;
    }

    interface GeocoderOptions {
      city?: string;
    }
    interface GeocoderResult {
      geocodes?: Array<{ location?: string }>;
      regeocode?: {
        formattedAddress?: string;
        addressComponent?: { city?: string; province?: string; district?: string };
      };
    }
    interface Geocoder {
      getLocation(address: string, callback: (status: string, result: GeocoderResult) => void): void;
      getAddress(position: number[], callback: (status: string, result: GeocoderResult) => void): void;
    }
    interface GeocoderConstructor {
      new (options?: GeocoderOptions): Geocoder;
    }

    interface ScaleOptions {
      position?: string;
      offset?: Pixel;
    }
    type Scale = Control;
    interface ScaleConstructor {
      new (options?: ScaleOptions): Scale;
    }

    // 官方类型未声明这三个插件的构造器值，用 var 补齐（接口/构造器接口可安全合并）
    var Geolocation: GeolocationConstructor;
    var Geocoder: GeocoderConstructor;
    var Scale: ScaleConstructor;
  }
}

export {};
