import type { ModuleProbeConfig, ModuleRuntimeConfig } from "../config/moduleRegistry";
import type { ModuleConnection, ModuleProbeResult, ProbeStatus } from "../types";

const REQUEST_TIMEOUT_MS = 4_500;
const HEALTH_STATUSES = new Set([
  "available",
  "degraded",
  "down",
  "error",
  "failed",
  "healthy",
  "ok",
  "unavailable",
  "unhealthy",
  "warning",
]);
const COMPONENT_STATUSES = new Set([
  "available",
  "degraded",
  "failed",
  "healthy",
  "ok",
  "timeout",
  "unavailable",
  "unhealthy",
  "unknown",
  "unreachable",
]);

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

function normalizedString(record: Record<string, unknown>, key: string) {
  return stringValue(record, key)?.trim().toLowerCase();
}

function validTimestamp(value: unknown) {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Date.parse(value));
}

function genericContractError(payload: Record<string, unknown>) {
  const status = normalizedString(payload, "status");
  if (status && HEALTH_STATUSES.has(status)) {
    return undefined;
  }

  const database = normalizedString(payload, "database");
  if (database === "available" || database === "unavailable") {
    return undefined;
  }

  if (isRecord(payload.summary)) {
    const values = Object.values(payload.summary);
    if (values.length > 0 && values.every((value) => typeof value === "number" && Number.isFinite(value))) {
      return undefined;
    }
  }

  if (
    Array.isArray(payload.checks) &&
    payload.checks.some(
      (check) => isRecord(check) && COMPONENT_STATUSES.has(normalizedString(check, "status") ?? ""),
    )
  ) {
    return undefined;
  }

  return "the JSON object contains no recognized health state";
}

function statusContractError(payload: Record<string, unknown>, probe: ModuleProbeConfig) {
  const contract = probe.healthContract;
  if (!contract || contract.kind !== "status") {
    return undefined;
  }

  const status = normalizedString(payload, "status");
  if (!status || !HEALTH_STATUSES.has(status)) {
    return "status is missing or invalid";
  }
  if (contract.expectedService && stringValue(payload, "service") !== contract.expectedService) {
    return `service must be ${contract.expectedService}`;
  }
  if (contract.requireCheckedAt && !validTimestamp(payload.checked_at)) {
    return "checked_at is missing or invalid";
  }

  for (const dependency of contract.requiredDependencies ?? []) {
    const dependencyStatus = normalizedString(payload, dependency);
    if (dependencyStatus !== "available" && dependencyStatus !== "unavailable") {
      return `${dependency} state is missing or invalid`;
    }
  }

  return undefined;
}

function componentSummaryContractError(payload: Record<string, unknown>) {
  if (!validTimestamp(payload.checked_at)) {
    return "checked_at is missing or invalid";
  }
  const summary = payload.summary;
  const checks = payload.checks;
  const scope = payload.scope;
  if (!isRecord(summary) || Object.keys(summary).length === 0) {
    return "summary is missing or empty";
  }
  if (!Array.isArray(checks) || checks.length === 0) {
    return "checks is missing or empty";
  }
  if (
    !isRecord(scope) ||
    !["required", "optional", "excluded"].every(
      (key) => Array.isArray(scope[key]) && scope[key].every((value) => typeof value === "string"),
    )
  ) {
    return "scope is missing or invalid";
  }

  const observedCounts: Record<string, number> = {};
  const checkIds = new Set<string>();
  for (const check of checks) {
    if (!isRecord(check) || typeof check.id !== "string" || check.id.trim() === "") {
      return "a component check has no valid id";
    }
    const checkId = check.id.trim();
    if (checkIds.has(checkId)) {
      return "component check ids must be unique";
    }
    checkIds.add(checkId);
    const status = normalizedString(check, "status");
    if (!status || !COMPONENT_STATUSES.has(status)) {
      return "a component check has an invalid status";
    }
    observedCounts[status] = (observedCounts[status] ?? 0) + 1;
  }

  const requiredIds = scope.required as string[];
  const requiredIdSet = new Set(requiredIds);
  if (
    requiredIds.length === 0 ||
    requiredIdSet.size !== requiredIds.length ||
    checkIds.size !== requiredIdSet.size ||
    [...checkIds].some((id) => !requiredIdSet.has(id))
  ) {
    return "component checks must match the required scope exactly";
  }

  for (const [status, count] of Object.entries(summary)) {
    if (!COMPONENT_STATUSES.has(status) || !Number.isInteger(count) || (count as number) < 0) {
      return "summary contains an invalid status count";
    }
    if (observedCounts[status] !== count) {
      return "summary does not match component checks";
    }
  }
  if (Object.keys(observedCounts).some((status) => summary[status] !== observedCounts[status])) {
    return "summary does not match component checks";
  }

  return undefined;
}

