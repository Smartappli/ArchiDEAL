import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import { DatasetManagementPanel } from "./DatasetManagementPanel";

const api = vi.hoisted(() => ({
  createDatasetResource: vi.fn(),
  deleteDatasetResource: vi.fn(),
  listAllDatasetResources: vi.fn(),
  updateDatasetResource: vi.fn(),
}));

vi.mock("../lib/managementApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/managementApi")>()),
  ...api,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function renderPanel() {
  return render(
    <I18nProvider>
      <DatasetManagementPanel areaDescription="Description" areaTitle="Datasets" moduleName="DEALData" />
    </I18nProvider>,
  );
}

beforeEach(() => {
  for (const mock of Object.values(api)) mock.mockReset();
  api.deleteDatasetResource.mockResolvedValue(undefined);
});

it("deletes a selected dataset catalog entry after confirmation", async () => {
  const dataset = {
    id: 8,
    name: "Telemetry",
    slug: "telemetry",
    description: "Telemetry data",
    enabled: true,
    revision: 4,
    updated_at: "2026-07-19T00:00:00Z",
  };
  api.listAllDatasetResources.mockResolvedValue([dataset]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPanel();

  expect(await screen.findByText("Telemetry")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Delete dataset entry" }));

  await waitFor(() => expect(api.deleteDatasetResource).toHaveBeenCalledWith(dataset));
  expect(screen.getByText("Dataset catalog entry deleted.")).toBeInTheDocument();
});

it("serializes dataset deletion and preserves the remaining resource", async () => {
  const user = userEvent.setup();
  const first = {
    id: 8,
    name: "Telemetry",
    slug: "telemetry",
    description: "Telemetry data",
    enabled: true,
    revision: 4,
    updated_at: "2026-07-19T00:00:00Z",
  };
  const second = {
    id: 9,
    name: "Archive",
    slug: "archive",
    description: "Archived data",
    enabled: false,
    revision: 2,
    updated_at: "2026-07-19T00:00:00Z",
  };
  const deletion = deferred<void>();
  api.listAllDatasetResources.mockResolvedValue([first, second]);
  api.deleteDatasetResource.mockReturnValue(deletion.promise);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPanel();

  expect(await screen.findByText("Telemetry")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Delete dataset entry" }));

  await waitFor(() => expect(api.deleteDatasetResource).toHaveBeenCalledWith(first));
  const editor = screen.getByRole("heading", { name: "Dataset catalog metadata" }).closest("form")!;
  const creator = screen.getByRole("heading", { name: "Create a dataset catalog entry" }).closest("form")!;
  expect(within(editor).getByLabelText("Name")).toBeDisabled();
  expect(within(editor).getByRole("button", { name: "Save changes" })).toBeDisabled();
  expect(within(editor).getByRole("button", { name: "Deleting dataset…" })).toBeDisabled();
  expect(within(creator).getByLabelText("Name")).toBeDisabled();
  expect(within(creator).getByRole("button", { name: "Create" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled();
  for (const selector of within(screen.getByRole("navigation", { name: "Dataset catalog entries" })).getAllByRole("button")) {
    expect(selector).toBeDisabled();
  }
  await user.click(within(creator).getByRole("button", { name: "Create" }));
  expect(api.createDatasetResource).not.toHaveBeenCalled();

  await act(async () => {
    deletion.resolve();
    await deletion.promise;
  });

  await waitFor(() => expect(screen.queryByText("Telemetry")).not.toBeInTheDocument());
  expect(screen.getByText("Archive")).toBeInTheDocument();
  expect(within(screen.getByRole("heading", { name: "Dataset catalog metadata" }).closest("form")!).getByDisplayValue("Archive")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
});
