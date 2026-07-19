import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  createDeviceResource,
  type ApiProblem,
  type Device,
  ManagementApiError,
  retireDeviceResource,
  updateDeviceResource,
} from "../lib/managementApi";
import { listDeviceRegistryPage } from "../lib/deviceRegistryApi";

interface DeviceManagementPanelProps {
  areaDescription: string;
  areaTitle: string;
  moduleName: string;
}

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

function parseJsonObject(
  value: string,
  { stringValuesOnly = false }: { stringValuesOnly?: boolean } = {},
): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value.trim() || "{}");
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new TypeError("expected a JSON object");
  }
  if (stringValuesOnly && Object.values(parsed).some((entry) => typeof entry !== "string")) {
    throw new TypeError("expected string values");
  }
  return parsed as Record<string, unknown>;
}

export function DeviceManagementPanel({
  areaDescription,
  areaTitle,
  moduleName,
}: DeviceManagementPanelProps) {
  const { t } = useI18n();
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadProblem, setLoadProblem] = useState<ApiProblem>();
  const [mutationProblem, setMutationProblem] = useState<ApiProblem>();
  const [successKey, setSuccessKey] = useState<MessageKey>();
  const [reloadKey, setReloadKey] = useState(0);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageCursors, setPageCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const [nextCursor, setNextCursor] = useState<string>();
  const [isSaving, setIsSaving] = useState(false);
  const [isRetiring, setIsRetiring] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [readOnly, setReadOnly] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState<Device["status"]>("provisioning");
  const [mqttTopic, setMqttTopic] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [settingsJson, setSettingsJson] = useState("{}");
  const [labelsJson, setLabelsJson] = useState("{}");

  const selectedDevice = useMemo(
    () => devices.find((device) => device.device_id === selectedId),
    [devices, selectedId],
  );

  function normalizeProblem(error: unknown): ApiProblem {
    return error instanceof ManagementApiError
      ? error.problem
      : { kind: "server", message: t("management.unknownError"), retryable: true };
  }

  function registerMutationProblem(error: unknown) {
    const problem = normalizeProblem(error);
    setMutationProblem(problem);
    if (problem.kind === "authorization") setReadOnly(true);
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setLoadProblem(undefined);
    listDeviceRegistryPage(
      {
        cursor: pageCursors[pageIndex],
        limit: 100,
        query: query || undefined,
      },
      controller.signal,
    )
      .then((page) => {
        setDevices(page.devices);
        setNextCursor(page.nextCursor);
        setSelectedId((current) => (
          page.devices.some((device) => device.device_id === current)
            ? current
            : page.devices[0]?.device_id ?? ""
        ));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoadProblem(normalizeProblem(error));
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  // `t` changes only when the language changes and should refresh error copy.
  }, [pageCursors, pageIndex, query, reloadKey, t]);

  function searchDevices(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setSuccessKey(undefined);
    setPageCursors([undefined]);
    setPageIndex(0);
    setQuery(queryInput.trim());
    setReloadKey((value) => value + 1);
  }

  function showPreviousPage() {
    if (pageIndex === 0) return;
    setIsLoading(true);
    setSuccessKey(undefined);
    setPageIndex((value) => value - 1);
  }

  function showNextPage() {
    if (!nextCursor) return;
    setIsLoading(true);
    setSuccessKey(undefined);
    setPageCursors((current) => {
      const next = current.slice(0, pageIndex + 1);
      next[pageIndex + 1] = nextCursor;
      return next;
    });
    setPageIndex((value) => value + 1);
  }

  useEffect(() => {
    if (!selectedDevice) return;
    setDisplayName(selectedDevice.display_name);
    setKind(selectedDevice.kind);
    setStatus(selectedDevice.status);
    setMqttTopic(selectedDevice.mqtt_topic ?? "");
    setCapabilities((selectedDevice.capabilities ?? []).join(", "));
    setSettingsJson(JSON.stringify(selectedDevice.settings ?? {}, null, 2));
    setLabelsJson(JSON.stringify(selectedDevice.labels ?? {}, null, 2));
    setMutationProblem(undefined);
  }, [selectedDevice?.device_id, selectedDevice?.revision]);

  async function submitDevice(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDevice || selectedDevice.status === "retired") return;
    setIsSaving(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      let parsedSettings: Record<string, unknown>;
      let parsedLabels: Record<string, string>;
      try {
        parsedSettings = parseJsonObject(settingsJson);
        parsedLabels = parseJsonObject(labelsJson, { stringValuesOnly: true }) as Record<string, string>;
      } catch {
        setMutationProblem({
          kind: "validation",
          message: t("management.device.jsonObjectError"),
          retryable: false,
        });
        return;
      }
      const updated = await updateDeviceResource(selectedDevice, {
        display_name: displayName.trim(),
        kind: kind.trim(),
        status,
        mqtt_topic: mqttTopic.trim() || null,
        capabilities: [...new Set(
          capabilities.split(",").map((value) => value.trim()).filter(Boolean),
        )],
        settings: parsedSettings,
        labels: parsedLabels,
      });
      setDevices((current) => current.map((device) => (
        device.device_id === updated.device_id ? updated : device
      )));
      setSuccessKey("management.device.saved");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      setIsSaving(false);
    }
  }

  async function retireDevice() {
    if (!selectedDevice || selectedDevice.status === "retired") return;
    if (!window.confirm(t("management.device.retireConfirm", { device: selectedDevice.display_name }))) return;
    setIsRetiring(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      await retireDeviceResource(selectedDevice);
      setSuccessKey("management.device.retired");
      setReloadKey((value) => value + 1);
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      setIsRetiring(false);
    }
  }

  async function createDevice(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setIsCreating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      await createDeviceResource({
        device_id: String(form.get("device_id") ?? "").trim(),
        display_name: String(form.get("display_name") ?? "").trim(),
        kind: String(form.get("kind") ?? "").trim(),
        status: "provisioning",
      });
      formElement.reset();
      setQueryInput("");
      setQuery("");
      setPageCursors([undefined]);
      setPageIndex(0);
      setReloadKey((value) => value + 1);
      setSuccessKey("management.device.created");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>/dealiot/api/devices</code>
          <button
            onClick={() => {
              setIsLoading(true);
              setReloadKey((value) => value + 1);
            }}
            type="button"
          >
            {t("management.retry")}
          </button>
        </div>

        <form className="management-search" onSubmit={searchDevices} role="search">
          <label>
            <span>{t("management.device.searchLabel")}</span>
            <input
              maxLength={160}
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder={t("management.device.searchPlaceholder")}
              value={queryInput}
            />
          </label>
          <button type="submit">{t("management.device.search")}</button>
        </form>

        {isLoading ? <p className="management-state">{t("management.loading")}</p> : null}
        {loadProblem ? (
          <div className={`management-notice management-notice--${loadProblem.kind}`} role="alert">
            <strong>{t(`management.error.${loadProblem.kind}` as MessageKey)}</strong>
            <p>{loadProblem.message}</p>
            {loadProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}
        {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}

        {!isLoading && !loadProblem && devices.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.emptyDetail")}</p>
          </div>
        ) : null}

        {devices.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("management.device.listAria")} className="management-selector">
              {devices.map((device) => (
                <button
                  aria-current={device.device_id === selectedId ? "true" : undefined}
                  className={device.device_id === selectedId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  key={device.device_id}
                  onClick={() => {
                    setSuccessKey(undefined);
                    setSelectedId(device.device_id);
                  }}
                  type="button"
                >
                  <strong>{device.display_name}</strong>
                  <code>{device.device_id}</code>
                  <span>{t("management.deviceMeta", { kind: device.kind, revision: device.revision, status: device.status })}</span>
                </button>
              ))}
            </nav>

            {selectedDevice ? (
              <form
                className="management-detail-form"
                onChange={() => setSuccessKey(undefined)}
                onSubmit={submitDevice}
              >
                <div className="management-detail-form__heading">
                  <div>
                    <h3>{t("management.device.editTitle")}</h3>
                    <code>{selectedDevice.device_id} · ETag &quot;{selectedDevice.revision}&quot;</code>
                  </div>
                  <span className="management-revision">{selectedDevice.kind}</span>
                </div>
                <label>
                  <span>{t("management.form.displayName")}</span>
                  <input disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setDisplayName(event.target.value)} required value={displayName} />
                </label>
                <label>
                  <span>{t("management.form.kind")}</span>
                  <input disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setKind(event.target.value)} required value={kind} />
                </label>
                <label>
                  <span>{t("management.device.status")}</span>
                  <select disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setStatus(event.target.value as Device["status"])} value={status}>
                    <option value="provisioning">{t("management.device.status.provisioning")}</option>
                    <option value="active">{t("management.device.status.active")}</option>
                    <option value="suspended">{t("management.device.status.suspended")}</option>
                    {selectedDevice.status === "retired" ? <option value="retired">{t("management.device.status.retired")}</option> : null}
                  </select>
                </label>
                <label className="management-detail-form__wide">
                  <span>{t("management.device.mqttTopic")}</span>
                  <input disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setMqttTopic(event.target.value)} placeholder="devices/example/telemetry" value={mqttTopic} />
                </label>
                <label className="management-detail-form__wide">
                  <span>{t("management.device.capabilities")}</span>
                  <input disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setCapabilities(event.target.value)} placeholder="gps, temperature" value={capabilities} />
                </label>
                <label className="management-detail-form__wide">
                  <span>{t("management.device.settings")}</span>
                  <textarea disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setSettingsJson(event.target.value)} rows={5} spellCheck={false} value={settingsJson} />
                </label>
                <label className="management-detail-form__wide">
                  <span>{t("management.device.labels")}</span>
                  <textarea disabled={readOnly || selectedDevice.status === "retired"} onChange={(event) => setLabelsJson(event.target.value)} rows={4} spellCheck={false} value={labelsJson} />
                </label>
                <p className="management-detail-form__help">{t("management.device.configurationHelp")}</p>
                <p className="management-detail-form__help">{t("management.device.etagHelp")}</p>
                {mutationProblem ? (
                  <div className={`management-notice management-notice--${mutationProblem.kind}`} role="alert">
                    <strong>{t(`management.error.${mutationProblem.kind}` as MessageKey)}</strong>
                    <p>{mutationProblem.message}</p>
                    {mutationProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
                  </div>
                ) : null}
                {selectedDevice.status === "retired" ? (
                  <p className="management-detail-form__help">{t("management.device.retiredReadOnly")}</p>
                ) : (
                  <div className="management-detail-form__actions">
                    <button disabled={readOnly || isSaving || isRetiring} type="submit">
                      {isSaving ? t("management.saving") : t("management.save")}
                    </button>
                    <button className="management-button--danger" disabled={readOnly || isSaving || isRetiring} onClick={retireDevice} type="button">
                      {isRetiring ? t("management.device.retiring") : t("management.device.retire")}
                    </button>
                  </div>
                )}
              </form>
            ) : null}
          </div>
        ) : null}

        {!loadProblem && (devices.length > 0 || pageIndex > 0) ? (
          <nav
            aria-label={t("management.device.paginationAria")}
            className="management-pagination"
          >
            <button disabled={isLoading || pageIndex === 0} onClick={showPreviousPage} type="button">
              {t("management.device.previousPage")}
            </button>
            <span>{t("management.device.page", { page: pageIndex + 1 })}</span>
            <button disabled={isLoading || !nextCursor} onClick={showNextPage} type="button">
              {t("management.device.nextPage")}
            </button>
          </nav>
        ) : null}

        {!readOnly ? (
          <form
            className="management-form"
            onChange={() => setSuccessKey(undefined)}
            onSubmit={createDevice}
          >
            <h3>{t("management.device.createTitle")}</h3>
            <label>
              <span>{t("management.form.deviceId")}</span>
              <input name="device_id" required />
            </label>
            <label>
              <span>{t("management.form.displayName")}</span>
              <input name="display_name" required />
            </label>
            <label>
              <span>{t("management.form.kind")}</span>
              <input name="kind" required />
            </label>
            <button disabled={isCreating} type="submit">
              {isCreating ? t("management.creating") : t("management.create")}
            </button>
          </form>
        ) : (
          <div className="management-notice management-notice--authorization">
            <strong>{t("management.readOnlyTitle")}</strong>
            <p>{t("management.readOnlyDetail")}</p>
          </div>
        )}
      </div>
    </article>
  );
}
