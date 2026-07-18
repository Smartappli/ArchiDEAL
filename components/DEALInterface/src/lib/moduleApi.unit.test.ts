import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleRuntimeConfig } from "../config/moduleRegistry";
import { fetchModuleConnection } from "./moduleApi";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
    },
  });
}

function textResponse(payload: string, status = 200) {
  return new Response(payload, {
    status,
  });
}

function runtimeConfig(overrides: Partial<ModuleRuntimeConfig> = {}): ModuleRuntimeConfig {
  return {
    key: "dealiot",
    apiBaseUrl: "/dealiot",
    healthPath: "/healthz",
    docsPath: "/docs/dealiot",
    authToken: "local-management-token",
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
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchModuleConnection", () => {
  it("classifies probe payloads and only sends DEALIoT auth to /api probes", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ status: "ok", service: "management" }))
      .mockResolvedValueOnce(jsonResponse({ summary: { healthy: 2, unhealthy: 1 } }));

    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(runtimeConfig());

    expect(connection.status).toBe("degraded");
    expect(connection.probes).toMatchObject([
      {
        id: "management-console",
        url: "/dealiot/healthz",
        status: "online",
        httpStatus: 200,
        detail: "ok / management",
      },
      {
        id: "platform-components",
        url: "/dealiot/api/health",
        status: "degraded",
        httpStatus: 200,
        detail: "2 healthy, 1 unhealthy",
      },
    ]);

    const firstHeaders = fetchMock.mock.calls[0][1]?.headers as Headers;
    const secondHeaders = fetchMock.mock.calls[1][1]?.headers as Headers;

    expect(firstHeaders.get("Authorization")).toBeNull();
    expect(secondHeaders.get("Authorization")).toBe("Bearer local-management-token");
  });

  it("keeps DEALIoT online when required components are healthy and optional ones are absent", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ status: "ok", service: "management" }))
      .mockResolvedValueOnce(
        jsonResponse({
          summary: { healthy: 3 },
          checks: [
            { id: "vernemq", status: "healthy" },
            { id: "mqtt-kafka-bridge", status: "healthy" },
            { id: "kafka", status: "healthy" },
          ],
          optional_summary: { unreachable: 11 },
          optional_checks: [{ id: "airflow", status: "unreachable" }],
          scope: {
            required: ["vernemq", "mqtt-kafka-bridge", "kafka"],
            optional: ["airflow"],
            excluded: [],
          },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(runtimeConfig());

    expect(connection.status).toBe("online");
    expect(connection.probes[1]).toMatchObject({
      id: "platform-components",
      status: "online",
      detail: "3 healthy",
    });
  });

  it("degrades DEALIoT when a required component is unreachable", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ status: "ok", service: "management" }))
      .mockResolvedValueOnce(jsonResponse({ summary: { healthy: 2, unreachable: 1 } }));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(runtimeConfig());

    expect(connection.status).toBe("degraded");
    expect(connection.probes[1]).toMatchObject({
      id: "platform-components",
      status: "degraded",
      detail: "2 healthy, 1 unreachable",
    });
  });

  it("marks non-OK HTTP responses as attention", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(jsonResponse({ status: "down" }, 503));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        key: "dealhost",
        apiBaseUrl: "/dealhost",
        authToken: undefined,
        probes: [
          {
            id: "gateway",
            label: "Gateway API",
            path: "/api/gateway/health/",
          },
        ],
      }),
    );

    expect(connection.status).toBe("attention");
    expect(connection.probes[0]).toMatchObject({
      url: "/dealhost/api/gateway/health/",
      status: "attention",
      httpStatus: 503,
      detail: "down",
    });
  });

  it("reports authentication challenges as protected services, not offline services", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(textResponse("authentication required", 401))
      .mockResolvedValueOnce(textResponse("forbidden", 403));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          { id: "gateway", label: "Gateway API", path: "/gateway/health" },
          { id: "admin", label: "Admin API", path: "/admin/health" },
        ],
      }),
    );

    expect(connection.status).toBe("protected");
    expect(connection.probes).toMatchObject([
      { id: "gateway", status: "protected", httpStatus: 401, detail: "HTTP 401" },
      { id: "admin", status: "protected", httpStatus: 403, detail: "HTTP 403" },
    ]);
  });

  it("returns an offline probe result when the network request fails", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValueOnce(new Error("connection refused"));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          {
            id: "management-console",
            label: "Management console",
            path: "/healthz",
          },
        ],
      }),
    );

    expect(connection.status).toBe("attention");
    expect(connection.probes[0]).toMatchObject({
      status: "attention",
      detail: "connection refused",
    });
  });

  it("marks a runtime with no configured probes as attention", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [],
      }),
    );

    expect(connection).toMatchObject({
      moduleKey: "dealiot",
      status: "attention",
      probes: [],
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses relative probe paths and probe-specific base URLs", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        apiBaseUrl: "",
        authToken: undefined,
        probes: [
          {
            id: "relative",
            label: "Relative health",
            path: "healthz",
          },
          {
            id: "gps",
            label: "GPS health",
            baseUrl: "https://dealdata-gps.example.test/",
            path: "/health/ready/",
          },
        ],
      }),
    );

    expect(connection.status).toBe("online");
    expect(connection.probes).toMatchObject([
      {
        id: "relative",
        url: "healthz",
      },
      {
        id: "gps",
        url: "https://dealdata-gps.example.test/health/ready/",
      },
    ]);
  });

  it("summarizes text and empty JSON payloads with HTTP fallback details", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(textResponse("plain health response"))
      .mockResolvedValueOnce(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          {
            id: "text",
            label: "Text health",
            path: "/health/text",
          },
          {
            id: "empty-json",
            label: "Empty JSON health",
            path: "/health/json",
          },
        ],
      }),
    );

    expect(connection.status).toBe("online");
    expect(connection.probes).toMatchObject([
      {
        id: "text",
        status: "online",
        detail: "HTTP 200",
      },
      {
        id: "empty-json",
        status: "online",
        detail: "HTTP 200",
      },
    ]);
  });

  it("classifies database, summary, check and status payload variants", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ database: "unavailable" }))
      .mockResolvedValueOnce(jsonResponse({ summary: { unhealthy: 1 } }))
      .mockResolvedValueOnce(jsonResponse({ summary: { ok: 2, degraded: 1 } }))
      .mockResolvedValueOnce(jsonResponse({ checks: [{ status: "healthy" }, { status: "failed" }] }))
      .mockResolvedValueOnce(jsonResponse({ checks: [{ status: "ok" }, { status: "failed" }] }))
      .mockResolvedValueOnce(jsonResponse({ checks: [{ status: "available" }, { status: "failed" }] }))
      .mockResolvedValueOnce(jsonResponse({ checks: [{ status: "available" }] }))
      .mockResolvedValueOnce(jsonResponse({ status: "warning" }))
      .mockResolvedValueOnce(jsonResponse({ status: "failed" }));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          {
            id: "database",
            label: "Database",
            path: "/database",
          },
          {
            id: "summary-attention",
            label: "Summary attention",
            path: "/summary/attention",
          },
          {
            id: "summary-degraded",
            label: "Summary degraded",
            path: "/summary/degraded",
          },
          {
            id: "checks-healthy",
            label: "Checks healthy",
            path: "/checks/healthy",
          },
          {
            id: "checks-ok",
            label: "Checks ok",
            path: "/checks/ok",
          },
          {
            id: "checks-available",
            label: "Checks available",
            path: "/checks/available",
          },
          {
            id: "checks-online",
            label: "Checks online",
            path: "/checks/online",
          },
          {
            id: "warning",
            label: "Warning",
            path: "/warning",
          },
          {
            id: "failed",
            label: "Failed",
            path: "/failed",
          },
        ],
      }),
    );

    expect(connection.status).toBe("degraded");
    expect(connection.probes).toMatchObject([
      {
        id: "database",
        status: "attention",
        detail: "unavailable",
      },
      {
        id: "summary-attention",
        status: "attention",
        detail: "1 unhealthy",
      },
      {
        id: "summary-degraded",
        status: "degraded",
        detail: "2 ok, 1 degraded",
      },
      {
        id: "checks-healthy",
        status: "degraded",
      },
      {
        id: "checks-ok",
        status: "degraded",
      },
      {
        id: "checks-available",
        status: "degraded",
      },
      {
        id: "checks-online",
        status: "online",
      },
      {
        id: "warning",
        status: "degraded",
        detail: "warning",
      },
      {
        id: "failed",
        status: "attention",
        detail: "failed",
      },
    ]);
  });

  it("reports a generic detail for non-Error network failures", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValueOnce("socket reset");
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          {
            id: "management-console",
            label: "Management console",
            path: "/healthz",
          },
        ],
      }),
    );

    expect(connection.status).toBe("attention");
    expect(connection.probes[0]).toMatchObject({
      status: "attention",
      detail: "Unknown network error",
    });
  });
});
