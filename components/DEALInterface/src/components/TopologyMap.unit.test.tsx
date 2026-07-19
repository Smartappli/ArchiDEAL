import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import { dealModules } from "../data/dashboard";
import { TopologyMap } from "./TopologyMap";

describe("TopologyMap", () => {
  it("marks the active module in the topology", () => {
    const { container } = render(<I18nProvider><TopologyMap activeKey="dealiot" modules={dealModules} /></I18nProvider>);
    expect(screen.getByRole("heading", { name: "Unified management surface" })).toBeInTheDocument();
    expect(container.querySelectorAll(".topology-node")).toHaveLength(dealModules.length);
    expect(container.querySelector(".topology-node--active")).toHaveTextContent("IoT");
  });
});
