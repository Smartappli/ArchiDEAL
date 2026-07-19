export type ApiErrorKind =
  | "authentication"
  | "authorization"
  | "validation"
  | "conflict"
  | "network"
  | "server";

export interface ApiProblem {
  kind: ApiErrorKind;
  status?: number;
  message: string;
  fields?: Record<string, string[]>;
  retryable: boolean;
  requestId?: string;
}

export class ManagementApiError extends Error {
  readonly problem: ApiProblem;

  constructor(problem: ApiProblem) {
    super(problem.message);
    this.name = "ManagementApiError";
    this.problem = problem;
  }
}

export interface HostedApplication {
  id: number;
  name: string;
  slug: string;
  description: string;
  current_version: string;
  released_at: string | null;
  enabled: boolean;
  revision: number;
  modules?: Array<{ id: number; name: string; slug: string }>;
  versions?: ApplicationVersion[];
}

export interface ApplicationVersion {
  id: number;
  version: string;
  notes: string;
  source: string;
  created_at: string;
}

export interface HostedModule {
  id: number;
  name: string;
  slug: string;
  public_path: string;
  deployment_target: string;
  upstream_host?: string;
  upstream_port?: number | null;
  enabled: boolean;
}

export interface GatewayRouteResult {
  route_id: string;
  dry_run: boolean;
  etag: string;
  skipped?: boolean;
  reason?: string;
  payload?: {
    uris?: string[];
    upstream?: { nodes?: Record<string, number> };
  } | null;
  response?: unknown;
}

export interface Dataset {
  id: number;
  name: string;
  slug: string;
  description: string;
  enabled: boolean;
  revision: number;
  updated_at: string;
  modules?: Array<{ id: number; name: string; slug: string }>;
  user_ids?: number[];
  group_ids?: number[];
}

export interface Device {
  device_id: string;
  display_name: string;
  kind: string;
  status: "provisioning" | "active" | "suspended" | "retired";
  mqtt_topic?: string | null;
  capabilities?: string[];
  settings?: Record<string, unknown>;
  labels?: Record<string, string>;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface DatasetPrincipalUser {
  id: number;
  label: string;
  email: string;
  is_active: boolean;
  identity_kind: "local" | "oidc";
}

export interface ProvisionedOidcIdentity {
  id: number;
  user_id: number;
  acl_username: string;
  issuer: string;
  subject: string;
  display_name: string;
  email: string;
  is_active: boolean;
  created: boolean;
  metadata_updated: boolean;
}

export interface DatasetPrincipalGroup {
  id: number;
  name: string;
}

export interface DatasetPrincipals {
  users: DatasetPrincipalUser[];
  groups: DatasetPrincipalGroup[];
  can_provision_oidc: boolean;
}

export interface IamGroup {
  id: number;
  name: string;
}

export interface IamUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  groups: IamGroup[];
  group_ids?: number[];
  date_joined: string;
  last_login: string | null;
  oidc_identity?: {
    issuer: string;
    subject: string;
    display_name: string;
    email: string;
    label: string;
  } | null;
}

interface CollectionEnvelope<T> {
  results?: T[];
  devices?: T[];
  next?: string | null;
}

interface DeviceEnvelope {
  device: Device;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function problemKind(status: number): ApiErrorKind {
  if (status === 401) return "authentication";
  if (status === 403) return "authorization";
  if (status === 400 || status === 422) return "validation";
  if (status === 409 || status === 412 || status === 428) return "conflict";
  return "server";
}

function problemFields(payload: unknown) {
  if (!isRecord(payload)) return undefined;

  const fields: Record<string, string[]> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (key === "detail" || key === "error" || key === "message") continue;
    if (typeof value === "string") fields[key] = [value];
    if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
      fields[key] = value;
    }
  }

  return Object.keys(fields).length > 0 ? fields : undefined;
}

