import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  type ApiProblem,
  createDatasetResource,
  deleteDatasetResource,
  type Dataset,
  listAllDatasetResources,
  ManagementApiError,
  updateDatasetResource,
} from "../lib/managementApi";

interface DatasetManagementPanelProps {
  areaDescription: string;
  areaTitle: string;
  moduleName: string;
}

type DatasetMutationKind = "create" | "delete" | "save";

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

export function DatasetManagementPanel({
  areaDescription,
  areaTitle,
  moduleName,
}: DatasetManagementPanelProps) {
  const { t } = useI18n();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [isLoading, setIsLoading] = useState(true);
  const [loadProblem, setLoadProblem] = useState<ApiProblem>();
  const [mutationProblem, setMutationProblem] = useState<ApiProblem>();
  const [successKey, setSuccessKey] = useState<MessageKey>();
  const [reloadKey, setReloadKey] = useState(0);
  const [mutationKind, setMutationKind] = useState<DatasetMutationKind>();
  const mutationInFlight = useRef(false);
  const [readOnly, setReadOnly] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(true);
  const isMutating = mutationKind !== undefined;

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedId),
    [datasets, selectedId],
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

  function beginMutation(nextKind: DatasetMutationKind) {
    if (mutationInFlight.current) return false;
    mutationInFlight.current = true;
    setMutationKind(nextKind);
    return true;
  }

  function finishMutation() {
    mutationInFlight.current = false;
    setMutationKind(undefined);
  }

  function refreshDatasets() {
    if (isLoading || isMutating) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    setReloadKey((value) => value + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setLoadProblem(undefined);
    listAllDatasetResources(controller.signal)
      .then((nextDatasets) => {
        if (!active) return;
        setDatasets(nextDatasets);
        setSelectedId((current) => (
          nextDatasets.some((dataset) => dataset.id === current)
            ? current
            : nextDatasets[0]?.id
        ));
      })
      .catch((error: unknown) => {
        if (!active || (error instanceof DOMException && error.name === "AbortError")) return;
        setDatasets([]);
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
  }, [reloadKey, t]);

  useEffect(() => {
    if (!selectedDataset) return;
    setName(selectedDataset.name);
    setDescription(selectedDataset.description);
    setEnabled(selectedDataset.enabled);
    setMutationProblem(undefined);
  }, [selectedDataset?.id, selectedDataset?.revision]);

  async function updateDataset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDataset) return;
    if (!beginMutation("save")) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      const updated = await updateDatasetResource(selectedDataset, {
        name: name.trim(),
        description: description.trim(),
        enabled,
      });
      setDatasets((current) => current.map((dataset) => (
        dataset.id === updated.id ? updated : dataset
      )));
      setSuccessKey("management.dataset.saved");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      finishMutation();
    }
  }

  async function createDataset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    if (!beginMutation("create")) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      const created = await createDatasetResource({
        name: String(form.get("name") ?? "").trim(),
        slug: String(form.get("slug") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
        enabled: form.get("enabled") === "on",
      });
      setDatasets((current) => [...current, created]);
      setSelectedId(created.id);
      formElement.reset();
      setSuccessKey("management.dataset.created");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      finishMutation();
    }
  }

  async function deleteDataset() {
    if (!selectedDataset) return;
    if (!window.confirm(t("management.dataset.deleteConfirm", { dataset: selectedDataset.name }))) return;
    if (!beginMutation("delete")) return;
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    const deletedId = selectedDataset.id;
    const nextSelectedId = datasets.find((dataset) => dataset.id !== deletedId)?.id;
    try {
      await deleteDatasetResource(selectedDataset);
      setDatasets((current) => current.filter((dataset) => dataset.id !== deletedId));
      setSelectedId(nextSelectedId);
      setSuccessKey("management.dataset.deleted");
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
          <code>/dealhost/api/hosting/datasets/</code>
          <button disabled={isLoading || isMutating} onClick={refreshDatasets} type="button">
            {t("management.retry")}
          </button>
        </div>

        <div className="management-notice management-notice--neutral">
          <strong>{t("management.dataset.scopeTitle")}</strong>
          <p>{t("management.dataset.scopeDetail")}</p>
        </div>

        {isLoading ? <p className="management-state">{t("management.loading")}</p> : null}
        {loadProblem ? (
          <div className={`management-notice management-notice--${loadProblem.kind}`} role="alert">
            <strong>{t(`management.error.${loadProblem.kind}` as MessageKey)}</strong>
            <p>{loadProblem.message}</p>
            {loadProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}
        {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}

        {!isLoading && !loadProblem && datasets.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.emptyDetail")}</p>
          </div>
        ) : null}

        {datasets.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("management.dataset.listAria")} className="management-selector">
              {datasets.map((dataset) => (
                <button
                  aria-current={dataset.id === selectedId ? "true" : undefined}
                  className={dataset.id === selectedId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  disabled={isLoading || isMutating || Boolean(loadProblem)}
                  key={dataset.id}
                  onClick={() => {
                    setMutationProblem(undefined);
                    setSuccessKey(undefined);
                    setSelectedId(dataset.id);
                  }}
                  type="button"
                >
                  <strong>{dataset.name}</strong>
                  <code>{dataset.slug}</code>
                  <span>{t("management.dataset.revision", { revision: dataset.revision })}</span>
                </button>
              ))}
            </nav>

            {selectedDataset ? (
              <form
                className="management-detail-form"
                onChange={() => setSuccessKey(undefined)}
                onSubmit={updateDataset}
              >
                <div className="management-detail-form__heading">
                  <div>
                    <h3>{t("management.dataset.editTitle")}</h3>
                    <code>{selectedDataset.slug}</code>
                  </div>
                  <span className="management-revision">
                    {t("management.dataset.revision", { revision: selectedDataset.revision })}
                  </span>
                </div>
                <label>
                  <span>{t("management.form.name")}</span>
                  <input disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)} onChange={(event) => setName(event.target.value)} required value={name} />
                </label>
                <label className="management-detail-form__wide">
                  <span>{t("management.form.description")}</span>
                  <textarea disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)} onChange={(event) => setDescription(event.target.value)} rows={4} value={description} />
                </label>
                <label className="management-checkbox management-detail-form__wide">
                  <input checked={enabled} disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
                  <span>{t("management.dataset.enabled")}</span>
                </label>
                <p className="management-detail-form__help">{t("management.dataset.etagHelp")}</p>
                {mutationProblem ? (
                  <div className={`management-notice management-notice--${mutationProblem.kind}`} role="alert">
                    <strong>{t(`management.error.${mutationProblem.kind}` as MessageKey)}</strong>
                    <p>{mutationProblem.message}</p>
                    {mutationProblem.kind === "conflict" ? (
                      <>
                        <p>{t("management.dataset.conflictHelp")}</p>
                        <button disabled={isLoading || isMutating} onClick={refreshDatasets} type="button">
                          {t("management.dataset.reloadAfterConflict")}
                        </button>
                      </>
                    ) : null}
                    {mutationProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
                  </div>
                ) : null}
                <div className="management-detail-form__actions">
                  <button disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)} type="submit">
                    {mutationKind === "save" ? t("management.saving") : t("management.save")}
                  </button>
                  <button
                    className="management-button--danger"
                    disabled={readOnly || isLoading || isMutating || Boolean(loadProblem)}
                    onClick={deleteDataset}
                    type="button"
                  >
                    {mutationKind === "delete" ? t("management.dataset.deleting") : t("management.dataset.delete")}
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        ) : null}

        {!readOnly ? (
          <form
            className="management-form"
            onChange={() => setSuccessKey(undefined)}
            onSubmit={createDataset}
          >
            <h3>{t("management.dataset.createTitle")}</h3>
            <label>
              <span>{t("management.form.name")}</span>
              <input disabled={isLoading || isMutating || Boolean(loadProblem)} name="name" required />
            </label>
            <label>
              <span>{t("management.form.slug")}</span>
              <input disabled={isLoading || isMutating || Boolean(loadProblem)} name="slug" required />
            </label>
            <label>
              <span>{t("management.form.description")}</span>
              <textarea disabled={isLoading || isMutating || Boolean(loadProblem)} name="description" rows={3} />
            </label>
            <label className="management-checkbox">
              <input defaultChecked disabled={isLoading || isMutating || Boolean(loadProblem)} name="enabled" type="checkbox" />
              <span>{t("management.dataset.enabled")}</span>
            </label>
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
      </div>
    </article>
  );
}
