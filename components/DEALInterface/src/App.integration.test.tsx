import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const healthyPayloads: Record<string, unknown> = {
  "/dealhost/api/gateway/health/": {
    status: "ok",
    service: "dealhost-gateway",
  },
  "/dealiot/healthz": {
    status: "ok",
    service: "dealiot-management",
  },
  "/dealiot/api/health": {
    summary: {
      healthy: 3,
    },
  },
  "/dealdata/core/health/ready/": {
    status: "ok",
    service: "dealdata-core",
  },
  "/dealdata/gps/health/ready/": {
    status: "ok",
    service: "dealdata-gps",
  },
  "/dealdata/sensor/health/ready/": {
    status: "ok",
    service: "dealdata-sensor",
  },
};

type MockPayload = unknown | Error;

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    headers: {
      "content-type": "application/json",
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

    return jsonResponse(payload);
  });

  vi.stubGlobal("fetch", fetchMock);

  return fetchMock;
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("App live module integrations", () => {
  it("probes DEALHost, DEALIoT and DEALData endpoints on initial render", async () => {
    const fetchMock = mockModuleFetch();

    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: /Manage DEALHost, DEALIot and DEALData from one deliberate interface/i,
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
    expect(screen.getByText("1/1 live probes healthy")).toBeInTheDocument();
  });

  it("keeps the console usable and surfaces a failed module probe", async () => {
    const user = userEvent.setup();
    const fetchMock = mockModuleFetch({
      "/dealiot/api/health": new Error("dealiot API offline"),
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALIot" }));

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
          service: "dealhost-gateway",
        },
      ],
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    expect(screen.getByText("1/1 live probes healthy")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(12));

    expect(screen.getByText("0/1 live probes healthy")).toBeInTheDocument();
    expect(screen.getByText("down / dealhost-gateway")).toBeInTheDocument();
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
        summary: {
          healthy: 4,
          degraded: 1,
        },
      },
    });

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));

    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALData" }));

    expect(await screen.findByText("/dealdata/sensor/health/ready/")).toBeInTheDocument();
    expect(screen.getByText("4 healthy, 1 degraded")).toBeInTheDocument();
    expect(screen.getByText("2/3 live probes healthy")).toBeInTheDocument();

    await user.click(within(screen.getByLabelText("Module navigation")).getByRole("button", { name: "DEALHost" }));

    expect(screen.getByText("/dealhost/api/gateway/health/")).toBeInTheDocument();
    expect(screen.getByText("1/1 live probes healthy")).toBeInTheDocument();
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

    expect(screen.getByRole("heading", { name: "Pilotez DEALHost, DEALIot et DEALData depuis une interface unifiee." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rafraichir" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
    expect(window.localStorage.getItem("dealinterface.language")).toBe("fr");
  });
});
