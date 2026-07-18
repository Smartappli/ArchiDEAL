import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import type { DealModule, ModuleConnection } from "../types";
import { PlatformHealth } from "./PlatformHealth";

const modules: DealModule[] = [
  {
    key: "dealhost",
    name: "DEALHost",
    shortName: "Host",
    summary: "",
    owner: "Platform",
    accent: "#000",
    status: "online",
    endpointLabel: "Gateway",
    capabilities: [],
    integrations: [],
    metrics: [],
  },
  {
    key: "dealiot",
    name: "DEALIoT",
    shortName: "IoT",
    summary: "",
    owner: "Platform",
    accent: "#000",
    status: "online",
    endpointLabel: "Telemetry",
    capabilities: [],
    integrations: [],
    metrics: [],
  },
];

const onlineConnection: ModuleConnection = {
  moduleKey: "dealhost",
  status: "online",
  checkedAt: "2026-07-18T12:00:00.000Z",
  probes: [],
};

function renderHealth(connections: Partial<Record<DealModule["key"], ModuleConnection>>, onRefresh = vi.fn()) {
  render(
    <I18nProvider>
      <PlatformHealth connections={connections} isRefreshing={false} modules={modules} onRefresh={onRefresh} />
    </I18nProvider>,
  );

  return onRefresh;
}

describe("PlatformHealth", () => {
  it("uses a pending state until every module has been checked", () => {
    renderHealth({ dealhost: onlineConnection });

    expect(screen.getByText("Connecting to module APIs…")).toBeInTheDocument();
    expect(screen.getByText("Checking")).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  it("reports a healthy platform and refreshes its live probes", async () => {
    const user = userEvent.setup();
    const onRefresh = renderHealth({ dealhost: onlineConnection, dealiot: onlineConnection });

    expect(screen.getByRole("heading", { name: "All connected modules are operational." })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
