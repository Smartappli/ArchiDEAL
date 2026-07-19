import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import { type ApiProblem, ManagementApiError } from "../lib/managementApi";
import {
  createExperiment,
  createGpsSensor,
  createSensor,
  deleteExperiment,
  deleteGpsSensor,
  deleteSensor,
  type ExperimentPayload,
  type ExperimentResource,
  type GpsFixResource,
  type GpsSensorPayload,
  type GpsSensorResource,
  listExperiments,
  listGpsFixes,
  listGpsSensors,
  listSensorEvents,
  listSensors,
  type SensorEventResource,
  type SensorPayload,
  type SensorResource,
  updateExperiment,
  updateGpsSensor,
  updateSensor,
} from "../lib/scientificApi";

export type ScientificResourceKind = "experiments" | "gps" | "sensors";
type ScientificResource = ExperimentResource | GpsSensorResource | SensorResource;
type ScientificEvent = GpsFixResource | SensorEventResource;
type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;
type MutationKind = "create" | "delete" | "save";

interface ScientificManagementPanelProps {
  areaDescription: string;
  areaTitle: string;
  kind: ScientificResourceKind;
  moduleName: string;
}

interface EditorValues {
  active: boolean;
  code: string;
  frequency: string;
  model: string;
  observedObjects: string;
  project: string;
  purchaseDate: string;
  simCard: string;
  vendor: string;
}

const collectionPaths: Record<ScientificResourceKind, string> = {
  experiments: "/dealdata/core/api/experiments/",
  gps: "/dealdata/gps/api/gps-sensors/",
  sensors: "/dealdata/sensor/api/sensors/",
};

function emptyValues(): EditorValues {
  return {
    active: true,
    code: "",
    frequency: "",
    model: "",
    observedObjects: "",
    project: "",
    purchaseDate: "",
    simCard: "",
    vendor: "",
  };
}

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

function identifiers(value: string) {
  return [...new Set(value.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean))];
}

function valuesFor(kind: ScientificResourceKind, resource: ScientificResource): EditorValues {
  const values = emptyValues();
  if (kind === "experiments") {
    const experiment = resource as ExperimentResource;
    values.project = experiment.project;
    values.observedObjects = experiment.observed_objects.join("\n");
  } else if (kind === "sensors") {
    const sensor = resource as SensorResource;
    values.code = sensor.code;
    values.vendor = sensor.vendor;
    values.model = sensor.model;
  } else {
    const gps = resource as GpsSensorResource;
    values.code = gps.code;
    values.purchaseDate = gps.purchase_date;
    values.frequency = String(gps.frequency);
    values.vendor = gps.vendor;
    values.model = gps.model;
    values.simCard = gps.sim_card;
    values.active = gps.active;
  }
  return values;
}

function payloadFor(kind: ScientificResourceKind, values: EditorValues) {
  if (kind === "experiments") {
    return {
      project: values.project.trim(),
      observed_objects: identifiers(values.observedObjects),
    } satisfies ExperimentPayload;
  }
  if (kind === "sensors") {
    return {
      code: values.code.trim(),
      vendor: values.vendor.trim(),
      model: values.model.trim(),
    } satisfies SensorPayload;
  }
  return {
    code: values.code.trim(),
    purchase_date: values.purchaseDate,
    frequency: Number(values.frequency),
    vendor: values.vendor.trim(),
    model: values.model.trim(),
    sim_card: values.simCard.trim(),
    active: values.active,
  } satisfies GpsSensorPayload;
}

async function loadResources(kind: ScientificResourceKind, signal?: AbortSignal): Promise<ScientificResource[]> {
  if (kind === "experiments") return listExperiments(signal);
  if (kind === "sensors") return listSensors(signal);
  return listGpsSensors(signal);
}

async function createResource(kind: ScientificResourceKind, values: EditorValues) {
  const payload = payloadFor(kind, values);
  if (kind === "experiments") return createExperiment(payload as ExperimentPayload);
  if (kind === "sensors") return createSensor(payload as SensorPayload);
  return createGpsSensor(payload as GpsSensorPayload);
}

async function updateResource(kind: ScientificResourceKind, id: string, values: EditorValues) {
  const payload = payloadFor(kind, values);
  if (kind === "experiments") return updateExperiment(id, payload as ExperimentPayload);
  if (kind === "sensors") return updateSensor(id, payload as SensorPayload);
  return updateGpsSensor(id, payload as GpsSensorPayload);
}