function problemMessage(payload: unknown, status: number) {
  if (isRecord(payload)) {
    for (const key of ["detail", "message", "error"]) {
      if (typeof payload[key] === "string") return payload[key];
    }
    const fields = problemFields(payload);
    if (fields) {
      return Object.entries(fields)
        .map(([name, messages]) => `${name}: ${messages.join(", ")}`)
        .join("; ");
    }
  }
  return `HTTP ${status}`;
}

function sameOriginCsrfToken() {
  if (typeof document === "undefined") return undefined;
  const entry = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith("csrftoken="));
  if (!entry) return undefined;
  const value = entry.slice("csrftoken=".length);
  try {
    return decodeURIComponent(value) || undefined;
  } catch {
    return undefined;
  }
}

async function responsePayload(response: Response) {
  if (response.status === 204) return undefined;

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json() as Promise<unknown>;
  }

  const text = await response.text();
  return text || undefined;
}

export async function managementRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  if (
    !path.startsWith("/")
    || path.startsWith("//")
    || path.includes("\\")
    || /[\u0000-\u001f\u007f]/.test(path)
  ) {
    throw new ManagementApiError({
      kind: "validation",
      message: "Management API paths must be same-origin.",
      retryable: false,
    });
  }

  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // Authentication is deliberately delegated to the same-origin OIDC/BFF
  // boundary. Browser code must never receive or manufacture a bearer token.
  headers.delete("Authorization");
  const method = (init.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrfToken = sameOriginCsrfToken();
    if (csrfToken && !headers.has("X-CSRFToken")) {
      headers.set("X-CSRFToken", csrfToken);
    }
  }

  const callerSignal = init.signal;
  const controller = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) abortFromCaller();
  else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
  const timeoutId = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 15_000);

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      cache: "no-store",
      credentials: "same-origin",
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError" && callerSignal?.aborted) {
      throw error;
    }
    throw new ManagementApiError({
      kind: "network",
      message: timedOut
        ? "The management API request timed out."
        : error instanceof Error ? error.message : "Network request failed.",
      retryable: true,
    });
  } finally {
    globalThis.clearTimeout(timeoutId);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }

  const payload = await responsePayload(response);
  const contentType = response.headers.get("content-type") ?? "";
  if (response.redirected || (response.ok && payload !== undefined && !contentType.includes("application/json"))) {
    throw new ManagementApiError({
      kind: "authentication",
      status: 401,
      message: "The operator session must be renewed.",
      retryable: false,
    });
  }

  if (!response.ok) {
    const kind = problemKind(response.status);
    throw new ManagementApiError({
      kind,
      status: response.status,
      message: problemMessage(payload, response.status),
      fields: problemFields(payload),
      retryable: kind === "network" || kind === "server",
      requestId: response.headers.get("x-request-id") ?? undefined,
    });
  }

  return payload as T;
}

export async function listManagementResources<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T[]> {
  const payload = await managementRequest<T[] | CollectionEnvelope<T>>(path, { signal });
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.results)) return payload.results;
  if (Array.isArray(payload.devices)) return payload.devices;
  throw new ManagementApiError({
    kind: "server",
    message: "The management API returned an invalid collection contract.",
    retryable: true,
  });
}

function nextCollectionPath(
  next: unknown,
  currentPath: string,
  allowedPathname: string,
) {
  if (next === null || next === undefined || next === "") return undefined;
  if (typeof next !== "string") {
    throw new ManagementApiError({
      kind: "server",
      message: "The management API returned an invalid pagination link.",
      retryable: true,
    });
  }

  const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  const resolved = new URL(next, `${origin}${currentPath}`);
  if (
    resolved.origin !== origin
    || resolved.pathname !== allowedPathname
    || resolved.hash
  ) {
    throw new ManagementApiError({
      kind: "server",
      message: "The management API returned an unsafe pagination link.",
      retryable: false,
    });
  }
  return `${resolved.pathname}${resolved.search}`;
}

