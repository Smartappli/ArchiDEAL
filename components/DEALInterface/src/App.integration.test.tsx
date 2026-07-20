import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type {
  Device,
  HostedApplication,
  RuntimeDeployment,
  RuntimeEnvironment,
  RuntimeOperation,
} from "./lib/managementApi";

const healthyPayloads: Record<string, unknown> = {
  "/dealhost/api/gateway/health/": {
    status: "ok",
    service: "gateway",
    database: "available",
    cache: "available",
  },
  "/dealiot/healthz": {
    status: "ok",
    checked_at: "2026-07-19T00:00:00Z",
  },
  "/dealiot/api/health": {
    checked_at: "2026-07-19T00:00:00Z",
    summary: {
      healthy: 3,
    },
    checks: [
      { id: "vernemq", status: "healthy" },
      { id: "mqtt-kafka-bridge", status: "healthy" },
      { id: "kafka", status: "healthy" },
    ],
    optional_summary: {},
    optional_checks: [],
    scope: {
      required: ["vernemq", "mqtt-kafka-bridge", "kafka"],
      optional: [],
      excluded: [],
    },
  },
  "/dealdata/core/health/ready/": {
    status: "ok",
    service: "core",
    database: "available",
  },
  "/dealdata/gps/health/ready/": {
    status: "ok",
    service: "gps",
    database: "available",
  },
  "/dealdata/sensor/health/ready/": {
    status: "ok",
    service: "sensor",
    database: "available",
  },
};

type MockPayload = unknown | Error | Response;

function jsonResponse(
  payload: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      ...headers,
    },
  });
}

function mockModuleFetch(overrides: Record<string, MockPayload | MockPayload[]> = {}) {
  const queuedOverrides = new Map(
    Object.entries(overrides).map(([url, payload]) => [url, Array.isArray(payload) ? [...payload] : [payload]]),
  );

  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    const overrideQueue = queuedOverrides.get(url);
    const payload =
      overrideQueue && overrideQueue.length > 0 ? overrideQueue.shift() : healthyPayloads[url] ?? { status: "ok" };

    if (payload instanceof Error) {
      throw payload;
    }
    if (payload instanceof Response) {
      return payload;
    }

    return jsonResponse(payload);
  });

  vi.stubGlobal("fetch", fetchMock);

  return fetchMock;
}

