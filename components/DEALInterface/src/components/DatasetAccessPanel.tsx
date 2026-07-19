import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import {
  type ApiProblem,
  type Dataset,
  type DatasetPrincipalGroup,
  type DatasetPrincipalUser,
  getDatasetPrincipals,
  listAllDatasetResources,
  ManagementApiError,
  provisionOidcIdentity,
  updateManagementResource,
} from "../lib/managementApi";

interface DatasetAccessPanelProps {
  areaDescription: string;
  areaTitle: string;
  moduleName: string;
}

interface AccessState {
  datasets: Dataset[];
  users: DatasetPrincipalUser[];
  groups: DatasetPrincipalGroup[];
  canProvisionOidc: boolean;
  loading: boolean;
  error?: ApiProblem;
}

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

function principalLabel(user: DatasetPrincipalUser) {
  return user.email && user.email !== user.label ? `${user.label} — ${user.email}` : user.label;
}

export function DatasetAccessPanel({ areaDescription, areaTitle, moduleName }: DatasetAccessPanelProps) {
  const { t } = useI18n();
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<AccessState>({
    datasets: [],
    users: [],
    groups: [],
    canProvisionOidc: false,
    loading: true,
  });
  const [selectedId, setSelectedId] = useState<number>();
  const [userIds, setUserIds] = useState<number[]>([]);
  const [groupIds, setGroupIds] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveProblem, setSaveProblem] = useState<ApiProblem>();
  const [saved, setSaved] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [provisionProblem, setProvisionProblem] = useState<ApiProblem>();
  const [provisioned, setProvisioned] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setState((current) => ({ ...current, loading: true, error: undefined }));
    Promise.all([
      listAllDatasetResources(controller.signal),
      getDatasetPrincipals(controller.signal),
    ])
      .then(([datasets, principals]) => {
        setState({
          datasets,
          users: principals.users,
          groups: principals.groups,
          canProvisionOidc: principals.can_provision_oidc,
          loading: false,
        });
        setSelectedId((current) => (
          current !== undefined && datasets.some((dataset) => dataset.id === current)
            ? current
            : datasets[0]?.id
        ));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const problem = error instanceof ManagementApiError
          ? error.problem
          : { kind: "server" as const, message: t("management.unknownError"), retryable: true };
        setState((current) => ({ ...current, loading: false, error: problem }));
      });
    return () => controller.abort();
  }, [reloadKey, t]);

  const selectedDataset = useMemo(
    () => state.datasets.find((dataset) => dataset.id === selectedId),
    [selectedId, state.datasets],
  );

  useEffect(() => {
    setUserIds(selectedDataset?.user_ids ?? []);
    setGroupIds(selectedDataset?.group_ids ?? []);
    setSaveProblem(undefined);
  }, [selectedDataset]);

  function toggleId(values: number[], id: number, checked: boolean) {
    return checked ? [...new Set([...values, id])] : values.filter((value) => value !== id);
  }

  async function saveAccess(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDataset) return;
    setSaving(true);
    setSaved(false);
    setSaveProblem(undefined);
    try {
      const updated = await updateManagementResource<Dataset>(
        `/dealhost/api/hosting/datasets/${selectedDataset.id}/`,
        { user_ids: userIds, group_ids: groupIds },
        undefined,
        { "If-Match": `"${selectedDataset.revision}"` },
      );
      setState((current) => ({
        ...current,
        datasets: current.datasets.map((dataset) => dataset.id === updated.id ? updated : dataset),
      }));
      setSaved(true);
    } catch (error) {
      setSaveProblem(
        error instanceof ManagementApiError
          ? error.problem
          : { kind: "server", message: t("management.unknownError"), retryable: true },
      );
    } finally {
      setSaving(false);
    }
  }

  async function provisionIdentity(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state.canProvisionOidc) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setProvisioning(true);
    setProvisionProblem(undefined);
    setProvisioned(false);
    try {
      await provisionOidcIdentity({
        issuer: String(form.get("issuer") ?? "").trim(),
        subject: String(form.get("subject") ?? "").trim(),
        display_name: String(form.get("display_name") ?? "").trim(),
        email: String(form.get("email") ?? "").trim(),
      });
      const principals = await getDatasetPrincipals();
      setState((current) => ({
        ...current,
        users: principals.users,
        groups: principals.groups,
        canProvisionOidc: principals.can_provision_oidc,
      }));
      formElement.reset();
      setProvisioned(true);
    } catch (error) {
      setProvisionProblem(
        error instanceof ManagementApiError
          ? error.problem
          : { kind: "server", message: t("management.unknownError"), retryable: true },
      );
    } finally {
      setProvisioning(false);
    }
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>/dealhost/api/hosting/datasets/ + /dealhost/api/hosting/dataset-principals/</code>
          <button onClick={() => setReloadKey((value) => value + 1)} type="button">
            {t("management.retry")}
          </button>
        </div>

        {state.loading ? <p className="management-state">{t("management.loading")}</p> : null}
        {state.error ? (
          <div className={`management-notice management-notice--${state.error.kind}`} role="alert">
            <strong>{t(`management.error.${state.error.kind}`)}</strong>
            <p>{state.error.message}</p>
            {state.error.kind === "authentication" ? (
              <a href={reconnectUrl()}>{t("management.reconnect")}</a>
            ) : null}
          </div>
        ) : null}

        {!state.loading && !state.error && state.datasets.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.emptyDetail")}</p>
          </div>
        ) : null}

        {!state.loading && !state.error && state.canProvisionOidc ? (
          <section className="oidc-provisioning" aria-labelledby="oidc-provisioning-title">
            <div>
              <h3 id="oidc-provisioning-title">{t("management.oidc.title")}</h3>
              <p>{t("management.oidc.help")}</p>
            </div>
            <form
              onChange={() => setProvisioned(false)}
              onSubmit={provisionIdentity}
            >
              <label>
                <span>{t("management.oidc.issuer")}</span>
                <input name="issuer" placeholder="https://identity.example/realms/operations" required type="url" />
              </label>
              <label>
                <span>{t("management.oidc.subject")}</span>
                <input name="subject" required />
              </label>
              <label>
                <span>{t("management.oidc.displayName")}</span>
                <input name="display_name" />
              </label>
              <label>
                <span>{t("management.oidc.email")}</span>
                <input name="email" type="email" />
              </label>
              {provisionProblem ? (
                <div className={`management-notice management-notice--${provisionProblem.kind}`} role="alert">
                  <strong>{t(`management.error.${provisionProblem.kind}`)}</strong>
                  <p>{provisionProblem.message}</p>
                  {provisionProblem.kind === "authentication" ? (
                    <a href={reconnectUrl()}>{t("management.reconnect")}</a>
                  ) : null}
                </div>
              ) : null}
              {provisioned ? <p className="management-success" role="status">{t("management.oidc.provisioned")}</p> : null}
              <button disabled={provisioning} type="submit">
                {provisioning ? t("management.oidc.provisioning") : t("management.oidc.provision")}
              </button>
            </form>
          </section>
        ) : null}

        {!state.loading && !state.error && !state.canProvisionOidc ? (
          <div className="management-notice management-notice--authorization">
            <strong>{t("management.oidc.restrictedTitle")}</strong>
            <p>{t("management.oidc.restrictedDetail")}</p>
          </div>
        ) : null}

        {selectedDataset ? (
          <form
            className="access-form"
            onChange={() => setSaved(false)}
            onSubmit={saveAccess}
          >
            <label className="access-form__dataset">
              <span>{t("management.access.dataset")}</span>
              <select
                value={selectedId}
                onChange={(event) => {
                  setSaved(false);
                  setSelectedId(Number(event.target.value));
                }}
              >
                {state.datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>{dataset.name}</option>
                ))}
              </select>
            </label>

            <p className="access-form__help">{t("management.access.help")}</p>
            <fieldset>
              <legend>{t("management.access.users")}</legend>
              {state.users.map((user) => (
                <label key={user.id}>
                  <input
                    checked={userIds.includes(user.id)}
                    onChange={(event) => setUserIds((values) => toggleId(values, user.id, event.target.checked))}
                    type="checkbox"
                  />
                  <span>{principalLabel(user)}</span>
                </label>
              ))}
            </fieldset>
            <fieldset>
              <legend>{t("management.access.groups")}</legend>
              {state.groups.map((group) => (
                <label key={group.id}>
                  <input
                    checked={groupIds.includes(group.id)}
                    onChange={(event) => setGroupIds((values) => toggleId(values, group.id, event.target.checked))}
                    type="checkbox"
                  />
                  <span>{group.name}</span>
                </label>
              ))}
            </fieldset>

            {saveProblem ? (
              <div className={`management-notice management-notice--${saveProblem.kind}`} role="alert">
                <strong>{t(`management.error.${saveProblem.kind}`)}</strong>
                <p>{saveProblem.message}</p>
                {saveProblem.kind === "authentication" ? (
                  <a href={reconnectUrl()}>{t("management.reconnect")}</a>
                ) : null}
              </div>
            ) : null}
            {saved ? <p className="access-form__success">{t("management.access.saved")}</p> : null}
            <button disabled={saving} type="submit">
              {saving ? t("management.access.saving") : t("management.access.save")}
            </button>
          </form>
        ) : null}
      </div>
    </article>
  );
}
