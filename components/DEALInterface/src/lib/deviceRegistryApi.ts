import {
  type Device,
  ManagementApiError,
  managementRequest,
} from "./managementApi";

export interface DeviceRegistryPage {
  devices: Device[];
  nextCursor?: string;
}

interface DeviceRegistryPagePayload {
  devices?: unknown;
  next_cursor?: unknown;
}

interface DevicePageQuery {
  cursor?: string;
  limit?: number;
  query?: string;
}

export async function listDeviceRegistryPage(
  { cursor, limit = 100, query }: DevicePageQuery = {},
  signal?: AbortSignal,
): Promise<DeviceRegistryPage> {
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 200) {
    throw new ManagementApiError({
      kind: "validation",
      message: "The device page size must be between 1 and 200.",
      retryable: false,
    });
  }

  const parameters = new URLSearchParams({ limit: String(limit) });
  if (cursor) parameters.set("cursor", cursor);
  if (query) parameters.set("q", query);
  const payload = await managementRequest<DeviceRegistryPagePayload>(
    `/dealiot/api/devices?${parameters.toString()}`,
    { signal },
  );

  if (
    typeof payload !== "object"
    || payload === null
    || !Array.isArray(payload.devices)
  ) {
    throw new ManagementApiError({
      kind: "server",
      message: "The device registry returned an invalid page contract.",
      retryable: true,
    });
  }

  const nextCursor = payload.next_cursor;
  if (
    nextCursor !== null
    && nextCursor !== undefined
    && (typeof nextCursor !== "string" || nextCursor.length === 0)
  ) {
    throw new ManagementApiError({
      kind: "server",
      message: "The device registry returned an invalid pagination cursor.",
      retryable: true,
    });
  }

  return {
    devices: payload.devices as Device[],
    nextCursor: typeof nextCursor === "string" ? nextCursor : undefined,
  };
}