afterEach(() => {
  window.localStorage.clear();
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${window.location.search}`,
  );
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("App live module integrations", () => {
  it("probes DEALHost, DEALIoT and DEALData endpoints on initial render", async () => {
    const fetchMock = mockModuleFetch();

    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: /Manage DEALHost, DEALIoT and DEALData from one deliberate interface/i,
      }),
    ).toBeInTheDocument();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    expect(fetchMock).toHaveBeenCalledWith("/dealhost/api/gateway/health/", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/dealiot/healthz", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/dealiot/api/health", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/dealdata/core/health/ready/", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/dealdata/gps/health/ready/", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/dealdata/sensor/health/ready/", expect.any(Object));

    expect(await screen.findByText("/dealhost/api/gateway/health/")).toBeInTheDocument();
    expect(screen.getByText(/1\/1 healthy probes/)).toBeInTheDocument();
  });

  it("restores a canonical module deep link on initial render", async () => {
    const user = userEvent.setup();
    window.history.replaceState(window.history.state, "", "#/modules/dealiot/devices");
    const fetchMock = mockModuleFetch({
      "/dealiot/api/devices?limit=100": { devices: [] },
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "DEALIoT device operations" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Device configuration" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(window.location.hash).toBe("#/modules/dealiot/devices");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/dealiot/api/devices?limit=100", expect.any(Object)));

    await user.click(screen.getByRole("link", { name: "Skip to main content" }));
    expect(document.getElementById("main-content")).toHaveFocus();
    expect(window.location.hash).toBe("#/modules/dealiot/devices");
  });

  it("keeps module areas in URL history and restores them with back and forward", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch({
      "/dealiot/api/devices?limit=100": { devices: [] },
    });

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    const moduleNavigation = within(screen.getByLabelText("Module navigation"));
    await user.click(moduleNavigation.getByRole("button", { name: "DEALHost" }));
    expect(window.location.hash).toBe("#/modules/dealhost/deployments");

    await user.click(moduleNavigation.getByRole("button", { name: "DEALData" }));
    expect(window.location.hash).toBe("#/modules/dealdata/datasets");

    await user.click(moduleNavigation.getByRole("button", { name: "DEALIoT" }));
    expect(window.location.hash).toBe("#/modules/dealiot/devices");

    await user.click(screen.getByRole("button", { name: "Telemetry intake" }));
    expect(window.location.hash).toBe("#/modules/dealiot/telemetry");
    expect(screen.getByRole("button", { name: "Telemetry intake" })).toHaveAttribute("aria-current", "page");

    await act(async () => window.history.back());
    await waitFor(() => expect(window.location.hash).toBe("#/modules/dealiot/devices"));
    expect(screen.getByRole("button", { name: "Device configuration" })).toHaveAttribute("aria-current", "page");

    await act(async () => window.history.forward());
    await waitFor(() => expect(window.location.hash).toBe("#/modules/dealiot/telemetry"));
    expect(screen.getByRole("button", { name: "Telemetry intake" })).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "All modules" }));
    expect(window.location.hash).toBe("#/");
    expect(screen.getByRole("heading", {
      name: /Manage DEALHost, DEALIoT and DEALData from one deliberate interface/i,
    })).toBeInTheDocument();
  });

  it("fails safely to the canonical home route for an invalid hash", async () => {
    window.history.replaceState(window.history.state, "", "#/modules/dealiot/secrets");
    mockModuleFetch();

    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: /Manage DEALHost, DEALIoT and DEALData from one deliberate interface/i,
      }),
    ).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/"));
  });

  it("keeps the console usable and surfaces a failed module probe", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch({
      "/dealiot/api/health": new Error("dealiot API offline"),
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALIoT" }));

    expect(await screen.findByText("/dealiot/api/health")).toBeInTheDocument();
    expect(screen.getByText("dealiot API offline")).toBeInTheDocument();
    expect(screen.getByText("1/2 live probes healthy")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Connected module APIs" })).toBeInTheDocument();
  });

  it("refreshes live probes and updates the selected module status", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch({
      "/dealhost/api/gateway/health/": [
        healthyPayloads["/dealhost/api/gateway/health/"],
        {
          status: "down",
          service: "gateway",
          database: "available",
          cache: "available",
        },
      ],
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    expect(screen.getByText(/1\/1 healthy probes/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(12));

    expect(screen.getByText(/0\/1 healthy probes/)).toBeInTheDocument();
    expect(screen.getByText("down / gateway / available")).toBeInTheDocument();
    expect(screen.getAllByText("Action needed").length).toBeGreaterThan(0);
  });

  it("lets operators pivot from the queue to a module-specific control surface", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch();

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    const queue = screen.getByRole("region", { name: "Actions requiring decision" });
    await user.click(within(queue).getAllByRole("button", { name: "DEALData" })[0]);

    expect(screen.getByRole("heading", { name: "DEALData endpoints" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "DEALData operating model" })).toBeInTheDocument();
    expect(screen.getByText("3/3 live probes healthy")).toBeInTheDocument();
    expect(screen.getByText("Governed data platform")).toBeInTheDocument();
  });

  it("shows degraded DEALData probe details without blocking module navigation", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch({
      "/dealdata/sensor/health/ready/": {
        status: "warning",
        service: "sensor",
        database: "available",
      },
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALData" }));

    expect(await screen.findByText("/dealdata/sensor/health/ready/")).toBeInTheDocument();
    expect(screen.getByText("warning / sensor / available")).toBeInTheDocument();
    expect(screen.getByText("2/3 live probes healthy")).toBeInTheDocument();

    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALHost" }));

    expect(screen.getByText("/dealhost/api/gateway/health/")).toBeInTheDocument();
    expect(screen.getByText("1/1 live probes healthy")).toBeInTheDocument();
  });

  it("does not report a proxy or login HTML response as a healthy module", async () => {
    const fetchMock = mockModuleFetch({
      "/dealhost/api/gateway/health/": new Response("<html><title>Sign in</title></html>", {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8" },
      }),
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    expect(screen.getByText("The endpoint returned a non-JSON page; health is not validated.")).toBeInTheDocument();
    expect(screen.getByText(/0\/1 healthy probes/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /DEALHost control API DEALHost Action needed/ }),
    ).toBeInTheDocument();
  });

  it("offers every DEALWebsite language and persists the selected interface language", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch();

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    const languageSelect = screen.getByRole("combobox", { name: "Interface language" });
    const languageOptions = within(languageSelect).getAllByRole("option");

    expect(languageOptions.map((option) => option.getAttribute("value"))).toEqual([
      "en-US",
      "bg",
      "hr",
      "cs",
      "da",
      "nl",
      "et",
      "fi",
      "fr",
      "de",
      "el",
      "hu",
      "ga",
      "it",
      "lv",
      "lt",
      "mt",
      "pl",
      "pt",
      "ro",
      "sk",
      "sl",
      "es",
      "sv",
    ]);

    await user.selectOptions(languageSelect, "fr");

    expect(screen.getByRole("heading", { name: "Pilotez DEALHost, DEALIoT et DEALData depuis une interface unifiée." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rafraîchir" })).toBeInTheDocument();
    expect(screen.getAllByText("Télémétrie").length).toBeGreaterThan(0);
    expect(document.documentElement.lang).toBe("fr");
    expect(window.localStorage.getItem("dealinterface.language")).toBe("fr");
  });

  it("loads real management resources and creates a DEALIoT device", async () => {
    const user = userEvent.setup();
    const devices = [
      {
        device_id: "barn-01",
        display_name: "Barn sensor",
        kind: "environment",
        status: "active",
        revision: 3,
        created_at: "2026-07-19T00:00:00Z",
        updated_at: "2026-07-19T00:00:00Z",
      },
    ];
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url === "/dealiot/api/devices" && method === "POST") {
        const payload = JSON.parse(String(init?.body));
        devices.push({
          ...payload,
          revision: 1,
          created_at: "2026-07-19T00:01:00Z",
          updated_at: "2026-07-19T00:01:00Z",
        });
        return jsonResponse(devices.at(-1));
      }
      if (url === "/dealiot/api/devices?limit=100" && method === "GET") {
        return jsonResponse({ devices });
      }
      if (url === "/dealhost/api/hosting/applications/") {
        return jsonResponse([
          {
            id: 4,
            name: "Field portal",
            slug: "field-portal",
            description: "Portal",
            current_version: "1.4.0",
            released_at: "2026-07-19T00:00:00Z",
            enabled: true,
            revision: 1,
          },
        ]);
      }
      if (url === "/dealhost/api/hosting/datasets/") {
        return jsonResponse([
          {
            id: 8,
            name: "Telemetry curated",
            slug: "telemetry-curated",
            description: "Curated telemetry",
            enabled: true,
            revision: 1,
            updated_at: "2026-07-19T00:00:00Z",
            user_ids: [1],
            group_ids: [2],
          },
        ]);
      }

      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    const navigation = screen.getByLabelText("Module navigation");
    await user.click(within(navigation).getByRole("button", { name: "DEALIoT" }));
    expect(await screen.findByText("Barn sensor")).toBeInTheDocument();

    const createHeading = screen.getByRole("heading", { name: "Register a device" });
    const createForm = createHeading.closest("form");
    expect(createForm).not.toBeNull();
    const createQueries = within(createForm as HTMLFormElement);
    await user.type(createQueries.getByLabelText("Device identifier"), "pasture-02");
    await user.type(createQueries.getByLabelText("Display name"), "Pasture tracker");
    await user.type(createQueries.getByLabelText("Device type"), "gps");
    await user.click(createQueries.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Pasture tracker")).toBeInTheDocument();

    const devicePost = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealiot/api/devices" && init?.method === "POST",
    );
    expect(devicePost?.[1]?.credentials).toBe("same-origin");
    expect(new Headers(devicePost?.[1]?.headers).has("Authorization")).toBe(false);

    await user.click(within(navigation).getByRole("button", { name: "DEALHost" }));
    expect(await screen.findByText("Field portal")).toBeInTheDocument();
    expect(screen.getByText(/release metadata, not runtime deployment/i)).toBeInTheDocument();

    await user.click(within(navigation).getByRole("button", { name: "DEALData" }));
    expect(await screen.findByText("Telemetry curated")).toBeInTheDocument();
  });

  it("pages and searches the DEALIoT registry without loading every device", async () => {
    const user = userEvent.setup();
    const firstDevice: Device = {
      device_id: "device-001",
      display_name: "First pasture sensor",
      kind: "sensor",
      status: "active",
      revision: 1,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const secondDevice: Device = {
      ...firstDevice,
      device_id: "device-101",
      display_name: "Second pasture sensor",
    };
    const searchDevice: Device = {
      ...firstDevice,
      device_id: "north-007",
      display_name: "North yard tracker",
    };
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url === "/dealiot/api/devices?limit=100") {
        return jsonResponse({ devices: [firstDevice], next_cursor: "device-001" });
      }
      if (url === "/dealiot/api/devices?limit=100&cursor=device-001") {
        return jsonResponse({ devices: [secondDevice], next_cursor: null });
      }
      if (url === "/dealiot/api/devices?limit=100&q=North+yard") {
        return jsonResponse({ devices: [searchDevice], next_cursor: null });
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    await user.click(
      within(screen.getByLabelText("Module navigation")).getByRole("button", {
        name: "DEALIoT",
      }),
    );

    expect(await screen.findByText("First pasture sensor")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Second pasture sensor")).toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Find devices"), "North yard");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("North yard tracker")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain(
      "/dealiot/api/devices?limit=100&q=North+yard",
    );
  });

  it("loads minimal ACL principals and saves DEALData dataset access rights", async () => {
    const user = userEvent.setup();
    const dataset = {
      id: 8,
      name: "Telemetry curated",
      slug: "telemetry-curated",
      description: "Curated telemetry",
      enabled: true,
      revision: 4,
      updated_at: "2026-07-19T00:00:00Z",
      user_ids: [1],
      group_ids: [2],
    };
    const principals = {
      users: [
        { id: 1, label: "Alice", email: "alice@example.test", is_active: true, identity_kind: "local" },
        { id: 3, label: "Bob", email: "bob@example.test", is_active: true, identity_kind: "local" },
        {
          id: 5,
          label: "Chloé Operator",
          email: "chloe@example.test",
          is_active: true,
          identity_kind: "oidc",
        },
      ],
      groups: [
        { id: 2, name: "researchers" },
        { id: 4, name: "operators" },
      ],
      can_provision_oidc: true,
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/dealhost/api/hosting/datasets/8/" && init?.method === "PATCH") {
        return jsonResponse({ ...dataset, ...JSON.parse(String(init.body)) });
      }
      if (url === "/dealhost/api/hosting/datasets/") return jsonResponse([dataset]);
      if (url === "/dealhost/api/hosting/dataset-principals/") return jsonResponse(principals);
      if (url === "/dealhost/api/iam/oidc-identities/" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        principals.users.push({
          id: 6,
          label: payload.display_name || payload.email || "OIDC identity 6",
          email: payload.email,
          is_active: true,
          identity_kind: "oidc",
        });
        return jsonResponse({
          id: 10,
          user_id: 6,
          acl_username: "oidc:91e02c4a",
          ...payload,
          is_active: true,
          created: true,
          metadata_updated: false,
        });
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    const navigation = screen.getByLabelText("Module navigation");
    await user.click(within(navigation).getByRole("button", { name: "DEALData" }));
    await user.click(screen.getByRole("button", { name: "Catalog visibility" }));

    const bob = await screen.findByRole("checkbox", { name: /Bob — bob@example.test/ });
    expect(screen.getByRole("checkbox", { name: "Chloé Operator — chloe@example.test" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Approved OIDC issuer"), "https://identity.example/realms/field");
    await user.type(screen.getByLabelText("Stable subject (sub)"), "nora-6");
    await user.type(screen.getByLabelText("Human-readable name"), "Nora Analyst");
    await user.type(screen.getByLabelText("Email (optional)"), "nora@example.test");
    await user.click(screen.getByRole("button", { name: "Provision OIDC identity" }));
    expect(await screen.findByText(/OIDC identity provisioned/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Nora Analyst — nora@example.test" })).toBeInTheDocument();
    const provisionCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/iam/oidc-identities/" && init?.method === "POST",
    );
    expect(JSON.parse(String(provisionCall?.[1]?.body))).toEqual({
      issuer: "https://identity.example/realms/field",
      subject: "nora-6",
      display_name: "Nora Analyst",
      email: "nora@example.test",
    });
    const operators = screen.getByRole("checkbox", { name: "operators" });
    await user.click(bob);
    await user.click(operators);
    await user.click(screen.getByRole("button", { name: "Save catalog visibility" }));

    await waitFor(() => expect(screen.getByText("Catalog visibility saved.")).toBeInTheDocument());
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/datasets/8/" && init?.method === "PATCH",
    );
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({ user_ids: [1, 3], group_ids: [2, 4] });
    expect(new Headers(patchCall?.[1]?.headers).get("If-Match")).toBe('"4"');
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/dealhost/api/iam/users/")).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/dealhost/api/iam/groups/")).toBe(false);
  });

  it("lets staff edit ACLs without exposing superuser-only OIDC provisioning", async () => {
    const user = userEvent.setup();
    const dataset = {
      id: 9,
      name: "Operations",
      slug: "operations",
      description: "Operations data",
      enabled: true,
      revision: 2,
      updated_at: "2026-07-19T00:00:00Z",
      user_ids: [],
      group_ids: [],
    };
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url === "/dealhost/api/hosting/datasets/") return jsonResponse([dataset]);
      if (url === "/dealhost/api/hosting/dataset-principals/") {
        return jsonResponse({
          users: [
            { id: 7, label: "Staff assignable", email: "staff@example.test", is_active: true, identity_kind: "local" },
          ],
          groups: [{ id: 5, name: "dataset-readers" }],
          can_provision_oidc: false,
        });
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALData" }));
    await user.click(screen.getByRole("button", { name: "Catalog visibility" }));

    expect(await screen.findByText("OIDC provisioning restricted")).toBeInTheDocument();
    expect(screen.queryByLabelText("Approved OIDC issuer")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Staff assignable — staff@example.test" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "dataset-readers" })).toBeInTheDocument();
  });

  it("updates and retires a selected DEALIoT device with its strong ETag", async () => {
    const user = userEvent.setup();
    let device: Device = {
      device_id: "barn-01",
      display_name: "Barn sensor",
      kind: "environment",
      status: "active",
      mqtt_topic: "devices/barn-01/telemetry",
      revision: 3,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/dealiot/api/devices?limit=100" && method === "GET") {
        return jsonResponse({ devices: device.status === "retired" ? [] : [device] });
      }
      if (url === "/dealiot/api/devices/barn-01" && method === "PATCH") {
        device = {
          ...device,
          ...JSON.parse(String(init?.body)),
          revision: 4,
          updated_at: "2026-07-19T00:01:00Z",
        };
        return jsonResponse({ device });
      }
      if (url === "/dealiot/api/devices/barn-01" && method === "DELETE") {
        device = {
          ...device,
          status: "retired",
          revision: 5,
          updated_at: "2026-07-19T00:02:00Z",
        };
        return new Response(null, { status: 204, headers: { ETag: '"5"' } });
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALIoT" }));

    const editorHeading = await screen.findByRole("heading", { name: "Edit device" });
    const editor = editorHeading.closest("form");
    expect(editor).not.toBeNull();
    const editorQueries = within(editor as HTMLFormElement);
    await user.clear(editorQueries.getByLabelText("Display name"));
    await user.type(editorQueries.getByLabelText("Display name"), "Barn north");
    await user.clear(editorQueries.getByLabelText("Device type"));
    await user.type(editorQueries.getByLabelText("Device type"), "sensor");
    await user.selectOptions(editorQueries.getByLabelText("Lifecycle status"), "suspended");
    await user.clear(editorQueries.getByLabelText("MQTT telemetry topic"));
    await user.type(editorQueries.getByLabelText("MQTT telemetry topic"), "devices/barn-north/telemetry");
    await user.type(editorQueries.getByLabelText("Capabilities (comma-separated)"), "temperature, humidity");
    fireEvent.change(editorQueries.getByLabelText("Non-secret settings (JSON object)"), {
      target: { value: '{"sample_interval_seconds":60}' },
    });
    fireEvent.change(editorQueries.getByLabelText("Labels (JSON object)"), {
      target: { value: '{"site":"north"}' },
    });
    await user.click(editorQueries.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Device configuration saved.")).toBeInTheDocument();
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealiot/api/devices/barn-01" && init?.method === "PATCH",
    );
    expect(new Headers(patchCall?.[1]?.headers).get("If-Match")).toBe('"3"');
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      display_name: "Barn north",
      kind: "sensor",
      status: "suspended",
      mqtt_topic: "devices/barn-north/telemetry",
      capabilities: ["temperature", "humidity"],
      settings: { sample_interval_seconds: 60 },
      labels: { site: "north" },
    });

    await user.click(screen.getByRole("button", { name: "Retire device" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Barn north"));
    expect(await screen.findByText("Device retired.")).toBeInTheDocument();
    expect(await screen.findByText("No resource yet")).toBeInTheDocument();
    const deleteCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealiot/api/devices/barn-01" && init?.method === "DELETE",
    );
    expect(new Headers(deleteCall?.[1]?.headers).get("If-Match")).toBe('"4"');
  });

  it("edits application metadata, records a version, and publishes an APISIX route only after preview", async () => {
    const user = userEvent.setup();
    let application: HostedApplication = {
      id: 4,
      name: "Field portal",
      slug: "field-portal",
      description: "Portal",
      current_version: "1.4.0",
      released_at: "2026-07-19T00:00:00Z",
      enabled: true,
      revision: 1,
      versions: [],
    };
    const modules = [
      {
        id: 2,
        name: "Field portal gateway",
        slug: "field-portal",
        public_path: "/field",
        deployment_target: "docker-compose",
        upstream_host: "field-portal",
        upstream_port: 8080,
        enabled: true,
      },
      {
        id: 3,
        name: "Internal worker",
        slug: "internal-worker",
        public_path: "",
        deployment_target: "worker",
        enabled: false,
      },
      {
        id: 4,
        name: "Other portal gateway",
        slug: "other-portal",
        public_path: "/other",
        deployment_target: "docker-compose",
        upstream_host: "other-portal",
        upstream_port: 8080,
        enabled: true,
      },
    ];
    let routePublicationAttempts = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/dealhost/api/hosting/applications/" && method === "GET") {
        return jsonResponse([application]);
      }
      if (url === "/dealhost/api/hosting/applications/4/" && method === "PATCH") {
        application = {
          ...application,
          ...JSON.parse(String(init?.body)),
          revision: application.revision + 1,
        };
        return jsonResponse(application);
      }
      if (url === "/dealhost/api/hosting/applications/4/versions/" && method === "POST") {
        const payload = JSON.parse(String(init?.body));
        const version = {
          id: 9,
          ...payload,
          created_at: "2026-07-19T00:03:00Z",
        };
        application = {
          ...application,
          current_version: payload.version,
          revision: application.revision + 1,
          versions: [version],
        };
        return jsonResponse(version);
      }
      if (url === "/dealhost/api/hosting/modules/") return jsonResponse(modules);
      if (url === "/dealhost/api/gateway/apisix/publish/" && method === "POST") {
        const payload = JSON.parse(String(init?.body));
        if (!payload.dry_run && routePublicationAttempts++ === 0) {
          return jsonResponse({
            detail: "The effective route changed after preview; preview it again.",
            code: "route_preview_stale",
          }, 412);
        }
        const routeEtag = payload.module_slug === "field-portal"
          ? `"sha256-${"c".repeat(64)}"`
          : `"sha256-${"d".repeat(64)}"`;
        return jsonResponse({
          route_id: "module-field-portal",
          dry_run: payload.dry_run,
          etag: routeEtag,
          payload: {
            uris: ["/field", "/field/*"],
            upstream: { nodes: { "field-portal:8080": 1 } },
          },
          response: payload.dry_run ? null : { value: { id: "module-field-portal" } },
        });
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALHost" }));

    await screen.findByText("Field portal");
    await user.type(screen.getByLabelText("Semantic version"), "1.5.0");
    await user.type(screen.getByLabelText("Release notes"), "Reviewed metadata");
    await user.click(screen.getByRole("button", { name: "Publish version metadata" }));
    expect(await screen.findByText("Version metadata published. No runtime deployment was performed.")).toBeInTheDocument();
    const versionCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/applications/4/versions/" && init?.method === "POST",
    );
    expect(versionCall).toBeDefined();
    expect(new Headers(versionCall?.[1]?.headers).get("If-Match")).toBe('"1"');
    await waitFor(() => expect(fetchMock.mock.calls.filter(
      ([url, init]) => String(url) === "/dealhost/api/hosting/applications/" && (init?.method ?? "GET") === "GET",
    )).toHaveLength(2));

    await user.click(screen.getByRole("button", { name: "Application catalog" }));
    const applicationHeading = await screen.findByRole("heading", { name: "Application metadata" });
    const applicationForm = applicationHeading.closest("form");
    expect(applicationForm).not.toBeNull();
    const applicationQueries = within(applicationForm as HTMLFormElement);
    await user.clear(applicationQueries.getByLabelText("Name"));
    await user.type(applicationQueries.getByLabelText("Name"), "Field operations portal");
    await user.clear(applicationQueries.getByLabelText("Description"));
    await user.type(applicationQueries.getByLabelText("Description"), "Operations catalog entry");
    await user.click(applicationQueries.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Application metadata saved.")).toBeInTheDocument();
    const applicationPatch = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/applications/4/" && init?.method === "PATCH",
    );
    expect(new Headers(applicationPatch?.[1]?.headers).get("If-Match")).toBe('"2"');

    await user.click(screen.getByRole("button", { name: "APISIX routes" }));
    expect(await screen.findByText("/field")).toBeInTheDocument();
    const publishButton = screen.getByRole("button", { name: "Confirm and publish route" });
    expect(publishButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Preview APISIX route" }));
    expect(await screen.findByText("Previewed; APISIX was not changed")).toBeInTheDocument();
    expect(screen.getAllByText("field-portal:8080").length).toBeGreaterThanOrEqual(1);
    expect(publishButton).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /Other portal gateway/ }));
    expect(publishButton).toBeDisabled();
    expect(fetchMock.mock.calls.filter(
      ([url, init]) => String(url) === "/dealhost/api/gateway/apisix/publish/" && init?.method === "POST",
    )).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /Field portal gateway/ }));
    expect(publishButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Preview APISIX route" }));
    expect(publishButton).toBeEnabled();
    await user.click(publishButton);
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Field portal gateway"));
    expect(await screen.findByText("The effective route changed after preview; preview it again.")).toBeInTheDocument();
    expect(publishButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Preview APISIX route" }));
    expect(publishButton).toBeEnabled();
    await user.click(publishButton);
    expect(await screen.findByText("Published to APISIX")).toBeInTheDocument();

    const routeCalls = fetchMock.mock.calls.filter(
      ([url, init]) => String(url) === "/dealhost/api/gateway/apisix/publish/" && init?.method === "POST",
    );
    expect(routeCalls.map(([, init]) => JSON.parse(String(init?.body)).dry_run)).toEqual([
      true,
      true,
      false,
      true,
      false,
    ]);
    expect(new Headers(routeCalls[2][1]?.headers).get("If-Match")).toBe(
      `"sha256-${"c".repeat(64)}"`,
    );
    expect(new Headers(routeCalls[4][1]?.headers).get("If-Match")).toBe(
      `"sha256-${"c".repeat(64)}"`,
    );

    await user.click(screen.getByRole("button", { name: /Internal worker/ }));
    expect(screen.getByText("Publication blocked for a disabled module")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview APISIX route" })).toBeDisabled();
  });

  it("deploys and stops a versioned runtime from the dedicated DEALHost area", async () => {
    const user = userEvent.setup();
    const application: HostedApplication = {
      id: 4,
      name: "Field portal",
      slug: "field-portal",
      description: "Portal",
      current_version: "1.5.0",
      released_at: "2026-07-20T08:00:00Z",
      enabled: true,
      revision: 3,
      modules: [{ id: 9, name: "API", slug: "api" }],
      versions: [{
        id: 12,
        version: "1.5.0",
        notes: "Runtime release",
        source: "ci",
        created_at: "2026-07-20T08:00:00Z",
      }],
    };
    const environment: RuntimeEnvironment = {
      slug: "production",
      name: "Production",
      description: "Production Kubernetes cluster",
      orchestrator: "kubernetes",
      enabled: true,
      capabilities: {
        start_stop: true,
        restart: true,
        scaling: {
          fixed: { min_replicas: 1, max_replicas: 20 },
          autoscaling: { enabled: true, min_replicas: 2, max_replicas: 20 },
        },
        logs: { max_lines: 1000, max_bytes: 262144 },
        domains: false,
      },
      policy: {
        requires_image_digest: true,
        allowed_registries: ["ghcr.io/smartappli"],
        allowed_secret_refs: [],
        stateless_only: true,
      },
    };
    let runtime: RuntimeDeployment = {
      id: "3a8c6658-2976-45c1-b666-f72e79c23fc4",
      application: { id: 4, name: "Field portal", slug: "field-portal" },
      environment: "production",
      version: "1.5.0",
      desired_state: "running",
      observed_state: "running",
      revision: 1,
      configuration: {},
      secret_refs: {},
      scaling: { api: { mode: "fixed", replicas: 1 } },
      components: [{
        module_id: 9,
        slug: "api",
        image_digest: "ghcr.io/smartappli/api@sha256:abc",
        desired_replicas: 1,
        ready_replicas: 1,
        available_replicas: 1,
        state: "running",
        health: "healthy",
        restart_count: 0,
        last_error: null,
      }],
      last_error: null,
      last_reconciled_at: "2026-07-20T08:03:00Z",
      created_at: "2026-07-20T08:01:00Z",
      updated_at: "2026-07-20T08:03:00Z",
    };
    const completedOperation = (type: RuntimeOperation["type"]): RuntimeOperation => ({
      id: `operation-${type}`,
      deployment_id: runtime.id,
      type,
      status: "succeeded",
      requested_at: "2026-07-20T08:01:00Z",
      started_at: "2026-07-20T08:01:01Z",
      finished_at: "2026-07-20T08:01:02Z",
      progress: { stage: "complete", percent: 100 },
      result: {},
      error: null,
    });
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/dealhost/api/hosting/applications/" && method === "GET") {
        return jsonResponse([application]);
      }
      if (url === "/dealhost/api/hosting/runtime-environments/?page=1&page_size=100") {
        return jsonResponse({ count: 1, next: null, previous: null, results: [environment] });
      }
      if (url === "/dealhost/api/hosting/deployments/?application_id=4&page=1&page_size=100") {
        return jsonResponse({ count: 0, next: null, previous: null, results: [] });
      }
      if (url === "/dealhost/api/hosting/deployments/" && method === "POST") {
        return jsonResponse({ deployment: runtime, operation: completedOperation("deploy") }, 202);
      }
      if (url === `/dealhost/api/hosting/deployments/${runtime.id}/operations/?page=1&page_size=20`) {
        return jsonResponse({ count: 0, next: null, previous: null, results: [] });
      }
      if (url === `/dealhost/api/hosting/deployments/${runtime.id}/actions/` && method === "POST") {
        runtime = {
          ...runtime,
          desired_state: "stopped",
          observed_state: "stopped",
          revision: 2,
          components: runtime.components.map((component) => ({
            ...component,
            ready_replicas: 0,
            available_replicas: 0,
            state: "stopped",
          })),
        };
        return jsonResponse({ deployment: runtime, operation: completedOperation("stop") }, 202);
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALHost" }));
    await screen.findByText("Field portal");
    await user.click(screen.getByRole("button", { name: "Runtime deployments" }));

    expect(window.location.hash).toBe("#/modules/dealhost/runtime");
    expect(await screen.findByText("No active runtime deployment")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deploy runtime" }));
    expect(await screen.findByRole("heading", { name: "Runtime deployment" })).toBeInTheDocument();
    expect(screen.getAllByText("Running").length).toBeGreaterThanOrEqual(1);

    const deployCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/deployments/" && init?.method === "POST",
    );
    expect(deployCall).toBeDefined();
    expect(new Headers(deployCall?.[1]?.headers).get("If-Match")).toBe('"3"');
    expect(new Headers(deployCall?.[1]?.headers).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/i);
    expect(new Headers(deployCall?.[1]?.headers).has("Authorization")).toBe(false);
    expect(JSON.parse(String(deployCall?.[1]?.body))).toEqual({
      application_id: 4,
      environment: "production",
      version: "1.5.0",
      scaling: { api: { mode: "fixed", replicas: 1 } },
      configuration: {},
      secret_refs: {},
    });

    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect((await screen.findAllByText("Stopped")).length).toBeGreaterThanOrEqual(1);
    const stopCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/actions/") && init?.method === "POST",
    );
    expect(JSON.parse(String(stopCall?.[1]?.body))).toEqual({ action: "stop" });
    expect(new Headers(stopCall?.[1]?.headers).get("If-Match")).toBe('"1"');
    expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
  });

  it("preserves a stale application edit until the operator reloads the current revision", async () => {
    const user = userEvent.setup();
    let application: HostedApplication = {
      id: 4,
      name: "Field portal",
      slug: "field-portal",
      description: "Initial metadata",
      current_version: "1.4.0",
      released_at: "2026-07-19T00:00:00Z",
      enabled: true,
      revision: 4,
      versions: [],
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/dealhost/api/hosting/applications/" && method === "GET") {
        return jsonResponse([application]);
      }
      if (url === "/dealhost/api/hosting/applications/4/" && method === "PATCH") {
        application = {
          ...application,
          name: "Concurrent server edit",
          revision: 5,
        };
        return jsonResponse(
          {
            detail: "The application changed after it was loaded.",
            revision: 5,
          },
          412,
        );
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALHost" }));
    await screen.findByText("Field portal");
    await user.click(screen.getByRole("button", { name: "Application catalog" }));

    const applicationHeading = await screen.findByRole("heading", { name: "Application metadata" });
    const applicationForm = applicationHeading.closest("form");
    expect(applicationForm).not.toBeNull();
    const applicationQueries = within(applicationForm as HTMLFormElement);
    const nameInput = applicationQueries.getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "Stale local edit");
    await user.click(applicationQueries.getByRole("button", { name: "Save changes" }));

    expect(await applicationQueries.findByText("Concurrent change detected")).toBeInTheDocument();
    expect(nameInput).toHaveValue("Stale local edit");
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/applications/4/" && init?.method === "PATCH",
    );
    expect(new Headers(patchCall?.[1]?.headers).get("If-Match")).toBe('"4"');

    await user.click(applicationQueries.getByRole("button", { name: "Reload current revision" }));
    await waitFor(() => expect(nameInput).toHaveValue("Concurrent server edit"));
    expect(applicationQueries.getByText("Revision 5")).toBeInTheDocument();
    expect(applicationQueries.queryByText("Concurrent change detected")).not.toBeInTheDocument();
  });

  it("preserves release metadata when publication detects a stale application revision", async () => {
    const user = userEvent.setup();
    let application: HostedApplication = {
      id: 4,
      name: "Field portal",
      slug: "field-portal",
      description: "Initial metadata",
      current_version: "1.4.0",
      released_at: "2026-07-19T00:00:00Z",
      enabled: true,
      revision: 4,
      versions: [],
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/dealhost/api/hosting/applications/" && method === "GET") {
        return jsonResponse([application]);
      }
      if (url === "/dealhost/api/hosting/applications/4/versions/" && method === "POST") {
        application = {
          ...application,
          name: "Concurrent release edit",
          revision: 5,
        };
        return jsonResponse(
          {
            detail: "The application changed after it was loaded.",
            revision: 5,
          },
          412,
          { ETag: '"5"' },
        );
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALHost" }));
    await screen.findByText("Field portal");

    const versionInput = screen.getByLabelText("Semantic version");
    const sourceInput = screen.getByLabelText("Source");
    const notesInput = screen.getByLabelText("Release notes");
    await user.type(versionInput, "1.5.0");
    await user.clear(sourceInput);
    await user.type(sourceInput, "ci");
    await user.type(notesInput, "Reviewed immutable metadata");
    await user.click(screen.getByRole("button", { name: "Publish version metadata" }));

    expect(await screen.findByText("Concurrent change detected")).toBeInTheDocument();
    expect(versionInput).toHaveValue("1.5.0");
    expect(sourceInput).toHaveValue("ci");
    expect(notesInput).toHaveValue("Reviewed immutable metadata");
    const publishCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/applications/4/versions/" && init?.method === "POST",
    );
    expect(new Headers(publishCall?.[1]?.headers).get("If-Match")).toBe('"4"');

    await user.click(screen.getByRole("button", { name: "Reload application revision" }));
    await screen.findByText("1.4.0 · Revision 5");
    expect(versionInput).toHaveValue("1.5.0");
    expect(sourceInput).toHaveValue("ci");
    expect(notesInput).toHaveValue("Reviewed immutable metadata");
    expect(screen.queryByText("Concurrent change detected")).not.toBeInTheDocument();
  });

  it("creates and conditionally updates paginated dataset catalog entries without hiding conflicts", async () => {
    const user = userEvent.setup();
    let primaryDataset = {
      id: 8,
      name: "Telemetry",
      slug: "telemetry",
      description: "Raw telemetry",
      enabled: true,
      revision: 4,
      updated_at: "2026-07-19T00:00:00Z",
      user_ids: [],
      group_ids: [],
    };
    const otherDatasets = [{
      id: 9,
      name: "Operations",
      slug: "operations",
      description: "Operations data",
      enabled: true,
      revision: 2,
      updated_at: "2026-07-19T00:00:00Z",
      user_ids: [],
      group_ids: [],
    }];
    let rejectNextUpdate = false;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/dealhost/api/hosting/datasets/" && method === "GET") {
        return jsonResponse({
          results: [primaryDataset],
          next: "/dealhost/api/hosting/datasets/?page=2",
        });
      }
      if (url === "/dealhost/api/hosting/datasets/?page=2" && method === "GET") {
        return jsonResponse({ results: otherDatasets, next: null });
      }
      if (url === "/dealhost/api/hosting/datasets/" && method === "POST") {
        const created = {
          id: 10,
          ...JSON.parse(String(init?.body)),
          revision: 1,
          updated_at: "2026-07-19T00:01:00Z",
          user_ids: [],
          group_ids: [],
        };
        otherDatasets.push(created);
        return jsonResponse(created, 201);
      }
      if (url === "/dealhost/api/hosting/datasets/8/" && method === "PATCH") {
        if (rejectNextUpdate) {
          rejectNextUpdate = false;
          primaryDataset = {
            ...primaryDataset,
            name: "Server telemetry",
            revision: 6,
            updated_at: "2026-07-19T00:03:00Z",
          };
          return jsonResponse({ detail: "The dataset changed after it was loaded.", revision: 6 }, 412);
        }
        primaryDataset = {
          ...primaryDataset,
          ...JSON.parse(String(init?.body)),
          revision: 5,
          updated_at: "2026-07-19T00:02:00Z",
        };
        return jsonResponse(primaryDataset);
      }
      return jsonResponse(healthyPayloads[url] ?? { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALData" }));

    const editorHeading = await screen.findByRole("heading", { name: "Dataset catalog metadata" });
    expect(screen.getByText("Operations")).toBeInTheDocument();
    expect(screen.getByText(/neither screen grants or denies access to GPS or Sensor events/i)).toBeInTheDocument();
    const editor = editorHeading.closest("form");
    expect(editor).not.toBeNull();
    const editorQueries = within(editor as HTMLFormElement);
    await user.clear(editorQueries.getByLabelText("Name"));
    await user.type(editorQueries.getByLabelText("Name"), "Telemetry curated");
    await user.clear(editorQueries.getByLabelText("Description"));
    await user.type(editorQueries.getByLabelText("Description"), "Curated telemetry");
    await user.click(editorQueries.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Dataset catalog metadata saved.")).toBeInTheDocument();

    const firstPatch = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/datasets/8/" && init?.method === "PATCH",
    );
    expect(new Headers(firstPatch?.[1]?.headers).get("If-Match")).toBe('"4"');
    expect(JSON.parse(String(firstPatch?.[1]?.body))).toEqual({
      name: "Telemetry curated",
      description: "Curated telemetry",
      enabled: true,
    });

    const createHeading = screen.getByRole("heading", { name: "Create a dataset catalog entry" });
    const createForm = createHeading.closest("form");
    expect(createForm).not.toBeNull();
    const createQueries = within(createForm as HTMLFormElement);
    await user.type(createQueries.getByLabelText("Name"), "Quality");
    await user.type(createQueries.getByLabelText("Stable slug"), "quality");
    await user.type(createQueries.getByLabelText("Description"), "Quality metrics");
    await user.click(createQueries.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Dataset catalog entry created.")).toBeInTheDocument();
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/dealhost/api/hosting/datasets/" && init?.method === "POST",
    );
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      name: "Quality",
      slug: "quality",
      description: "Quality metrics",
      enabled: true,
    });

    await user.click(screen.getByRole("button", { name: /Telemetry curated/ }));
    rejectNextUpdate = true;
    await user.clear(editorQueries.getByLabelText("Name"));
    await user.type(editorQueries.getByLabelText("Name"), "Stale client value");
    await user.click(editorQueries.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Concurrent change detected")).toBeInTheDocument();
    expect(screen.getByText(/stale edit was not saved/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reload current revision" }));
    expect(await screen.findByDisplayValue("Server telemetry")).toBeInTheDocument();

    const patchCalls = fetchMock.mock.calls.filter(
      ([url, init]) => String(url) === "/dealhost/api/hosting/datasets/8/" && init?.method === "PATCH",
    );
    expect(new Headers(patchCalls[1][1]?.headers).get("If-Match")).toBe('"5"');
  });

  it("keeps all modules on the home page and opens their dedicated workspaces", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch({
      "/dealdata/core/api/experiments/": [],
      "/dealdata/sensor/api/sensors/": [],
      "/dealdata/sensor/api/wildfi/sensor/?limit=20&offset=0&summary=true": { results: [] },
      "/dealdata/gps/api/gps-sensors/": [],
      "/dealdata/gps/api/wildfi/gps/?limit=20&offset=0&summary=true": { results: [] },
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    expect(screen.getAllByRole("button", { name: /DEALHost/ }).length).toBeGreaterThan(1);
    expect(screen.getAllByRole("button", { name: /DEALIoT/ }).length).toBeGreaterThan(1);
    expect(screen.getAllByRole("button", { name: /DEALData/ }).length).toBeGreaterThan(1);

    const navigation = screen.getByLabelText("Module navigation");
    await user.click(within(navigation).getByRole("button", { name: "DEALIoT" }));
    expect(screen.getByRole("heading", { name: "DEALIoT device operations" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Device configuration" })).toBeInTheDocument();

    await user.click(within(navigation).getByRole("button", { name: "DEALHost" }));
    expect(screen.getByRole("heading", { name: "DEALHost application operations" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Release metadata" })).toBeInTheDocument();

    await user.click(within(navigation).getByRole("button", { name: "DEALData" }));
    expect(screen.getByRole("heading", { name: "DEALData scientific workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Datasets" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Experiments" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sensors" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "GPS sensors" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Catalog visibility" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Experiments" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/dealdata/core/api/experiments/",
      expect.any(Object),
    ));
    await user.click(screen.getByRole("button", { name: "Sensors" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/dealdata/sensor/api/wildfi/sensor/?limit=20&offset=0&summary=true",
      expect.any(Object),
    ));
    await user.click(screen.getByRole("button", { name: "GPS sensors" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/dealdata/gps/api/wildfi/gps/?limit=20&offset=0&summary=true",
      expect.any(Object),
    ));
  });
});
