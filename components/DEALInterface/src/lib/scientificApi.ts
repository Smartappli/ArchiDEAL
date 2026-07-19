import {
  createManagementResource,
  deleteManagementResource,
  listManagementResources,
  updateManagementResource,
} from "./managementApi";

export interface ExperimentResource {
  id: string;
  project: string;
  observed_objects: string[];
}

export interface SensorResource {
  id: string;
  vendor: string;
  model: string;
  code: string;
  created_at: string;
  updated_at: string;
}

export interface GpsSensorResource {
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
}

export interface SensorEventResource {
  id: string;
  device_id: string;
  observed_object_id: string | null;
  timestamp: string;
  sensor_type: string;
}

export interface GpsFixResource {
  id: string;
  device_id: string;
  observed_object_id: string | null;
  timestamp: string;
  latitude: number | null;
  longitude: number | null;
}

export type ExperimentPayload = Pick<ExperimentResource, "project" | "observed_objects">;
export type SensorPayload = Pick<SensorResource, "vendor" | "model" | "code">;
export type GpsSensorPayload = Pick<
  GpsSensorResource,
  "code" | "purchase_date" | "frequency" | "vendor" | "model" | "sim_card" | "active"
>;

const EXPERIMENTS_PATH = "/dealdata/core/api/experiments/";
const SENSORS_PATH = "/dealdata/sensor/api/sensors/";
const GPS_SENSORS_PATH = "/dealdata/gps/api/gps-sensors/";

function detailPath(collectionPath: string, id: string) {
  return `${collectionPath}${encodeURIComponent(id)}/`;
}

export function listExperiments(signal?: AbortSignal) {
  return listManagementResources<ExperimentResource>(EXPERIMENTS_PATH, signal);
}

export function createExperiment(payload: ExperimentPayload, signal?: AbortSignal) {
  return createManagementResource<ExperimentResource>(EXPERIMENTS_PATH, payload, signal);
}

export function updateExperiment(id: string, payload: ExperimentPayload, signal?: AbortSignal) {
  return updateManagementResource<ExperimentResource>(detailPath(EXPERIMENTS_PATH, id), payload, signal);
}

export function deleteExperiment(id: string, signal?: AbortSignal) {
  return deleteManagementResource(detailPath(EXPERIMENTS_PATH, id), signal);
}

export function listSensors(signal?: AbortSignal) {
  return listManagementResources<SensorResource>(SENSORS_PATH, signal);
}

export function createSensor(payload: SensorPayload, signal?: AbortSignal) {
  return createManagementResource<SensorResource>(SENSORS_PATH, payload, signal);
}

export function updateSensor(id: string, payload: SensorPayload, signal?: AbortSignal) {
  return updateManagementResource<SensorResource>(detailPath(SENSORS_PATH, id), payload, signal);
}

export function deleteSensor(id: string, signal?: AbortSignal) {
  return deleteManagementResource(detailPath(SENSORS_PATH, id), signal);
}

export function listSensorEvents(signal?: AbortSignal) {
  return listManagementResources<SensorEventResource>(
    "/dealdata/sensor/api/wildfi/sensor/?limit=20&offset=0&summary=true",
    signal,
  );
}

export function listGpsSensors(signal?: AbortSignal) {
  return listManagementResources<GpsSensorResource>(GPS_SENSORS_PATH, signal);
}

export function createGpsSensor(payload: GpsSensorPayload, signal?: AbortSignal) {
  return createManagementResource<GpsSensorResource>(GPS_SENSORS_PATH, payload, signal);
}

export function updateGpsSensor(id: string, payload: GpsSensorPayload, signal?: AbortSignal) {
  return updateManagementResource<GpsSensorResource>(detailPath(GPS_SENSORS_PATH, id), payload, signal);
}

export function deleteGpsSensor(id: string, signal?: AbortSignal) {
  return deleteManagementResource(detailPath(GPS_SENSORS_PATH, id), signal);
}

export function listGpsFixes(signal?: AbortSignal) {
  return listManagementResources<GpsFixResource>(
    "/dealdata/gps/api/wildfi/gps/?limit=20&offset=0&summary=true",
    signal,
  );
}
