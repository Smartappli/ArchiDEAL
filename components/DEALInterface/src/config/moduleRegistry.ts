import type { ModuleKey } from "../types";

export interface ModuleProbeConfig {
  id: string;
  label: string;
  baseUrl?: string;
  path: string;
}

export interface ModuleRuntimeConfig {
  key: ModuleKey;
  apiBaseUrl: string;
  healthPath: string;
  docsPath: string;
  authToken?: string;
  probes: ModuleProbeConfig[];
}

export const moduleRuntimeConfig: Record<ModuleKey, ModuleRuntimeConfig> = {
  dealhost: {
    key: "dealhost",
    apiBaseUrl: import.meta.env.VITE_DEALHOST_API_URL ?? "/dealhost",
    healthPath: "/api/gateway/health/",
    docsPath: "/docs/dealhost",
    probes: [
      {
        id: "gateway",
        label: "Gateway API",
        path: "/api/gateway/health/",
      },
    ],
  },
  dealiot: {
    key: "dealiot",
    apiBaseUrl: import.meta.env.VITE_DEALIOT_API_URL ?? "/dealiot",
    healthPath: "/healthz",
    docsPath: "/docs/dealiot",
    authToken: import.meta.env.VITE_DEALIOT_MANAGEMENT_TOKEN,
    probes: [
      {
        id: "management-console",
        label: "Management console",
        path: "/healthz",
      },
      {
        id: "platform-components",
        label: "Platform components",
        path: "/api/health",
      },
    ],
  },
  dealdata: {
    key: "dealdata",
    apiBaseUrl: import.meta.env.VITE_DEALDATA_API_URL ?? "/dealdata/core",
    healthPath: "/health/ready/",
    docsPath: "/docs/dealdata",
    probes: [
      {
        id: "core",
        label: "Core layer",
        baseUrl: import.meta.env.VITE_DEALDATA_CORE_API_URL ?? "/dealdata/core",
        path: "/health/ready/",
      },
      {
        id: "gps",
        label: "GPS layer",
        baseUrl: import.meta.env.VITE_DEALDATA_GPS_API_URL ?? "/dealdata/gps",
        path: "/health/ready/",
      },
      {
        id: "sensor",
        label: "Sensor layer",
        baseUrl: import.meta.env.VITE_DEALDATA_SENSOR_API_URL ?? "/dealdata/sensor",
        path: "/health/ready/",
      },
    ],
  },
};
