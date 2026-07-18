import type { ModuleProbeConfig, ModuleRuntimeConfig } from "../config/moduleRegistry";
import type { ModuleConnection, ModuleProbeResult, ProbeStatus } from "../types";

const REQUEST_TIMEOUT_MS = 4_500;

function joinUrl(baseUrl: string, path: string) {
  if (!baseUrl) {
    return path;
  }

  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(record: Record<string, unknown>, key: string) {
  const value = record[key];

  return typeof value === "string" ? value : undefined;
}

function numberValue(record: Record<string, unknown>, key: string) {
  const value = record[key];

  return typeof value === "number" ? value : undefined;
}

function extractNumericSummary(payload: unknown) {
  if (!isRecord(payload) || !isRecord(payload.summary)) {
    return undefined;
  }

  const entries = Object.entries(payload.summary).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number",
  );

  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function countUnhealthyStatuses(summary: Record<string, unknown>) {
  const unhealthyKeys = [
    "error",
    "failed",
    "unhealthy",
    "unavailable",
    "unreachable",
    "unknown",
    "timeout",
    "degraded",
  ];

  return unhealthyKeys.reduce((total, key) => total + (numberValue(summary, key) ?? 0), 0);
}

function classifyPayload(payload: unknown, responseOk: boolean): ProbeStatus {
  if (!responseOk) {
    return "attention";
  }

  if (!isRecord(payload)) {
    return "online";
  }

  const database = stringValue(payload, "database")?.toLowerCase();
  if (database === "unavailable") {
    return "attention";
  }

  const summary = payload.summary;
  if (isRecord(summary)) {
    const unhealthyCount = countUnhealthyStatuses(summary);
    const healthyCount = numberValue(summary, "healthy") ?? numberValue(summary, "ok") ?? 0;

    if (unhealthyCount > 0) {
      return healthyCount > 0 ? "degraded" : "attention";
    }
  }

  const checks = payload.checks;
  if (Array.isArray(checks)) {
    const statuses = checks
      .filter(isRecord)
      .map((check) => stringValue(check, "status")?.toLowerCase())
      .filter(Boolean);

    if (statuses.some((status) => status !== "healthy" && status !== "ok" && status !== "available")) {
      return statuses.some((status) => status === "healthy" || status === "ok" || status === "available")
        ? "degraded"
        : "attention";
    }
  }

  const status = stringValue(payload, "status")?.toLowerCase();
  if (status && ["error", "failed", "unhealthy", "unavailable", "down"].includes(status)) {
    return "attention";
  }
  if (status && ["degraded", "warning"].includes(status)) {
    return "degraded";
  }

  return "online";
}

function classifyResponse(payload: unknown, response: Response): ProbeStatus {
  if (response.status === 401 || response.status === 403) {
    return "protected";
  }

  return classifyPayload(payload, response.ok);
}

function summarizePayload(payload: unknown, httpStatus: number) {
  if (!isRecord(payload)) {
    return `HTTP ${httpStatus}`;
  }

  const status = stringValue(payload, "status");
  const service = stringValue(payload, "service");
  const database = stringValue(payload, "database");
  const summary = payload.summary;

  if (isRecord(summary)) {
    const parts = Object.entries(summary).map(([key, value]) => `${value} ${key}`);

    if (parts.length > 0) {
      return parts.join(", ");
    }
  }

  return [status, service, database].filter(Boolean).join(" / ") || `HTTP ${httpStatus}`;
}

function overallStatus(probes: ModuleProbeResult[]): ProbeStatus {
  if (probes.length === 0) {
    return "attention";
  }
  if (probes.every((probe) => probe.status === "online")) {
    return "online";
  }
  if (probes.every((probe) => probe.status === "online" || probe.status === "protected")) {
    return "protected";
  }
  if (probes.some((probe) => probe.status === "online" || probe.status === "degraded")) {
    return "degraded";
  }

  return "attention";
}

async function parseResponse(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json() as Promise<unknown>;
  }

  return response.text();
}

async function fetchProbe(runtime: ModuleRuntimeConfig, probe: ModuleProbeConfig): Promise<ModuleProbeResult> {
  const url = joinUrl(probe.baseUrl ?? runtime.apiBaseUrl, probe.path);
  const checkedAt = new Date().toISOString();
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const startedAt = performance.now();

  try {
    const headers = new Headers({ Accept: "application/json, text/plain;q=0.9, */*;q=0.8" });
    if (runtime.authToken && probe.path.startsWith("/api/")) {
      headers.set("Authorization", `Bearer ${runtime.authToken}`);
    }

    const response = await fetch(url, {
      headers,
      signal: controller.signal,
    });
    const payload = await parseResponse(response);
    const responseTimeMs = Math.round(performance.now() - startedAt);
    const summary = extractNumericSummary(payload);

    return {
      id: probe.id,
      label: probe.label,
      url,
      status: classifyResponse(payload, response),
      httpStatus: response.status,
      responseTimeMs,
      detail: summarizePayload(payload, response.status),
      summary,
      checkedAt,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown network error";

    return {
      id: probe.id,
      label: probe.label,
      url,
      status: "attention",
      detail,
      checkedAt,
    };
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function fetchModuleConnection(runtime: ModuleRuntimeConfig): Promise<ModuleConnection> {
  const probes = await Promise.all(runtime.probes.map((probe) => fetchProbe(runtime, probe)));

  return {
    moduleKey: runtime.key,
    status: overallStatus(probes),
    checkedAt: new Date().toISOString(),
    probes,
  };
}
