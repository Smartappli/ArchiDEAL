import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  createManagementResource,
  type Dataset,
  type Device,
  type HostedApplication,
  type HostedModule,
  listManagementResources,
  ManagementApiError,
  type ApiProblem,
} from "../lib/managementApi";
import type { ModuleKey } from "../types";

type ResourceKind = "applications" | "datasets" | "devices" | "modules";
type ManagementResource = Dataset | Device | HostedApplication | HostedModule;

interface AreaApiConfig {
  endpoint: string;
  kind: ResourceKind;
  create?: boolean;
  mode?: "access" | "governance" | "releases" | "routes";
}

const areaApis: Record<ModuleKey, Record<string, AreaApiConfig | undefined>> = {
  dealiot: {
    devices: { endpoint: "/dealiot/api/devices", kind: "devices", create: true },
    telemetry: undefined,
    rules: undefined,
  },
  dealhost: {
    deployments: {
      endpoint: "/dealhost/api/hosting/applications/",
      kind: "applications",
      mode: "releases",
    },
    apps: {
      endpoint: "/dealhost/api/hosting/applications/",
      kind: "applications",
      create: true,
    },
    domains: {
      endpoint: "/dealhost/api/hosting/modules/",
      kind: "modules",
      mode: "routes",
    },
  },
  dealdata: {
    datasets: {
      endpoint: "/dealhost/api/hosting/datasets/",
      kind: "datasets",
      create: true,
    },
    access: {
      endpoint: "/dealhost/api/hosting/datasets/",
      kind: "datasets",
      mode: "access",
    },
    governance: undefined,
  },
};

interface ResourceState {
  status: "idle" | "loading" | "success" | "empty" | "error";
  data: ManagementResource[];
  error?: ApiProblem;
}

interface ManagementAreaPanelProps {
  areaDescription: string;
  areaId: string;
  areaTitle: string;
  moduleKey: ModuleKey;
  moduleName: string;
}

function resourceTitle(resource: ManagementResource) {
  if ("display_name" in resource) return resource.display_name;
  return resource.name;
}

function resourceIdentifier(resource: ManagementResource) {
  if ("device_id" in resource) return resource.device_id;
  return resource.slug;
}

function resourceMeta(resource: ManagementResource, config: AreaApiConfig, t: (key: MessageKey, params?: Record<string, string | number>) => string) {
  if ("device_id" in resource) {
    return t("management.deviceMeta", {
      kind: resource.kind,
      revision: resource.revision,
      status: resource.status,
    });
  }
  if ("current_version" in resource) {
    const version = resource.current_version || t("management.noRelease");
    return config.mode === "releases"
      ? t("management.releaseMeta", { version })
      : t("management.applicationMeta", { version });
  }
  if ("public_path" in resource) {
    return t("management.routeMeta", {
      path: resource.public_path || t("management.noPublicRoute"),
      target: resource.deployment_target,
    });
  }
  if (config.mode === "access") {
    return t("management.accessMeta", {
      groups: resource.group_ids?.length ?? 0,
      users: resource.user_ids?.length ?? 0,
    });
  }
  return resource.description || t("management.noDescription");
}

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

