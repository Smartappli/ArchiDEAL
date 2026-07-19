import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  createManagementResource,
  type ApiProblem,
  type HostedApplication,
  listManagementResources,
  ManagementApiError,
  publishHostedApplicationVersion,
  updateHostedApplicationResource,
} from "../lib/managementApi";

interface ApplicationManagementPanelProps {
  areaDescription: string;
  areaTitle: string;
  mode: "applications" | "releases";
  moduleName: string;
}

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

export function ApplicationManagementPanel({
  areaDescription,
  areaTitle,
  mode,
  moduleName,
}: ApplicationManagementPanelProps) {
  const { t } = useI18n();
  const [applications, setApplications] = useState<HostedApplication[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [isLoading, setIsLoading] = useState(true);
  const [loadProblem, setLoadProblem] = useState<ApiProblem>();
  const [mutationProblem, setMutationProblem] = useState<ApiProblem>();
  const [successKey, setSuccessKey] = useState<MessageKey>();
  const [reloadKey, setReloadKey] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [readOnly, setReadOnly] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(true);

  const selectedApplication = useMemo(
    () => applications.find((application) => application.id === selectedId),
    [applications, selectedId],
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
    listManagementResources<HostedApplication>(
      "/dealhost/api/hosting/applications/",
      controller.signal,
    )
      .then((nextApplications) => {
        setApplications(nextApplications);
        setSelectedId((current) => (
          nextApplications.some((application) => application.id === current)
            ? current
            : nextApplications[0]?.id
        ));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoadProblem(normalizeProblem(error));
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  }, [reloadKey, t]);

  useEffect(() => {
    if (!selectedApplication) return;
    setName(selectedApplication.name);
    setDescription(selectedApplication.description);
    setEnabled(selectedApplication.enabled);
  }, [selectedApplication?.id, selectedApplication?.revision]);

  useEffect(() => {
    setMutationProblem(undefined);
    setSuccessKey(undefined);
  }, [selectedApplication?.id]);

  async function updateApplication(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication) return;
    setIsSaving(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      const updated = await updateHostedApplicationResource(selectedApplication, {
        name: name.trim(),
        description: description.trim(),
        enabled,
      });
      setApplications((current) => current.map((application) => (
        application.id === updated.id ? updated : application
      )));
      setSuccessKey("management.application.saved");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      setIsSaving(false);
    }
  }

  async function createApplication(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setIsCreating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      const created = await createManagementResource<HostedApplication>(
        "/dealhost/api/hosting/applications/",
        {
          name: String(form.get("name") ?? "").trim(),
          slug: String(form.get("slug") ?? "").trim(),
          description: String(form.get("description") ?? "").trim(),
          enabled: true,
        },
      );
      setApplications((current) => [...current, created]);
      setSelectedId(created.id);
      formElement.reset();
      setSuccessKey("management.application.created");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      setIsCreating(false);
    }
  }

  async function publishVersion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setIsSaving(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    try {
      await publishHostedApplicationVersion(selectedApplication, {
        version: String(form.get("version") ?? "").trim(),
        notes: String(form.get("notes") ?? "").trim(),
        source: String(form.get("source") ?? "").trim() || "manual",
      });
      // The publication endpoint is idempotent: replaying an older, identical
      // version returns that immutable record without moving the catalog's
      // current-version pointer. Reload the authoritative application instead
      // of assuming every successful response advanced it.
      setReloadKey((value) => value + 1);
      formElement.reset();
      setSuccessKey("management.release.published");
    } catch (error) {
      registerMutationProblem(error);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>/dealhost/api/hosting/applications/</code>
          <button onClick={() => setReloadKey((value) => value + 1)} type="button">
            {t("management.retry")}
          </button>
        </div>

        {mode === "releases" ? (
          <div className="management-notice management-notice--neutral">
            <strong>{t("management.release.noticeTitle")}</strong>
            <p>{t("management.release.noticeDetail")}</p>
          </div>
        ) : null}

        {isLoading ? <p className="management-state">{t("management.loading")}</p> : null}
        {loadProblem ? (
          <div className={`management-notice management-notice--${loadProblem.kind}`} role="alert">
            <strong>{t(`management.error.${loadProblem.kind}` as MessageKey)}</strong>
            <p>{loadProblem.message}</p>
            {loadProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}

        {!isLoading && !loadProblem && applications.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.emptyDetail")}</p>
          </div>
        ) : null}

        {applications.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("management.application.listAria")} className="management-selector">
              {applications.map((application) => (
                <button
                  aria-current={application.id === selectedId ? "true" : undefined}
                  className={application.id === selectedId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  key={application.id}
                  onClick={() => setSelectedId(application.id)}
                  type="button"
                >
                  <strong>{application.name}</strong>
                  <code>{application.slug}</code>
                  <span>{t("management.applicationMeta", { version: application.current_version || t("management.noRelease") })}</span>
                </button>
              ))}
            </nav>

            {selectedApplication && mode === "applications" ? (
              <form
                className="management-detail-form"
                onChange={() => setSuccessKey(undefined)}
                onSubmit={updateApplication}
              >
                <div className="management-detail-form__heading">
                  <div>
                    <h3>{t("management.application.editTitle")}</h3>
                    <code>{selectedApplication.slug}</code>
                  </div>
                  <span className="management-revision">
                    {t("management.application.revision", {
                      revision: selectedApplication.revision,
                    })}
                  </span>
                </div>
                <label>
                  <span>{t("management.form.name")}</span>
                  <input disabled={readOnly} onChange={(event) => setName(event.target.value)} required value={name} />
                </label>
                <label className="management-detail-form__wide">
                  <span>{t("management.form.description")}</span>
                  <textarea disabled={readOnly} onChange={(event) => setDescription(event.target.value)} rows={4} value={description} />
                </label>
                <label className="management-checkbox management-detail-form__wide">
                  <input checked={enabled} disabled={readOnly} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
                  <span>{t("management.application.enabled")}</span>
                </label>
                <p className="management-detail-form__help">
                  {t("management.application.etagHelp")}
                </p>
                {mutationProblem ? (
                  <div className={`management-notice management-notice--${mutationProblem.kind}`} role="alert">
                    <strong>{t(`management.error.${mutationProblem.kind}` as MessageKey)}</strong>
                    <p>{mutationProblem.message}</p>
                    {mutationProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
                    {mutationProblem.status === 412 ? (
                      <>
                        <p>{t("management.application.conflictHelp")}</p>
                        <button
                          onClick={() => {
                            setMutationProblem(undefined);
                            setReloadKey((value) => value + 1);
                          }}
                          type="button"
                        >
                          {t("management.application.reloadAfterConflict")}
                        </button>
                      </>
                    ) : null}
                  </div>
                ) : null}
                {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}
                <div className="management-detail-form__actions">
                  <button disabled={readOnly || isSaving} type="submit">
                    {isSaving ? t("management.saving") : t("management.save")}
                  </button>
                </div>
              </form>
            ) : null}

            {selectedApplication && mode === "releases" ? (
              <div className="management-release">
                <form
                  className="management-detail-form"
                  onChange={() => setSuccessKey(undefined)}
                  onSubmit={publishVersion}
                >
                  <div className="management-detail-form__heading">
                    <div>
                      <h3>{t("management.release.formTitle")}</h3>
                      <code>{selectedApplication.slug}</code>
                    </div>
                    <span className="management-revision">
                      {selectedApplication.current_version || t("management.noRelease")}
                      {" · "}
                      {t("management.application.revision", {
                        revision: selectedApplication.revision,
                      })}
                    </span>
                  </div>
                  <label>
                    <span>{t("management.release.version")}</span>
                    <input disabled={readOnly} name="version" placeholder="1.2.3" required />
                  </label>
                  <label>
                    <span>{t("management.release.source")}</span>
                    <input defaultValue="manual" disabled={readOnly} name="source" required />
                  </label>
                  <label className="management-detail-form__wide">
                    <span>{t("management.release.notes")}</span>
                    <textarea disabled={readOnly} name="notes" rows={4} />
                  </label>
                  <p className="management-detail-form__help">{t("management.release.formHelp")}</p>
                  {mutationProblem ? (
                    <div className={`management-notice management-notice--${mutationProblem.kind}`} role="alert">
                      <strong>{t(`management.error.${mutationProblem.kind}` as MessageKey)}</strong>
                      <p>{mutationProblem.message}</p>
                      {mutationProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
                      {mutationProblem.status === 412 ? (
                        <>
                          <p>{t("management.release.conflictHelp")}</p>
                          <button
                            onClick={() => {
                              setMutationProblem(undefined);
                              setReloadKey((value) => value + 1);
                            }}
                            type="button"
                          >
                            {t("management.release.reloadAfterConflict")}
                          </button>
                        </>
                      ) : null}
                    </div>
                  ) : null}
                  {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}
                  <div className="management-detail-form__actions">
                    <button disabled={readOnly || isSaving} type="submit">
                      {isSaving ? t("management.release.publishing") : t("management.release.publish")}
                    </button>
                  </div>
                </form>

                <section aria-labelledby="release-history-title" className="management-history">
                  <h3 id="release-history-title">{t("management.release.history")}</h3>
                  {selectedApplication.versions?.length ? (
                    <ul>
                      {selectedApplication.versions.map((version) => (
                        <li key={version.id}>
                          <strong>{version.version}</strong>
                          <span>{version.source}</span>
                          {version.notes ? <p>{version.notes}</p> : null}
                        </li>
                      ))}
                    </ul>
                  ) : <p>{t("management.release.noHistory")}</p>}
                </section>
              </div>
            ) : null}
          </div>
        ) : null}

        {mode === "applications" && !readOnly ? (
          <form
            className="management-form"
            onChange={() => setSuccessKey(undefined)}
            onSubmit={createApplication}
          >
            <h3>{t("management.application.createTitle")}</h3>
            <label>
              <span>{t("management.form.name")}</span>
              <input name="name" required />
            </label>
            <label>
              <span>{t("management.form.slug")}</span>
              <input name="slug" required />
            </label>
            <label>
              <span>{t("management.form.description")}</span>
              <input name="description" />
            </label>
            <button disabled={isCreating} type="submit">
              {isCreating ? t("management.creating") : t("management.create")}
            </button>
          </form>
        ) : null}

        {readOnly ? (
          <div className="management-notice management-notice--authorization">
            <strong>{t("management.readOnlyTitle")}</strong>
            <p>{t("management.readOnlyDetail")}</p>
          </div>
        ) : null}
      </div>
    </article>
  );
}
