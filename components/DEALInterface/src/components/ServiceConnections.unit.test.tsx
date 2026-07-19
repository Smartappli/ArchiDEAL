import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModuleRuntimeConfig } from "../config/moduleRegistry";
import { I18nProvider } from "../i18n/I18nProvider";
import type { DealModule, ModuleConnection, ModuleKey } from "../types";
import { ServiceConnections } from "./ServiceConnections";

const modules: DealModule[] = [
  {
    key: "dealhost",
    name: "DEALHost",
    shortName: "Host",
    summary: "",
    owner: "Platform",
    accent: "#000",
    status: "protected",
    endpointLabel: "Gateway",
    capabilities: [],
    integrations: [],
    metrics: [],
  },
];

const runtime: ModuleRuntimeConfig = {
  key: "dealhost",
  apiBaseUrl: "/dealhost",
  healthPath: "/api/gateway/health/",
  docsPath: "/docs/dealhost",
  probes: [{ id: "gateway", label: "Gateway API", path: "/api/gateway/health/" }],
};

const runtimes = {
  dealhost: runtime,
  dealiot: { ...runtime, key: "dealiot" },
  dealdata: { ...runtime, key: "dealdata" },
} satisfies Record<ModuleKey, ModuleRuntimeConfig>;

describe("ServiceConnections", () => {
  it("shows protected probes without counting them as healthy", () => {
    const connection: ModuleConnection = {
      moduleKey: "dealhost",
      status: "protected",
      checkedAt: "2026-07-18T12:00:00.000Z",
      probes: [
        {
          id: "gateway",
          label: "Gateway API",
          url: "/dealhost/api/gateway/health/",
          status: "protected",
          httpStatus: 401,
          detail: "HTTP 401",
          checkedAt: "2026-07-18T12:00:00.000Z",
        },
      ],
    };

    render(
      <I18nProvider>
        <ServiceConnections
          activeKey="dealhost"
          connections={{ dealhost: connection }}
          isRefreshing={false}
          modules={modules}
          onRefresh={vi.fn()}
          onSelectModule={vi.fn()}
          runtimes={runtimes}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(/0\/1 healthy probes/)).toBeInTheDocument();
    expect(screen.getAllByText("Access protected")).toHaveLength(2);
    expect(screen.queryByText("Online")).not.toBeInTheDocument();
  });
});
