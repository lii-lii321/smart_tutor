/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
  readonly VITE_AMAP_KEY: string;
  readonly VITE_AMAP_VERSION: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
