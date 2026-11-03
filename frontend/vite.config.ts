import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Development only. The backend is expected on port 8000; set BACKEND_PORT to use another port
// (for example when 8000 is taken), then start the backend with the same port.
// (`process` is read through globalThis because no Node type package is installed.)
const nodeEnv = (globalThis as { process?: { env: Record<string, string | undefined> } }).process
  ?.env;
const backend = `http://127.0.0.1:${nodeEnv?.BACKEND_PORT ?? "8000"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    // Development only: forwards the real endpoints to the backend so the browser needs no
    // CORS. Run the backend on port 8000 (see README). `/api` carries the voice-session
    // endpoints, which exist only when the backend is started with VOICE_ENABLED=true.
    proxy: {
      "/health": backend,
      "/api": backend,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
