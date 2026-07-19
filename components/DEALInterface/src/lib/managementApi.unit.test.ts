import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createDatasetResource,
  type Dataset,
  type Device,
  getDatasetPrincipals,
  listAllDatasetResources,
  ManagementApiError,
  listManagementResources,
  managementRequest,
  publishGatewayRoute,
  publishHostedApplicationVersion,
  provisionOidcIdentity,
  retireDeviceResource,
  updateDatasetResource,
  updateDeviceResource,
  updateHostedApplicationResource,
} from "./managementApi";

function jsonResponse(payload: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(status === 204 ? null : JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; Max-Age=0; path=/";
});

describe("managementRequest", () => {
  it("uses the same-origin session and strips bearer headers", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await managementRequest("/dealhost/api/hosting/applications/", {
      headers: { Authorization: "Bearer must-not-leave-browser-code" },
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.cache).toBe("no-store");
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

  it("forwards Django's same-origin CSRF cookie only on unsafe methods", async () => {
    document.cookie = "csrftoken=csrf%2Dtest%2Dvalue; path=/";
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await managementRequest("/dealhost/api/hosting/applications/", {
      method: "POST",
      body: "{}",
    });
    await managementRequest("/dealhost/api/hosting/applications/");

    expect(
      new Headers(fetchMock.mock.calls[0][1]?.headers).get("X-CSRFToken"),
    ).toBe("csrf-test-value");
    expect(
      new Headers(fetchMock.mock.calls[1][1]?.headers).has("X-CSRFToken"),
    ).toBe(false);
  });

  it("uses a strong device revision ETag for PATCH and unwraps the device envelope", async () => {
    const device: Device = {
      device_id: "barn:01",
      display_name: "Barn sensor",
      kind: "sensor",
      status: "active",
      revision: 7,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const updated = { ...device, display_name: "Barn north", revision: 8 };
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ device: updated }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateDeviceResource(device, {
      display_name: "Barn north",
      kind: "sensor",
      status: "active",
      mqtt_topic: "devices/barn-01/telemetry",
      capabilities: ["temperature"],
      settings: { sample_interval_seconds: 60 },
      labels: { site: "north" },
    })).resolves.toEqual(updated);

    expect(fetchMock).toHaveBeenCalledWith(
      "/dealiot/api/devices/barn%3A01",
      expect.objectContaining({ method: "PATCH" }),
    );
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("If-Match")).toBe('"7"');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      display_name: "Barn north",
      kind: "sensor",
      status: "active",
      mqtt_topic: "devices/barn-01/telemetry",
      capabilities: ["temperature"],
      settings: { sample_interval_seconds: 60 },
      labels: { site: "north" },
    });
  });

  it("loads every dataset catalog page and rejects cross-origin pagination links", async () => {
    const first: Dataset = {
      id: 1,
      name: "Telemetry",
      slug: "telemetry",
      description: "Telemetry data",
      enabled: true,
      revision: 1,
      updated_at: "2026-07-19T00:00:00Z",
    };
    const second: Dataset = {
      ...first,
      id: 2,
      name: "Operations",
      slug: "operations",
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        results: [first],
        next: "/dealhost/api/hosting/datasets/?page=2",
      }))
      .mockResolvedValueOnce(jsonResponse({ results: [second], next: null }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listAllDatasetResources()).resolves.toEqual([first, second]);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/dealhost/api/hosting/datasets/",
      "/dealhost/api/hosting/datasets/?page=2",
    ]);

    fetchMock.mockReset();
    fetchMock.mockResolvedValueOnce(jsonResponse({
      results: [first],
      next: "https://attacker.example/datasets?page=2",
    }));
    await expect(listAllDatasetResources()).rejects.toMatchObject({
      problem: { kind: "server", retryable: false },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockReset();
    fetchMock.mockResolvedValueOnce(jsonResponse({
      results: [first],
      next: "/dealhost/api/iam/users/?page=2",
    }));
    await expect(listAllDatasetResources()).rejects.toMatchObject({
      problem: { kind: "server", retryable: false },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not render a malformed management collection as an empty catalog", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listManagementResources("/api/resources")).rejects.toMatchObject({
      problem: { kind: "server", retryable: true },
    });
  });

  it("creates catalog metadata and updates a dataset with its strong revision ETag", async () => {
    const dataset: Dataset = {
      id: 8,
      name: "Telemetry",
      slug: "telemetry",
      description: "Telemetry data",
      enabled: true,
      revision: 4,
      updated_at: "2026-07-19T00:00:00Z",
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(dataset, 201))
      .mockResolvedValueOnce(jsonResponse({ ...dataset, name: "Telemetry curated", revision: 5 }));
    vi.stubGlobal("fetch", fetchMock);

    await createDatasetResource({
      name: "Telemetry",
      slug: "telemetry",
      description: "Telemetry data",
      enabled: true,
    });
    await updateDatasetResource(dataset, {
      name: "Telemetry curated",
      description: "Curated telemetry data",
      enabled: false,
    });

    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      name: "Telemetry",
      slug: "telemetry",
      description: "Telemetry data",
      enabled: true,
    });
    expect(fetchMock.mock.calls[1][1]?.method).toBe("PATCH");
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("If-Match")).toBe('"4"');
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      name: "Telemetry curated",
      description: "Curated telemetry data",
      enabled: false,
    });
  });

  it("uses the same strong ETag when retiring a device and rejects invalid revisions", async () => {
    const validDevice: Device = {
      device_id: "barn-01",
      display_name: "Barn sensor",
      kind: "sensor",
      status: "active",
      revision: 2,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({}, 204));
    vi.stubGlobal("fetch", fetchMock);

    await retireDeviceResource(validDevice);
    expect(fetchMock.mock.calls[0][1]?.method).toBe("DELETE");
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("If-Match")).toBe('"2"');

    expect(() => retireDeviceResource({ ...validDevice, revision: 0 })).toThrow(ManagementApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses the documented application, version and APISIX publication contracts", async () => {
    const application = {
      id: 4,
      name: "Field portal",
      slug: "field-portal",
      description: "Portal",
      current_version: "1.0.0",
      released_at: null,
      enabled: true,
      revision: 3,
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ ...application, name: "Field operations" }))
      .mockResolvedValueOnce(jsonResponse({
        id: 9,
        version: "1.1.0",
        notes: "Reviewed",
        source: "manual",
        created_at: "2026-07-19T00:00:00Z",
      }, 201))
      .mockResolvedValueOnce(jsonResponse({
        route_id: "module-field-portal",
        dry_run: true,
        etag: `"sha256-${"a".repeat(64)}"`,
        payload: { uris: ["/field", "/field/*"] },
      }, 201))
      .mockResolvedValueOnce(jsonResponse({
        id: 12,
        user_id: 6,
        acl_username: "oidc:a1b2",
        issuer: "https://identity.example/realms/field",
        subject: "operator-6",
        display_name: "Field operator",
        email: "operator@example.test",
        is_active: true,
        created: true,
        metadata_updated: false,
      }, 201));
    vi.stubGlobal("fetch", fetchMock);

    await updateHostedApplicationResource(application, {
      name: "Field operations",
      description: "Portal",
      enabled: true,
    });
    await publishHostedApplicationVersion(application, {
      version: "1.1.0",
      notes: "Reviewed",
      source: "manual",
    });
    await publishGatewayRoute("field-portal", true);
    await provisionOidcIdentity({
      issuer: "https://identity.example/realms/field",
      subject: "operator-6",
      display_name: "Field operator",
      email: "operator@example.test",
    });

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method])).toEqual([
      ["/dealhost/api/hosting/applications/4/", "PATCH"],
      ["/dealhost/api/hosting/applications/4/versions/", "POST"],
      ["/dealhost/api/gateway/apisix/publish/", "POST"],
      ["/dealhost/api/iam/oidc-identities/", "POST"],
    ]);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("If-Match")).toBe('"3"');
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("If-Match")).toBe('"3"');
    expect(() => updateHostedApplicationResource(
      { ...application, revision: 0 },
      { name: "Unsafe update", description: "Portal", enabled: true },
    )).toThrow(ManagementApiError);
    expect(() => publishHostedApplicationVersion(
      { ...application, revision: 0 },
      { version: "1.1.0", notes: "Unsafe", source: "manual" },
    )).toThrow(ManagementApiError);
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({
      module_slug: "field-portal",
      dry_run: true,
    });
  });

  it("binds APISIX publication to the exact strong ETag returned by preview", async () => {
    const previewEtag = `"sha256-${"c".repeat(64)}"`;
    const routeResult = {
      route_id: "module-field-portal",
      etag: previewEtag,
      payload: { uris: ["/field", "/field/*"] },
      response: null,
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ ...routeResult, dry_run: true }, 201, {
        ETag: previewEtag,
      }))
      .mockResolvedValueOnce(jsonResponse({ ...routeResult, dry_run: false }, 201, {
        ETag: previewEtag,
      }));
    vi.stubGlobal("fetch", fetchMock);

    const preview = await publishGatewayRoute("field-portal", true);
    await publishGatewayRoute("field-portal", false, preview.etag);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("If-Match")).toBe(
      previewEtag,
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      module_slug: "field-portal",
      dry_run: false,
    });
  });

  it("never sends an APISIX publication without one valid strong preview ETag", () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    expect(() => publishGatewayRoute("field-portal", false)).toThrow(
      ManagementApiError,
    );
    expect(() => publishGatewayRoute("field-portal", false, 'W/"weak"')).toThrow(
      ManagementApiError,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects absolute and protocol-relative management URLs", async () => {
    await expect(managementRequest("https://example.test/api")).rejects.toMatchObject({
      problem: { kind: "validation" },
    });
    await expect(managementRequest("//example.test/api")).rejects.toMatchObject({
      problem: { kind: "validation" },
    });
    await expect(managementRequest("/\\example.test/api")).rejects.toMatchObject({
      problem: { kind: "validation" },
    });
  });

  it.each([
    [401, "authentication"],
    [403, "authorization"],
    [400, "validation"],
    [409, "conflict"],
    [412, "conflict"],
    [428, "conflict"],
    [500, "server"],
  ] as const)("maps HTTP %s to %s", async (status, kind) => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "blocked" }, status)));

    await expect(managementRequest("/api/resource")).rejects.toMatchObject({
      problem: { kind, status, message: "blocked" },
    });
  });

  it("preserves validation fields and request ids", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { slug: ["Already exists."], detail: "Invalid input." },
          400,
          { "x-request-id": "request-123" },
        ),
      ),
    );

    try {
      await managementRequest("/api/resource");
      expect.fail("request should fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ManagementApiError);
      expect((error as ManagementApiError).problem).toMatchObject({
        fields: { slug: ["Already exists."] },
        requestId: "request-123",
      });
    }
  });

  it("shows field-level validation when the API omits a detail message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({
        name: ["This field may not be blank."],
        slug: ["Already exists."],
      }, 400)),
    );

    await expect(managementRequest("/api/resource")).rejects.toMatchObject({
      problem: {
        kind: "validation",
        message: "name: This field may not be blank.; slug: Already exists.",
      },
    });
  });

  it("supports empty responses and normalizes collection envelopes", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({}, 204))
      .mockResolvedValueOnce(jsonResponse({ results: [{ id: 1 }] }))
      .mockResolvedValueOnce(jsonResponse({ devices: [{ device_id: "cow-1" }] }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(managementRequest("/api/resource", { method: "DELETE" })).resolves.toBeUndefined();
    await expect(listManagementResources<{ id: number }>("/api/resources")).resolves.toEqual([{ id: 1 }]);
    await expect(listManagementResources<{ device_id: string }>("/api/devices")).resolves.toEqual([
      { device_id: "cow-1" },
    ]);
  });

  it("loads the minimal dataset-principals contract without IAM catalogs", async () => {
    const payload = {
      users: [
        {
          id: 4,
          label: "Chloé Operator",
          email: "chloe@example.test",
          is_active: true,
          identity_kind: "oidc" as const,
        },
      ],
      groups: [{ id: 2, name: "analysts" }],
      can_provision_oidc: false,
    };
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getDatasetPrincipals()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "/dealhost/api/hosting/dataset-principals/",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("times out a management request that never receives a response", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async (_input, init) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      })),
    );

    const assertion = expect(managementRequest("/api/slow")).rejects.toMatchObject({
      problem: { kind: "network", message: "The management API request timed out." },
    });
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
  });
});
