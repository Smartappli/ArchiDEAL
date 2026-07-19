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
  it("classifies probe payloads and delegates authentication to the same-origin session", async () => {
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
    expect(secondHeaders.get("Authorization")).toBeNull();
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("same-origin");
    expect(fetchMock.mock.calls[1][1]?.credentials).toBe("same-origin");
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

  it("rejects 2xx text and empty JSON responses instead of reporting them healthy", async () => {
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

    expect(connection.status).toBe("attention");
    expect(connection.probes).toMatchObject([
      {
        id: "text",
        status: "attention",
        httpStatus: 200,
        detail: "Expected a JSON health response",
      },
      {
        id: "empty-json",
        status: "attention",
        httpStatus: 200,
        detail: "Health contract not validated: the JSON object contains no recognized health state",
      },
    ]);
  });

  it("rejects invalid JSON and payloads from a different backend contract", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response("<html>login</html>", {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          status: "ok",
          service: "not-the-gateway",
          database: "available",
          cache: "available",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        key: "dealhost",
        apiBaseUrl: "/dealhost",
        probes: [
          {
            id: "invalid-json",
            label: "Invalid JSON",
            path: "/invalid-json",
          },
          {
            id: "gateway",
            label: "Gateway API",
            path: "/api/gateway/health/",
            healthContract: {
              kind: "status",
              expectedService: "gateway",
              requiredDependencies: ["database", "cache"],
            },
          },
        ],
      }),
    );

    expect(connection.status).toBe("attention");
    expect(connection.probes).toMatchObject([
      { id: "invalid-json", status: "attention", httpStatus: 200, detail: "Invalid JSON health response" },
      {
        id: "gateway",
        status: "attention",
        httpStatus: 200,
        detail: "Health contract not validated: service must be gateway",
      },
    ]);
  });

  it("validates the configured gateway and readiness payload fields before reporting online", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "gateway", database: "available", cache: "available" }),
      )
      .mockResolvedValueOnce(jsonResponse({ status: "ok", service: "gps", database: "available" }));
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          {
            id: "gateway",
            label: "Gateway API",
            path: "/gateway",
            healthContract: {
              kind: "status",
              expectedService: "gateway",
              requiredDependencies: ["database", "cache"],
            },
          },
          {
            id: "gps",
            label: "GPS layer",
            path: "/gps",
            healthContract: {
              kind: "status",
              expectedService: "gps",
              requiredDependencies: ["database"],
            },
          },
        ],
      }),
    );

    expect(connection.status).toBe("online");
    expect(connection.probes).toMatchObject([
      { id: "gateway", status: "online" },
      { id: "gps", status: "online" },
    ]);
  });

  it("rejects component summaries with missing or duplicate required checks", async () => {
    const scope = {
      required: ["vernemq", "mqtt-kafka-bridge", "kafka"],
      optional: [],
      excluded: [],
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          checked_at: "2026-07-19T00:00:00Z",
          summary: { healthy: 2 },
          checks: [
            { id: "vernemq", status: "healthy" },
            { id: "kafka", status: "healthy" },
          ],
          scope,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          checked_at: "2026-07-19T00:00:00Z",
          summary: { healthy: 3 },
          checks: [
            { id: "vernemq", status: "healthy" },
            { id: "vernemq", status: "healthy" },
            { id: "kafka", status: "healthy" },
          ],
          scope,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const connection = await fetchModuleConnection(
      runtimeConfig({
        probes: [
          {
            id: "missing-required",
            label: "Missing required component",
            path: "/missing",
            healthContract: { kind: "component-summary" },
          },
          {
            id: "duplicate-required",
            label: "Duplicate required component",
            path: "/duplicate",
            healthContract: { kind: "component-summary" },
          },
        ],
      }),
    );

    expect(connection.status).toBe("attention");
    expect(connection.probes).toMatchObject([
      {
        id: "missing-required",
        status: "attention",
        validationIssue: "contract",
        detail: "Health contract not validated: component checks must match the required scope exactly",
      },
      {
        id: "duplicate-required",
        status: "attention",
        validationIssue: "contract",
        detail: "Health contract not validated: component check ids must be unique",
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