async function removeResource(kind: ScientificResourceKind, id: string) {
  if (kind === "experiments") return deleteExperiment(id);
  if (kind === "sensors") return deleteSensor(id);
  return deleteGpsSensor(id);
}

function resourceTitle(kind: ScientificResourceKind, resource: ScientificResource, t: Translate) {
  if (kind === "experiments") return t("scientific.resource.experiment", { id: resource.id.slice(0, 8) });
  return (resource as SensorResource | GpsSensorResource).code;
}

function resourceMeta(kind: ScientificResourceKind, resource: ScientificResource, t: Translate) {
  if (kind === "experiments") {
    const experiment = resource as ExperimentResource;
    return t("scientific.resource.experimentMeta", {
      count: experiment.observed_objects.length,
      project: experiment.project,
    });
  }
  if (kind === "sensors") {
    const sensor = resource as SensorResource;
    return `${sensor.vendor} · ${sensor.model}`;
  }
  const gps = resource as GpsSensorResource;
  return t("scientific.resource.gpsMeta", {
    frequency: gps.frequency,
    status: t(gps.active ? "scientific.resource.active" : "scientific.resource.inactive"),
  });
}

function ResourceFields({
  disabled,
  kind,
  onChange,
  values,
}: {
  disabled: boolean;
  kind: ScientificResourceKind;
  onChange: React.Dispatch<React.SetStateAction<EditorValues>>;
  values: EditorValues;
}) {
  const { t } = useI18n();
  const set = <K extends keyof EditorValues>(key: K, value: EditorValues[K]) => {
    onChange((current) => ({ ...current, [key]: value }));
  };

  if (kind === "experiments") {
    return (
      <>
        <label>
          <span>{t("scientific.form.project")}</span>
          <input disabled={disabled} onChange={(event) => set("project", event.target.value)} required value={values.project} />
        </label>
        <label className="management-detail-form__wide">
          <span>{t("scientific.form.observedObjects")}</span>
          <textarea disabled={disabled} onChange={(event) => set("observedObjects", event.target.value)} rows={4} value={values.observedObjects} />
        </label>
        <p className="management-detail-form__help">{t("scientific.form.identifiersHelp")}</p>
      </>
    );
  }

  return (
    <>
      <label>
        <span>{t("scientific.form.code")}</span>
        <input disabled={disabled} onChange={(event) => set("code", event.target.value)} required value={values.code} />
      </label>
      <label>
        <span>{t("scientific.form.vendor")}</span>
        <input disabled={disabled} onChange={(event) => set("vendor", event.target.value)} required={kind === "sensors"} value={values.vendor} />
      </label>
      <label>
        <span>{t("scientific.form.model")}</span>
        <input disabled={disabled} onChange={(event) => set("model", event.target.value)} required={kind === "sensors"} value={values.model} />
      </label>
      {kind === "gps" ? (
        <>
          <label>
            <span>{t("scientific.form.purchaseDate")}</span>
            <input disabled={disabled} onChange={(event) => set("purchaseDate", event.target.value)} required type="date" value={values.purchaseDate} />
          </label>
          <label>
            <span>{t("scientific.form.frequency")}</span>
            <input disabled={disabled} min="0" onChange={(event) => set("frequency", event.target.value)} required step="any" type="number" value={values.frequency} />
          </label>
          <label>
            <span>{t("scientific.form.simCard")}</span>
            <input disabled={disabled} onChange={(event) => set("simCard", event.target.value)} value={values.simCard} />
          </label>
          <label className="management-checkbox management-detail-form__wide">
            <input checked={values.active} disabled={disabled} onChange={(event) => set("active", event.target.checked)} type="checkbox" />
            <span>{t("scientific.form.active")}</span>
          </label>
        </>
      ) : null}
    </>
  );
}

function eventTitle(event: ScientificEvent) {
  return `${event.device_id} · ${event.timestamp}`;
}

function eventMeta(kind: ScientificResourceKind, event: ScientificEvent, t: Translate) {
  if (kind === "sensors") return (event as SensorEventResource).sensor_type || t("scientific.events.sensor");
  const fix = event as GpsFixResource;
  return fix.latitude === null || fix.longitude === null
    ? t("scientific.events.positionUnavailable")
    : `${fix.latitude}, ${fix.longitude}`;
}