export async function listAllDatasetResources(signal?: AbortSignal): Promise<Dataset[]> {
  const datasets: Dataset[] = [];
  const seenPaths = new Set<string>();
  let path: string | undefined = "/dealhost/api/hosting/datasets/";

  for (let page = 0; path !== undefined && page < 100; page += 1) {
    if (seenPaths.has(path)) {
      throw new ManagementApiError({
        kind: "server",
        message: "The dataset catalog returned a cyclic pagination link.",
        retryable: true,
      });
    }
    seenPaths.add(path);

    const payload = await managementRequest<Dataset[] | CollectionEnvelope<Dataset>>(
      path,
      { signal },
    );
    if (Array.isArray(payload)) {
      datasets.push(...payload);
      return datasets;
    }
    if (!isRecord(payload) || !Array.isArray(payload.results)) {
      throw new ManagementApiError({
        kind: "server",
        message: "The dataset catalog returned an invalid collection contract.",
        retryable: true,
      });
    }
    datasets.push(...payload.results);
    path = nextCollectionPath(
      payload.next,
      path,
      "/dealhost/api/hosting/datasets/",
    );
  }

  if (path !== undefined) {
    throw new ManagementApiError({
      kind: "server",
      message: "The dataset catalog exceeded the supported pagination depth.",
      retryable: true,
    });
  }
  return datasets;
}

export function createManagementResource<T>(
  path: string,
  payload: object,
  signal?: AbortSignal,
  headers?: HeadersInit,
) {
  return managementRequest<T>(path, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
    headers,
  });
}

export function updateManagementResource<T>(
  path: string,
  payload: object,
  signal?: AbortSignal,
  headers?: HeadersInit,
) {
  return managementRequest<T>(path, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
    headers,
  });
}

export function deleteManagementResource(
  path: string,
  signal?: AbortSignal,
  headers?: HeadersInit,
) {
  return managementRequest<void>(path, { method: "DELETE", signal, headers });
}

export function createIamUser(
  payload: Pick<IamUser, "username" | "email" | "first_name" | "last_name" | "is_active" | "is_staff" | "is_superuser"> & { password: string; group_ids: number[] },
  signal?: AbortSignal,
) {
  return createManagementResource<IamUser>("/dealhost/api/iam/users/", payload, signal);
}

export function updateIamUser(
  userId: number,
  payload: Pick<IamUser, "email" | "first_name" | "last_name" | "is_active" | "is_staff" | "is_superuser"> & { group_ids: number[] },
  signal?: AbortSignal,
) {
  return updateManagementResource<IamUser>(`/dealhost/api/iam/users/${userId}/`, payload, signal);
}

export function deleteIamUser(userId: number, signal?: AbortSignal) {
  return deleteManagementResource(`/dealhost/api/iam/users/${userId}/`, signal);
}

export function setIamUserPassword(userId: number, password: string, signal?: AbortSignal) {
  return createManagementResource<void>(
    `/dealhost/api/iam/users/${userId}/set-password/`,
    { password },
    signal,
  );
}

function strongRevisionEtag(revision: number) {
  if (!Number.isSafeInteger(revision) || revision < 1) {
    throw new ManagementApiError({
      kind: "validation",
      message: "A positive resource revision is required for a conditional mutation.",
      retryable: false,
    });
  }
  return `"${revision}"`;
}

export function createDatasetResource(
  payload: Pick<Dataset, "name" | "slug" | "description" | "enabled">,
  signal?: AbortSignal,
) {
  return createManagementResource<Dataset>(
    "/dealhost/api/hosting/datasets/",
    payload,
    signal,
  );
}

export function updateDatasetResource(
  dataset: Dataset,
  payload: Pick<Dataset, "name" | "description" | "enabled">,
  signal?: AbortSignal,
) {
  return updateManagementResource<Dataset>(
    `/dealhost/api/hosting/datasets/${dataset.id}/`,
    payload,
    signal,
    { "If-Match": strongRevisionEtag(dataset.revision) },
  );
}

export function deleteDatasetResource(dataset: Dataset, signal?: AbortSignal) {
  return deleteManagementResource(
    `/dealhost/api/hosting/datasets/${dataset.id}/`,
    signal,
    { "If-Match": strongRevisionEtag(dataset.revision) },
  );
}

