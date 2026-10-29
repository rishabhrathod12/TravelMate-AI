/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL of the backend API. Leave it empty to use the same origin, which in
   * development is the Vite proxy. This value is visible in the browser, so it
   * must never hold a secret.
   */
  readonly VITE_API_BASE_URL?: string;
  /**
   * Development only. "session" opens real sessions on the backend (no audio, no voice service).
   * Anything else, or unset, uses the labelled mock. Ignored in a production build.
   */
  readonly VITE_VOICE_ADAPTER?: string;
}
