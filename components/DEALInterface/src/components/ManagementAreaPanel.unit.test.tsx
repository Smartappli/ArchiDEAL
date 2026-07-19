import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import { ManagementApiError } from "../lib/managementApi";
import { ManagementAreaPanel } from "./ManagementAreaPanel";

const api = vi.hoisted(() => ({ createManagementResource: vi.fn(), listManagementResources: vi.fn() }));
vi.mock("../lib/managementApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/managementApi")>()), ...api,
}));

function panel(moduleKey: "dealiot" | "dealhost" | "dealdata", areaId: string) {
  return render(<I18nProvider><ManagementAreaPanel areaDescription="Description" areaId={areaId} areaTitle="Area" moduleKey={moduleKey} moduleName="Module" /></I18nProvider>);
}

beforeEach(() => {
  api.createManagementResource.mockReset().mockResolvedValue({});
  api.listManagementResources.mockReset().mockResolvedValue([]);
});

describe("ManagementAreaPanel", () => {
  it("explains areas without a management endpoint", () => {
    panel("dealdata", "governance");
    expect(screen.getByText("API contract not exposed")).toBeInTheDocument();
  });

  it("lists devices and creates a provisioning device", async () => {
    const user = userEvent.setup();
    api.listManagementResources.mockResolvedValueOnce([{ device_id: "tag-1", display_name: "Tag One", kind: "gps", status: "active", revision: 4 }]).mockResolvedValueOnce([]);
    panel("dealiot", "devices");
    expect(await screen.findByText("Tag One")).toBeInTheDocument();
    expect(screen.getByText(/gps.*active.*revision 4/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Device identifier"), "tag-2");
    await user.type(screen.getByLabelText("Display name"), "Tag Two");
    await user.type(screen.getByLabelText("Device type"), "imu");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(api.createManagementResource).toHaveBeenCalledWith("/dealiot/api/devices", {
      device_id: "tag-2", display_name: "Tag Two", kind: "imu", status: "provisioning",
    }));
  });

  it("renders application release, route, and dataset access metadata", async () => {
    api.listManagementResources.mockResolvedValueOnce([{ id: 1, name: "Portal", slug: "portal", description: "", current_version: "1.2.3", released_at: null, enabled: true, revision: 1 }]);
    const first = panel("dealhost", "deployments");
    expect(await screen.findByText(/Published version: 1.2.3/)).toBeInTheDocument();
    first.unmount();

    api.listManagementResources.mockResolvedValueOnce([{ id: 2, name: "API", slug: "api", public_path: "/api", deployment_target: "api:8000", enabled: true }]);
    const second = panel("dealhost", "domains");
    expect(await screen.findByText(/\/api.*api:8000/)).toBeInTheDocument();
    second.unmount();

    api.listManagementResources.mockResolvedValueOnce([{ id: 3, name: "Telemetry", slug: "telemetry", description: "", enabled: true, revision: 1, updated_at: "now", group_ids: [1], user_ids: [2, 3] }]);
    panel("dealdata", "access");
    expect(await screen.findByText(/2 direct user.*1 group/i)).toBeInTheDocument();
  });

  it("surfaces authentication errors and supports retry", async () => {
    api.listManagementResources.mockRejectedValueOnce(new ManagementApiError({ kind: "authentication", message: "Sign in", retryable: true })).mockResolvedValueOnce([]);
    panel("dealhost", "apps");
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in");
    expect(screen.getByRole("link", { name: "Reconnect with OIDC" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("The API returned no resource for the current operator.")).toBeInTheDocument();
  });

  it("switches to read-only after an authorization failure", async () => {
    api.createManagementResource.mockRejectedValue(new ManagementApiError({ kind: "authorization", message: "Forbidden", retryable: false }));
    panel("dealhost", "apps");
    await screen.findByText("The API returned no resource for the current operator.");
    const form = screen.getByRole("heading", { name: "Add a resource" }).closest("form")!;
    await userEvent.type(within(form).getByLabelText("Name"), "Portal");
    await userEvent.type(within(form).getByLabelText("Stable slug"), "portal");
    await userEvent.type(within(form).getByLabelText("Description"), "Description");
    await userEvent.click(within(form).getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Read-only access")).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });
});
