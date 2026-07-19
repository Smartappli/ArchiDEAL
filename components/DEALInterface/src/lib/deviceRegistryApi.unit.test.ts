import { afterEach, describe, expect, it, vi } from "vitest";
import { listDeviceRegistryPage } from "./deviceRegistryApi";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listDeviceRegistryPage", () => {
  it("uses bounded server-side pagination and search", async () => {
    const device = {
      device_id: "barn-201",
      display_name: "Barn sensor",
      kind: "sensor",
      status: "active",
      revision: 3,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({
      devices: [device],
      next_cursor: "barn-201",
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listDeviceRegistryPage({
      cursor: "barn-100",
      limit: 100,
      query: "Barn north",
    })).resolves.toEqual({ devices: [device], nextCursor: "barn-201" });
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/dealiot/api/devices?limit=100&cursor=barn-100&q=Barn+north",
    );
  });

  it("fails closed for invalid limits and malformed pages", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listDeviceRegistryPage({ limit: 201 })).rejects.toMatchObject({
      problem: { kind: "validation", retryable: false },
    });
    expect(fetchMock).not.toHaveBeenCalled();

    await expect(listDeviceRegistryPage()).rejects.toMatchObject({
      problem: { kind: "server", retryable: true },
    });
  });
});
