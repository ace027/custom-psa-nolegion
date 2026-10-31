/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BRAND_NAME?: string;
  readonly VITE_BRAND_MARK?: string;
  readonly VITE_BRAND_LOGO_URL?: string;
  /** JSON object mapping existing theme colour token names to values. */
  readonly VITE_BRAND_COLORS?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
