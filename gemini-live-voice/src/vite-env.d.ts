/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GEMINI_API_KEY: string;
  readonly VITE_CLOUDFLARE_WORKER_URL: string;
  readonly VITE_GCP_GATEWAY_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
