/// <reference types="vite/client" />
/// <reference types="@amap/amap-jsapi-types" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, never>, Record<string, never>, Record<string, unknown>>;
  export default component;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
  readonly VITE_AMAP_KEY: string;
  /** 高德 Web 服务 key：REST 接口（行政区划/地理编码）专用，未配置时回退 VITE_AMAP_KEY */
  readonly VITE_AMAP_REST_KEY?: string;
  readonly VITE_AMAP_VERSION: string;
  /** 高德 JSAPI 2.0 安全密钥：2.0 起瓦片强制校验，缺配置则底图灰屏（仅点标渲染） */
  readonly VITE_AMAP_SECURITY_CODE?: string;
  /** 地图样式，默认 amap://styles/light；Key 矢量通道不可用时可设 normal 走栅格 */
  readonly VITE_AMAP_STYLE?: string;
  readonly VITE_SENTRY_DSN?: string;
  /** 无码访问根路径时兜底的默认橱窗邀请码；未配置时本地回退演示账号 tx886 */
  readonly VITE_DEFAULT_INVITE_CODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
