import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import { ScientificManagementPanel, type ScientificResourceKind } from "./ScientificManagementPanel";

const api = vi.hoisted(() => ({
  createExperiment: vi.fn(),
  createGpsSensor: vi.fn(),
  createSensor: vi.fn(),
  deleteExperiment: vi.fn(),
  deleteGpsSensor: vi.fn(),
  deleteSensor: vi.fn(),
  listExperiments: vi.fn(),
  listGpsFixes: vi.fn(),
  listGpsSensors: vi.fn(),
  listSensorEvents: vi.fn(),
  listSensors: vi.fn(),
  updateExperiment: vi.fn(),
  updateGpsSensor: vi.fn(),
  updateSensor: vi.fn(),
}));

vi.mock("../lib/scientificApi", () => api);

function panelElement(kind: ScientificResourceKind) {
  return (
    <I18nProvider>
      <ScientificManagementPanel
        areaDescription="Description"
        areaTitle="Area"
        kind={kind}
        moduleName="DEALData"
      />
    </I18nProvider>
  );
}

function panel(kind: ScientificResourceKind) {
  return render(panelElement(kind));
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

beforeEach(() => {
  for (const mock of Object.values(api)) mock.mockReset();
  api.listExperiments.mockResolvedValue([]);
  api.listGpsFixes.mockResolvedValue([]);
  api.listGpsSensors.mockResolvedValue([]);
  api.listSensorEvents.mockResolvedValue([]);
  api.listSensors.mockResolvedValue([]);
  api.deleteExperiment.mockResolvedValue(undefined);
  api.deleteGpsSensor.mockResolvedValue(undefined);
  api.deleteSensor.mockResolvedValue(undefined);
});

describe("ScientificManagementPanel", () => {
  it("creates, updates and deletes experiments with project and object links", async () => {
    const user = userEvent.setup();
    const first = {
      id: "11111111-1111-1111-1111-111111111111",
      project: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      observed_objects: ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
    };
    const second = {
      id: "22222222-2222-2222-2222-222222222222",
      project: "cccccccc-cccc-cccc-cccc-cccccccccccc",
      observed_objects: [],
    };
    api.listExperiments.mockResolvedValue([first]);
    api.updateExperiment.mockResolvedValue({ ...first, project: second.project });
    api.createExperiment.mockResolvedValue(second);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    panel("experiments");

    expect(await screen.findByText("Experiment 11111111")).toBeInTheDocument();
    const editor = screen.getByRole("heading", { name: "Scientific metadata" }).closest("form")!;
    const projectInput = within(editor).getByLabelText("Project UUID");
    await waitFor(() => expect(projectInput).toHaveValue(first.project));
    fireEvent.change(projectInput, { target: { value: second.project } });
    await user.click(within(editor).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.updateExperiment).toHaveBeenCalledWith(first.id, {
      project: second.project,
      observed_objects: first.observed_objects,
    }));
    await waitFor(() => expect(within(editor).getByRole("button", { name: "Save changes" })).toBeEnabled());

    const creator = screen.getByRole("heading", { name: "Create a resource" }).closest("form")!;
    await user.type(within(creator).getByLabelText("Project UUID"), second.project);
    await user.type(
      within(creator).getByLabelText("Observed object UUIDs"),
      "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb, bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    );
    await user.click(within(creator).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(api.createExperiment).toHaveBeenCalledWith({
      project: second.project,
      observed_objects: ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
    }));

    await waitFor(() => expect(screen.getByText("Experiment 22222222")).toBeInTheDocument());
    const updatedEditor = screen.getByRole("heading", { name: "Scientific metadata" }).closest("form")!;
    await waitFor(() => expect(within(updatedEditor).getByRole("button", { name: "Delete" })).toBeEnabled());
    await user.click(within(updatedEditor).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteExperiment).toHaveBeenCalledWith(second.id));
  });

  it("shows recent sensor events without exposing their payload", async () => {
    api.listSensorEvents.mockResolvedValue([{
      id: "event-1",
      device_id: "tag-1",
      observed_object_id: "object-1",
      timestamp: "2026-07-19T12:00:00Z",
      sensor_type: "temperature",
      payload: { secret: "not part of the frontend contract" },
    }]);
    panel("sensors");

    expect(await screen.findByText("tag-1 · 2026-07-19T12:00:00Z")).toBeInTheDocument();
    expect(screen.getByText("temperature")).toBeInTheDocument();
    expect(screen.queryByText(/not part of the frontend contract/)).not.toBeInTheDocument();
  });

  it("creates GPS sensor metadata with a numeric frequency and active state", async () => {
    const user = userEvent.setup();
    const created = {
      id: "gps-1",
      code: "GPS-1",
      purchase_date: "2026-07-19",
      frequency: 2.5,
      vendor: "Acme",
      model: "Tracker",
      sim_card: "SIM-1",
      active: true,
      created_at: "2026-07-19T12:00:00Z",
      updated_at: "2026-07-19T12:00:00Z",
    };
    api.createGpsSensor.mockResolvedValue(created);
    panel("gps");
    const creator = await screen.findByRole("heading", { name: "Create a resource" });
    const form = creator.closest("form")!;
    await waitFor(() => expect(within(form).getByRole("button", { name: "Create" })).toBeEnabled());

    await user.type(within(form).getByLabelText("Stable code"), "GPS-1");
    await user.type(within(form).getByLabelText("Vendor"), "Acme");
    await user.type(within(form).getByLabelText("Model"), "Tracker");
    await user.type(within(form).getByLabelText("Purchase date"), "2026-07-19");
    await user.type(within(form).getByLabelText("Sampling frequency (Hz)"), "2.5");
    await user.type(within(form).getByLabelText("SIM card identifier"), "SIM-1");
    await user.click(within(form).getByRole("button", { name: "Create" }));

    await waitFor(() => expect(api.createGpsSensor).toHaveBeenCalledWith({
      code: "GPS-1",
      purchase_date: "2026-07-19",
      frequency: 2.5,
      vendor: "Acme",
      model: "Tracker",
      sim_card: "SIM-1",
      active: true,
    }));
  });

  it("keeps the event empty state hidden while recent events are loading", async () => {
    const eventRequest = deferred<Array<{
      id: string;
      device_id: string;
      observed_object_id: string | null;
      timestamp: string;
      sensor_type: string;
    }>>();
    api.listSensorEvents.mockReturnValue(eventRequest.promise);

    panel("sensors");

    expect(screen.queryByText("No recent event was returned.")).not.toBeInTheDocument();
    expect(screen.getAllByText("Loading management data…").length).toBeGreaterThan(0);

    await act(async () => {
      eventRequest.resolve([{
        id: "event-delayed",
        device_id: "tag-delayed",
        observed_object_id: null,
        timestamp: "2026-07-19T13:00:00Z",
        sensor_type: "humidity",
      }]);
      await eventRequest.promise;
    });

    expect(await screen.findByText("tag-delayed · 2026-07-19T13:00:00Z")).toBeInTheDocument();
    expect(screen.queryByText("No recent event was returned.")).not.toBeInTheDocument();
  });

  it("ignores obsolete resource and event responses after the scientific kind changes", async () => {
    const staleResources = deferred<Array<{
      id: string;
      code: string;
      vendor: string;
      model: string;
      created_at: string;
      updated_at: string;
    }>>();
    const staleEvents = deferred<Array<{
      id: string;
      device_id: string;
      observed_object_id: string | null;
      timestamp: string;
      sensor_type: string;
    }>>();
    const currentResources = deferred<Array<{
      id: string;
      code: string;
      purchase_date: string;
      frequency: number;
      vendor: string;
      model: string;
      sim_card: string;
      active: boolean;
      created_at: string;
      updated_at: string;
    }>>();
    const currentEvents = deferred<Array<{
      id: string;
      device_id: string;
      observed_object_id: string | null;
      timestamp: string;
      latitude: number | null;
      longitude: number | null;
    }>>();
    api.listSensors.mockReturnValue(staleResources.promise);
    api.listSensorEvents.mockReturnValue(staleEvents.promise);
    api.listGpsSensors.mockReturnValue(currentResources.promise);
    api.listGpsFixes.mockReturnValue(currentEvents.promise);

    const view = panel("sensors");
    view.rerender(panelElement("gps"));

    await act(async () => {
      staleResources.resolve([{
        id: "11111111-1111-1111-1111-111111111111",
        code: "STALE-SENSOR",
        vendor: "Old",
        model: "Old",
        created_at: "2026-07-19T12:00:00Z",
        updated_at: "2026-07-19T12:00:00Z",
      }]);
      staleEvents.resolve([{
        id: "stale-event",
        device_id: "stale-device",
        observed_object_id: null,
        timestamp: "2026-07-19T12:00:00Z",
        sensor_type: "temperature",
      }]);
      await Promise.all([staleResources.promise, staleEvents.promise]);
    });

    expect(screen.queryByText("STALE-SENSOR")).not.toBeInTheDocument();
    expect(screen.queryByText(/stale-device/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled();

    await act(async () => {
      currentResources.resolve([{
        id: "22222222-2222-2222-2222-222222222222",
        code: "GPS-CURRENT",
        purchase_date: "2026-07-19",
        frequency: 1,
        vendor: "Acme",
        model: "Tracker",
        sim_card: "SIM-2",
        active: true,
        created_at: "2026-07-19T13:00:00Z",
        updated_at: "2026-07-19T13:00:00Z",
      }]);
      currentEvents.resolve([{
        id: "current-event",
        device_id: "current-device",
        observed_object_id: null,
        timestamp: "2026-07-19T13:00:00Z",
        latitude: 50.64,
        longitude: 5.57,
      }]);
      await Promise.all([currentResources.promise, currentEvents.promise]);
    });

    expect(await screen.findByText("GPS-CURRENT")).toBeInTheDocument();
    expect(screen.getByText("current-device · 2026-07-19T13:00:00Z")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
  });

  it("serializes scientific mutations and disables every conflicting control", async () => {
    const user = userEvent.setup();
    const sensor = {
      id: "33333333-3333-3333-3333-333333333333",
      code: "SENSOR-1",
      vendor: "Acme",
      model: "Probe",
      created_at: "2026-07-19T12:00:00Z",
      updated_at: "2026-07-19T12:00:00Z",
    };
    const updateRequest = deferred<typeof sensor>();
    api.listSensors.mockResolvedValue([sensor]);
    api.updateSensor.mockReturnValue(updateRequest.promise);
    panel("sensors");

    expect(await screen.findByText("SENSOR-1")).toBeInTheDocument();
    const editor = screen.getByRole("heading", { name: "Scientific metadata" }).closest("form")!;
    const creator = screen.getByRole("heading", { name: "Create a resource" }).closest("form")!;
    await user.clear(within(editor).getByLabelText("Vendor"));
    await user.type(within(editor).getByLabelText("Vendor"), "Updated vendor");
    await user.click(within(editor).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(api.updateSensor).toHaveBeenCalledTimes(1));
    expect(within(editor).getByLabelText("Vendor")).toBeDisabled();
    expect(within(editor).getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(within(creator).getByLabelText("Stable code")).toBeDisabled();
    expect(within(creator).getByRole("button", { name: "Create" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled();
    expect(within(screen.getByRole("navigation", { name: "Scientific resources" })).getByRole("button")).toBeDisabled();
    await user.click(within(creator).getByRole("button", { name: "Create" }));
    expect(api.createSensor).not.toHaveBeenCalled();

    await act(async () => {
      updateRequest.resolve({ ...sensor, vendor: "Updated vendor" });
      await updateRequest.promise;
    });

    await waitFor(() => expect(within(creator).getByRole("button", { name: "Create" })).toBeEnabled());
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
  });
});
