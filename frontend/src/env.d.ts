/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL of the backend API. Leave it empty to use the same origin, which in
   * development is the Vite proxy. This value is visible in the browser, so it
   * must never hold a secret.
   */
  readonly VITE_API_BASE_URL?: string;
}
