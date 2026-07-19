import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createExperiment,
  createGpsSensor,
  createSensor,
  deleteExperiment,
  deleteGpsSensor,
  deleteSensor,
  listExperiments,
  listGpsFixes,
  listGpsSensors,
  listSensorEvents,
  listSensors,
  updateExperiment,
  updateGpsSensor,
  updateSensor,
} from "./scientificApi";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("scientificApi", () => {
  it("uses the core experiment collection and encoded detail paths", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (_url, init) => (
      init?.method === "DELETE" ? jsonResponse(undefined, 204) : jsonResponse([])
    ));
    vi.stubGlobal("fetch", fetchMock);

    await listExperiments();
    await createExperiment({ project: "project-1", observed_objects: ["object-1"] });
    await updateExperiment("experiment/unsafe", { project: "project-2", observed_objects: [] });
    await deleteExperiment("experiment/unsafe");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/dealdata/core/api/experiments/",
      "/dealdata/core/api/experiments/",
      "/dealdata/core/api/experiments/experiment%2Funsafe/",
      "/dealdata/core/api/experiments/experiment%2Funsafe/",
    ]);
    expect(fetchMock.mock.calls.map(([, init]) => init?.method ?? "GET")).toEqual([
      "GET", "POST", "PATCH", "DELETE",
    ]);
  });

  it("uses the sensor metadata and recent-event contracts", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (_url, init) => (
      init?.method === "DELETE" ? jsonResponse(undefined, 204) : jsonResponse({ results: [] })
    ));
    vi.stubGlobal("fetch", fetchMock);

    await listSensors();
    await createSensor({ code: "S-1", vendor: "Bosch", model: "BMP680" });
    await updateSensor("sensor-1", { code: "S-2", vendor: "Bosch", model: "BMP680" });
    await deleteSensor("sensor-1");
    await listSensorEvents();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/dealdata/sensor/api/sensors/",
      "/dealdata/sensor/api/sensors/",
      "/dealdata/sensor/api/sensors/sensor-1/",
      "/dealdata/sensor/api/sensors/sensor-1/",
      "/dealdata/sensor/api/wildfi/sensor/?limit=20&offset=0&summary=true",
    ]);
  });

  it("uses the GPS metadata and recent-fix contracts", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (_url, init) => (
      init?.method === "DELETE" ? jsonResponse(undefined, 204) : jsonResponse([])
    ));
    vi.stubGlobal("fetch", fetchMock);
    const payload = {
      code: "GPS-1",
      purchase_date: "2026-07-19",
      frequency: 1,
      vendor: "Acme",
      model: "Tracker",
      sim_card: "sim-1",
      active: true,
    };

    await listGpsSensors();
    await createGpsSensor(payload);
    await updateGpsSensor("gps-1", payload);
    await deleteGpsSensor("gps-1");
    await listGpsFixes();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/dealdata/gps/api/gps-sensors/",
      "/dealdata/gps/api/gps-sensors/",
      "/dealdata/gps/api/gps-sensors/gps-1/",
      "/dealdata/gps/api/gps-sensors/gps-1/",
      "/dealdata/gps/api/wildfi/gps/?limit=20&offset=0&summary=true",
    ]);
  });
});
