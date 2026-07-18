import { describe, expect, it } from "vitest";
import { demoDataEnabled } from "./runtimeMode";

describe("demoDataEnabled", () => {
  it("always disables fixture data in production builds", () => {
    expect(demoDataEnabled("production", "true")).toBe(false);
    expect(demoDataEnabled("production")).toBe(false);
  });

  it("keeps fixture data available for development unless disabled", () => {
    expect(demoDataEnabled("development")).toBe(true);
    expect(demoDataEnabled("test", "false")).toBe(false);
  });
});
