import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/dealhost": {
          target: env.DEALHOST_PROXY_TARGET ?? "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dealhost/, ""),
        },
        "/dealiot": {
          target: env.DEALIOT_PROXY_TARGET ?? "http://127.0.0.1:8090",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dealiot/, ""),
        },
        "/dealdata/core": {
          target: env.DEALDATA_CORE_PROXY_TARGET ?? "http://127.0.0.1:7000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dealdata\/core/, ""),
        },
        "/dealdata/gps": {
          target: env.DEALDATA_GPS_PROXY_TARGET ?? "http://127.0.0.1:7001",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dealdata\/gps/, ""),
        },
        "/dealdata/sensor": {
          target: env.DEALDATA_SENSOR_PROXY_TARGET ?? "http://127.0.0.1:7002",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dealdata\/sensor/, ""),
        },
      },
    },
  };
});
