import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const wsTarget = apiTarget.replace(/^http/i, "ws");

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/health": apiTarget,
        "/v1": {
          target: apiTarget,
          timeout: 600000,
          proxyTimeout: 600000,
        },
        "/api": "http://127.0.0.1:5000",
        "/debug": { target: wsTarget, ws: true },
      },
    },
  };
});