function devicePath(deviceId: string) {
  return `/dealiot/api/devices/${encodeURIComponent(deviceId)}`;
}

function unwrapDevice(payload: Device | DeviceEnvelope) {
  return "device" in payload ? payload.device : payload;
}

export async function createDeviceResource(
  payload: Pick<Device, "device_id" | "display_name" | "kind" | "status">,
  signal?: AbortSignal,
) {
  const result = await createManagementResource<Device | DeviceEnvelope>(
    "/dealiot/api/devices",
    payload,
    signal,
  );
  return unwrapDevice(result);
}

export async function updateDeviceResource(
  device: Device,
  payload: {
    display_name: string;
    kind: string;
    status: Device["status"];
    mqtt_topic: string | null;
    capabilities: string[];
    settings: Record<string, unknown>;
    labels: Record<string, string>;
  },
  signal?: AbortSignal,
) {
  const result = await updateManagementResource<Device | DeviceEnvelope>(
    devicePath(device.device_id),
    payload,
    signal,
    { "If-Match": strongRevisionEtag(device.revision) },
  );
  return unwrapDevice(result);
}

export function retireDeviceResource(device: Device, signal?: AbortSignal) {
  return managementRequest<void>(devicePath(device.device_id), {
    method: "DELETE",
    headers: { "If-Match": strongRevisionEtag(device.revision) },
    signal,
  });
}

export function updateHostedApplicationResource(
  application: HostedApplication,
  payload: Pick<HostedApplication, "name" | "description" | "enabled">,
  signal?: AbortSignal,
) {
  return updateManagementResource<HostedApplication>(
    `/dealhost/api/hosting/applications/${application.id}/`,
    payload,
    signal,
    { "If-Match": strongRevisionEtag(application.revision) },
  );
}

export function publishHostedApplicationVersion(
  application: HostedApplication,
  payload: { version: string; notes: string; source: string },
  signal?: AbortSignal,
) {
  return createManagementResource<ApplicationVersion>(
    `/dealhost/api/hosting/applications/${application.id}/versions/`,
    payload,
    signal,
    { "If-Match": strongRevisionEtag(application.revision) },
  );
}

const STRONG_ROUTE_PREVIEW_ETAG = /^"sha256-[0-9a-f]{64}"$/;

export function isStrongRoutePreviewEtag(value: unknown): value is string {
  return typeof value === "string" && STRONG_ROUTE_PREVIEW_ETAG.test(value);
}

export function publishGatewayRoute(
  moduleSlug: string,
  dryRun: boolean,
  previewEtag?: string,
  signal?: AbortSignal,
) {
  if (!dryRun && !isStrongRoutePreviewEtag(previewEtag)) {
    throw new ManagementApiError({
      kind: "validation",
      message: "A valid strong route preview ETag is required before publication.",
      retryable: false,
    });
  }
  return managementRequest<GatewayRouteResult>(
    "/dealhost/api/gateway/apisix/publish/",
    {
      method: "POST",
      body: JSON.stringify({ module_slug: moduleSlug, dry_run: dryRun }),
      headers: dryRun || typeof previewEtag !== "string"
        ? undefined
        : { "If-Match": previewEtag },
      signal,
    },
  );
}

export function provisionOidcIdentity(
  payload: { issuer: string; subject: string; display_name: string; email: string },
  signal?: AbortSignal,
) {
  return createManagementResource<ProvisionedOidcIdentity>(
    "/dealhost/api/iam/oidc-identities/",
    payload,
    signal,
  );
}

export async function getDatasetPrincipals(signal?: AbortSignal): Promise<DatasetPrincipals> {
  const payload = await managementRequest<Partial<DatasetPrincipals>>(
    "/dealhost/api/hosting/dataset-principals/",
    { signal },
  );
  return {
    users: Array.isArray(payload.users) ? payload.users : [],
    groups: Array.isArray(payload.groups) ? payload.groups : [],
    can_provision_oidc: payload.can_provision_oidc === true,
  };
}
