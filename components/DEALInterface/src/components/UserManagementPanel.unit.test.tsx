import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import { ManagementApiError, type IamUser } from "../lib/managementApi";
import { UserManagementPanel } from "./UserManagementPanel";

const api = vi.hoisted(() => ({
  createIamUser: vi.fn(),
  deleteIamUser: vi.fn(),
  listManagementResources: vi.fn(),
  setIamUserPassword: vi.fn(),
  updateIamUser: vi.fn(),
}));

vi.mock("../lib/managementApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/managementApi")>()),
  ...api,
}));

const localUser: IamUser = {
  id: 1, username: "alice", email: "alice@example.test", first_name: "Alice", last_name: "Admin",
  is_active: true, is_staff: true, is_superuser: false, groups: [{ id: 10, name: "operators" }],
  date_joined: "2026-01-01", last_login: null,
};
const oidcUser: IamUser = {
  ...localUser, id: 2, username: "oidc-bob", email: "", first_name: "Bob", groups: [],
  oidc_identity: { issuer: "issuer", subject: "bob", display_name: "Bob", email: "", label: "Bob" },
};

function renderPanel() {
  return render(<I18nProvider><UserManagementPanel areaDescription="Manage identities" areaTitle="Users" moduleName="DEALHost" /></I18nProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((mock) => mock.mockReset());
  api.listManagementResources.mockImplementation((endpoint: string) => Promise.resolve(endpoint.includes("groups")
    ? [{ id: 10, name: "operators" }, { id: 20, name: "reviewers" }]
    : [localUser, oidcUser]));
  api.updateIamUser.mockResolvedValue({ ...localUser, first_name: "Alicia", groups: [{ id: 20, name: "reviewers" }] });
  api.setIamUserPassword.mockResolvedValue(undefined);
  api.deleteIamUser.mockResolvedValue(undefined);
  api.createIamUser.mockResolvedValue({ ...localUser, id: 3, username: "charlie" });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("UserManagementPanel", () => {
  it("loads, filters, edits groups and saves a local user", async () => {
    const user = userEvent.setup();
    renderPanel();
    expect(await screen.findByRole("button", { name: /alice/i })).toHaveAttribute("aria-current", "true");

    await user.type(screen.getByRole("searchbox"), "bob");
    expect(screen.queryByRole("button", { name: /alice/i })).not.toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox"));

    const editor = screen.getByRole("heading", { name: "alice" }).closest("form")!;
    await user.clear(within(editor).getByLabelText("First name"));
    await user.type(within(editor).getByLabelText("First name"), "Alicia");
    await user.click(screen.getByLabelText(/operators/));
    await user.click(screen.getByLabelText(/reviewers/));
    await user.click(screen.getByRole("button", { name: "Save user" }));

    await waitFor(() => expect(api.updateIamUser).toHaveBeenCalledWith(1, expect.objectContaining({
      first_name: "Alicia", group_ids: [20],
    })));
    expect(await screen.findByRole("status")).toHaveTextContent("User saved.");
  });

  it("changes a password, deletes a user and creates another", async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByRole("button", { name: /alice/i });

    await user.type(screen.getByLabelText("New password"), "secure-pass");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(api.setIamUserPassword).toHaveBeenCalledWith(1, "secure-pass"));

    await user.click(screen.getByRole("button", { name: "Delete user" }));
    await waitFor(() => expect(api.deleteIamUser).toHaveBeenCalledWith(1));
    expect(screen.getByRole("button", { name: /oidc-bob/i })).toHaveAttribute("aria-current", "true");

    const createForm = screen.getByRole("heading", { name: "Create a local user" }).closest("form")!;
    await user.type(within(createForm).getByLabelText("Username"), "charlie");
    await user.type(within(createForm).getByLabelText("Initial password"), "secure-pass");
    await user.click(within(createForm).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(api.createIamUser).toHaveBeenCalledWith(expect.objectContaining({ username: "charlie" })));
    expect(await screen.findByRole("button", { name: /charlie/i })).toHaveAttribute("aria-current", "true");
  });

  it("shows authentication failures, retries, and ignores cancelled deletion", async () => {
    api.listManagementResources.mockRejectedValue(new ManagementApiError({
      kind: "authentication", message: "Session expired", retryable: true,
    }));
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("Session expired");
    expect(screen.getByRole("link", { name: "Reconnect with OIDC" })).toHaveAttribute("href", expect.stringContaining("/oauth2/start"));

    api.listManagementResources.mockResolvedValueOnce([localUser]).mockResolvedValueOnce([]);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("button", { name: /alice/i });
    vi.mocked(window.confirm).mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "Delete user" }));
    expect(api.deleteIamUser).not.toHaveBeenCalled();
  });

  it("normalizes unexpected action errors and renders an empty directory", async () => {
    api.listManagementResources.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByText("The API returned no resource for the current operator.")).toBeInTheDocument();

    const createForm = screen.getByRole("heading", { name: "Create a local user" }).closest("form")!;
    api.createIamUser.mockRejectedValue(new Error("boom"));
    fireEvent.change(within(createForm).getByLabelText("Username"), { target: { value: "broken" } });
    fireEvent.change(within(createForm).getByLabelText("Initial password"), { target: { value: "secure-pass" } });
    fireEvent.submit(createForm);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unexpected management API error.");
  });
});