export function ManagementAreaPanel({
  areaDescription,
  areaId,
  areaTitle,
  moduleKey,
  moduleName,
}: ManagementAreaPanelProps) {
  const { t } = useI18n();
  const config = areaApis[moduleKey][areaId];
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<ResourceState>({ status: "idle", data: [] });
  const [isCreating, setIsCreating] = useState(false);
  const [createProblem, setCreateProblem] = useState<ApiProblem>();
  const [readOnly, setReadOnly] = useState(false);

  useEffect(() => {
    setCreateProblem(undefined);
    setReadOnly(false);
    if (!config) {
      setState({ status: "idle", data: [] });
      return undefined;
    }

    const controller = new AbortController();
    setState((current) => ({ status: "loading", data: current.data }));
    listManagementResources<ManagementResource>(config.endpoint, controller.signal)
      .then((data) => setState({ status: data.length > 0 ? "success" : "empty", data }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const problem = error instanceof ManagementApiError
          ? error.problem
          : { kind: "server" as const, message: t("management.unknownError"), retryable: true };
        setState((current) => ({ status: "error", data: current.data, error: problem }));
      });

    return () => controller.abort();
  }, [config, reloadKey, t]);

  const formCopy = useMemo(() => {
    if (!config) return undefined;
    if (config.kind === "devices") {
      return {
        primary: "management.form.deviceId" as MessageKey,
        secondary: "management.form.displayName" as MessageKey,
        tertiary: "management.form.kind" as MessageKey,
      };
    }
    return {
      primary: "management.form.name" as MessageKey,
      secondary: "management.form.slug" as MessageKey,
      tertiary: "management.form.description" as MessageKey,
    };
  }, [config]);

  async function submitResource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config || !formCopy) return;

    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const primary = String(form.get("primary") ?? "").trim();
    const secondary = String(form.get("secondary") ?? "").trim();
    const tertiary = String(form.get("tertiary") ?? "").trim();
    const payload = config.kind === "devices"
      ? {
          device_id: primary,
          display_name: secondary,
          kind: tertiary,
          status: "provisioning",
        }
      : {
          name: primary,
          slug: secondary,
          description: tertiary,
          enabled: true,
        };

    setIsCreating(true);
    setCreateProblem(undefined);
    try {
      await createManagementResource(config.endpoint, payload);
      formElement.reset();
      setReloadKey((value) => value + 1);
    } catch (error) {
      const problem = error instanceof ManagementApiError
        ? error.problem
        : { kind: "server" as const, message: t("management.unknownError"), retryable: true };
      setCreateProblem(problem);
      if (problem.kind === "authorization") setReadOnly(true);
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      {!config ? (
        <div className="management-notice management-notice--neutral">
          <strong>{t("management.notExposedTitle")}</strong>
          <p>{t("management.notExposedDetail")}</p>
        </div>
      ) : (
        <div className="management-surface">
          <div className="management-toolbar">
            <code>{config.endpoint}</code>
            <button onClick={() => setReloadKey((value) => value + 1)} type="button">
              {t("management.retry")}
            </button>
          </div>

          {state.status === "loading" ? <p className="management-state">{t("management.loading")}</p> : null}

          {state.status === "error" && state.error ? (
            <div className={`management-notice management-notice--${state.error.kind}`} role="alert">
              <strong>{t(`management.error.${state.error.kind}` as MessageKey)}</strong>
              <p>{state.error.message}</p>
              {state.error.kind === "authentication" ? (
                <a href={reconnectUrl()}>{t("management.reconnect")}</a>
              ) : null}
            </div>
          ) : null}

          {state.status === "empty" ? (
            <div className="management-empty">
              <strong>{t("management.emptyTitle")}</strong>
              <p>{t("management.emptyDetail")}</p>
            </div>
          ) : null}

          {state.data.length > 0 ? (
            <ul className="management-list">
              {state.data.map((resource) => (
                <li key={`${config.kind}-${resourceIdentifier(resource)}`}>
                  <div>
                    <strong>{resourceTitle(resource)}</strong>
                    <code>{resourceIdentifier(resource)}</code>
                  </div>
                  <p>{resourceMeta(resource, config, t)}</p>
                </li>
              ))}
            </ul>
          ) : null}

          {config.create && formCopy && !readOnly ? (
            <form className="management-form" onSubmit={submitResource}>
              <h3>{t("management.createTitle")}</h3>
              <label>
                <span>{t(formCopy.primary)}</span>
                <input name="primary" required />
              </label>
              <label>
                <span>{t(formCopy.secondary)}</span>
                <input name="secondary" required />
              </label>
              <label>
                <span>{t(formCopy.tertiary)}</span>
                <input name="tertiary" required />
              </label>
              {createProblem ? (
                <div className="management-notice management-notice--validation" role="alert">
                  <strong>{t(`management.error.${createProblem.kind}` as MessageKey)}</strong>
                  <p>{createProblem.message}</p>
                </div>
              ) : null}
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
      )}
    </article>
  );
}