export function ScientificManagementPanel({
  areaDescription,
  areaTitle,
  kind,
  moduleName,
}: ScientificManagementPanelProps) {
  const { t } = useI18n();
  const [resources, setResources] = useState<ScientificResource[]>([]);
  const [events, setEvents] = useState<ScientificEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [editValues, setEditValues] = useState<EditorValues>(emptyValues);
  const [createValues, setCreateValues] = useState<EditorValues>(emptyValues);
  const [loadProblem, setLoadProblem] = useState<ApiProblem>();
  const [eventProblem, setEventProblem] = useState<ApiProblem>();
  const [mutationProblem, setMutationProblem] = useState<ApiProblem>();
  const [successKey, setSuccessKey] = useState<MessageKey>();
  const [isLoading, setIsLoading] = useState(true);
  const [isEventsLoading, setIsEventsLoading] = useState(kind !== "experiments");
  const [mutationKind, setMutationKind] = useState<MutationKind>();
  const mutationInFlight = useRef(false);
  const [readOnly, setReadOnly] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const isMutating = mutationKind !== undefined;

  const selectedResource = useMemo(
    () => resources.find((resource) => resource.id === selectedId),
    [resources, selectedId],
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

  function beginMutation(nextKind: MutationKind) {
    if (mutationInFlight.current) return false;
    mutationInFlight.current = true;
    setMutationKind(nextKind);
    return true;
  }

  function finishMutation() {
    mutationInFlight.current = false;
    setMutationKind(undefined);
  }

  function refresh() {
    if (isLoading || isEventsLoading || isMutating) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    setReloadKey((value) => value + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setLoadProblem(undefined);
    loadResources(kind, controller.signal)
      .then((nextResources) => {
        if (!active) return;
        setResources(nextResources);
        setSelectedId((current) => (
          nextResources.some((resource) => resource.id === current)
            ? current
            : nextResources[0]?.id
        ));
      })
      .catch((error: unknown) => {
        if (!active || (error instanceof DOMException && error.name === "AbortError")) return;
        setResources([]);
        setSelectedId(undefined);
        setLoadProblem(normalizeProblem(error));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [kind, reloadKey, t]);

  useEffect(() => {
    if (kind === "experiments") {
      setEvents([]);
      setEventProblem(undefined);
      setIsEventsLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    setIsEventsLoading(true);
    setEvents([]);
    setEventProblem(undefined);
    const request = kind === "sensors"
      ? listSensorEvents(controller.signal)
      : listGpsFixes(controller.signal);
    request
      .then((nextEvents) => {
        if (active) setEvents(nextEvents);
      })
      .catch((error: unknown) => {
        if (!active || (error instanceof DOMException && error.name === "AbortError")) return;
        setEventProblem(normalizeProblem(error));
      })
      .finally(() => {
        if (active) setIsEventsLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [kind, reloadKey, t]);

  useEffect(() => {
    if (!selectedResource) return;
    setEditValues(valuesFor(kind, selectedResource));
    setMutationProblem(undefined);
  }, [kind, selectedResource]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!beginMutation("create")) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      const created = await createResource(kind, createValues);
      setResources((current) => [...current, created]);
      setSelectedId(created.id);
      setCreateValues(emptyValues());
      setSuccessKey("scientific.created");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      finishMutation();
    }
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedResource) return;
    if (!beginMutation("save")) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      const updated = await updateResource(kind, selectedResource.id, editValues);
      setResources((current) => current.map((resource) => (
        resource.id === updated.id ? updated : resource
      )));
      setSuccessKey("scientific.saved");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      finishMutation();
    }
  }

  async function remove() {
    if (!selectedResource) return;
    if (!window.confirm(t("scientific.deleteConfirm", { resource: resourceTitle(kind, selectedResource, t) }))) return;
    if (!beginMutation("delete")) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    const deletedId = selectedResource.id;
    const nextSelectedId = resources.find((resource) => resource.id !== deletedId)?.id;
    try {
      await removeResource(kind, deletedId);
      setResources((current) => current.filter((resource) => resource.id !== deletedId));
      setSelectedId(nextSelectedId);
      setSuccessKey("scientific.deleted");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      finishMutation();
    }
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>{collectionPaths[kind]}</code>
          <button disabled={isLoading || isEventsLoading || isMutating} onClick={refresh} type="button">
            {t("management.retry")}
          </button>
        </div>

        {isLoading ? <p className="management-state">{t("management.loading")}</p> : null}
        {loadProblem ? (
          <div className={`management-notice management-notice--${loadProblem.kind}`} role="alert">
            <strong>{t(`management.error.${loadProblem.kind}` as MessageKey)}</strong>
            <p>{loadProblem.message}</p>
            {loadProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}
        {mutationProblem ? (
          <div className={`management-notice management-notice--${mutationProblem.kind}`} role="alert">
            <strong>{t(`management.error.${mutationProblem.kind}` as MessageKey)}</strong>
            <p>{mutationProblem.message}</p>
            {mutationProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}
        {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}

        {!isLoading && !loadProblem && resources.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.emptyDetail")}</p>
          </div>
        ) : null}

        {resources.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("scientific.listAria")} className="management-selector">
              {resources.map((resource) => (
                <button
                  aria-current={resource.id === selectedId ? "true" : undefined}
                  className={resource.id === selectedId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  disabled={isLoading || isMutating || Boolean(loadProblem)}
                  key={resource.id}
                  onClick={() => setSelectedId(resource.id)}
                  type="button"
                >
                  <strong>{resourceTitle(kind, resource, t)}</strong>
                  <code>{resource.id}</code>
                  <span>{resourceMeta(kind, resource, t)}</span>
                </button>
              ))}
            </nav>

            {selectedResource ? (
              <form className="management-detail-form" onChange={() => setSuccessKey(undefined)} onSubmit={save}>
                <div className="management-detail-form__heading">
                  <div>
                    <h3>{t("scientific.editTitle")}</h3>
                    <code>{selectedResource.id}</code>
                  </div>
                </div>
                <ResourceFields
                  disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)}
                  kind={kind}
                  onChange={setEditValues}
                  values={editValues}
                />
                {kind !== "experiments" ? (
                  <p className="management-detail-form__help">{t("scientific.deleteProtectedHelp")}</p>
                ) : null}
                <div className="management-detail-form__actions">
                  <button disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)} type="submit">
                    {mutationKind === "save" ? t("management.saving") : t("management.save")}
                  </button>
                  <button
                    className="management-button--danger"
                    disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)}
                    onClick={remove}
                    type="button"
                  >
                    {mutationKind === "delete" ? t("scientific.deleting") : t("scientific.delete")}
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        ) : null}

        {!readOnly ? (
          <form className="management-form" onChange={() => setSuccessKey(undefined)} onSubmit={create}>
            <h3>{t("scientific.createTitle")}</h3>
            <ResourceFields
              disabled={isLoading || isMutating || Boolean(loadProblem)}
              kind={kind}
              onChange={setCreateValues}
              values={createValues}
            />
            <button disabled={isLoading || isMutating || Boolean(loadProblem)} type="submit">
              {mutationKind === "create" ? t("management.creating") : t("management.create")}
            </button>
          </form>
        ) : (
          <div className="management-notice management-notice--authorization">
            <strong>{t("management.readOnlyTitle")}</strong>
            <p>{t("management.readOnlyDetail")}</p>
          </div>
        )}

        {kind !== "experiments" ? (
          <section aria-labelledby={`scientific-events-${kind}`}>
            <h3 id={`scientific-events-${kind}`}>{t("scientific.events.title")}</h3>
            <p>{t("scientific.events.help")}</p>
            {isEventsLoading ? <p className="management-state" role="status">{t("management.loading")}</p> : null}
            {eventProblem ? <p className="management-state" role="alert">{eventProblem.message}</p> : null}
            {!isEventsLoading && !eventProblem && events.length === 0 ? <p className="management-state">{t("scientific.events.empty")}</p> : null}
            {events.length > 0 ? (
              <ul className="management-list">
                {events.map((event) => (
                  <li key={event.id}>
                    <div>
                      <strong>{eventTitle(event)}</strong>
                      <code>{event.observed_object_id ?? event.id}</code>
                    </div>
                    <p>{eventMeta(kind, event, t)}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}
      </div>
    </article>
  );
}