function contractError(payload: unknown, probe: ModuleProbeConfig) {
  if (!isRecord(payload)) {
    return "the response body is not a JSON object";
  }
  if (!probe.healthContract) {
    return genericContractError(payload);
  }
  if (probe.healthContract.kind === "component-summary") {
    return componentSummaryContractError(payload);
  }

  return statusContractError(payload, probe);
}

function classifyPayload(payload: unknown, responseOk: boolean, probe: ModuleProbeConfig): ProbeStatus {
  if (!responseOk) {
    return "attention";
  }

  if (!isRecord(payload)) {
    return "attention";
  }

  if (probe.healthContract?.kind === "status") {
    for (const dependency of probe.healthContract.requiredDependencies ?? []) {
      if (normalizedString(payload, dependency) !== "available") {
        return "attention";
      }
    }
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
  if (probes.every((probe) => probe.status === "protected")) {
    return "protected";
  }
  if (probes.some((probe) => probe.status === "online" || probe.status === "degraded")) {
    return "degraded";
  }

  return "attention";
}

type ParsedResponse =
  | { ok: true; payload: unknown }
  | { ok: false; error: string; validationIssue: "non-json" | "invalid-json" };

async function parseResponse(response: Response): Promise<ParsedResponse> {
  const contentType = response.headers.get("content-type") ?? "";
  const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();

  if (mediaType !== "application/json" && !mediaType.endsWith("+json")) {
    await response.text();
    return { ok: false, error: "Expected a JSON health response", validationIssue: "non-json" };
  }

  try {
    return { ok: true, payload: (await response.json()) as unknown };
  } catch {
    return { ok: false, error: "Invalid JSON health response", validationIssue: "invalid-json" };
  }
}

async function fetchProbe(runtime: ModuleRuntimeConfig, probe: ModuleProbeConfig): Promise<ModuleProbeResult> {
  const url = joinUrl(probe.baseUrl ?? runtime.apiBaseUrl, probe.path);
  const checkedAt = new Date().toISOString();
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const startedAt = performance.now();

  try {
    const headers = new Headers({ Accept: "application/json" });

    const response = await fetch(url, {
      credentials: "same-origin",
      headers,
      signal: controller.signal,
    });
    const responseTimeMs = Math.round(performance.now() - startedAt);
    if (response.status === 401 || response.status === 403) {
      return {
        id: probe.id,
        label: probe.label,
        url,
        status: "protected",
        httpStatus: response.status,
        responseTimeMs,
        detail: `HTTP ${response.status}`,
        checkedAt,
      };
    }

    const parsed = await parseResponse(response);
    if (!parsed.ok) {
      return {
        id: probe.id,
        label: probe.label,
        url,
        status: "attention",
        httpStatus: response.status,
        responseTimeMs,
        detail: parsed.error,
        validationIssue: parsed.validationIssue,
        checkedAt,
      };
    }

    const payload = parsed.payload;
    const summary = extractNumericSummary(payload);
    const validationError = response.ok ? contractError(payload, probe) : undefined;

    return {
      id: probe.id,
      label: probe.label,
      url,
      status: validationError ? "attention" : classifyPayload(payload, response.ok, probe),
      httpStatus: response.status,
      responseTimeMs,
      detail: validationError
        ? `Health contract not validated: ${validationError}`
        : summarizePayload(payload, response.status),
      validationIssue: validationError ? "contract" : undefined,
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
