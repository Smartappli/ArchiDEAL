import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  type ApiProblem,
  type GatewayRouteResult,
  type HostedModule,
  isStrongRoutePreviewEtag,
  listManagementResources,
  ManagementApiError,
  publishGatewayRoute,
} from "../lib/managementApi";

interface RoutePublicationPanelProps {
  areaDescription: string;
  areaTitle: string;
  moduleName: string;
}

interface ScopedRouteResult {
  moduleId: number;
  moduleSlug: string;
  result: GatewayRouteResult;
}

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

export function RoutePublicationPanel({
  areaDescription,
  areaTitle,
  moduleName,
}: RoutePublicationPanelProps) {
  const { t } = useI18n();
  const [modules, setModules] = useState<HostedModule[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadProblem, setLoadProblem] = useState<ApiProblem>();
  const [mutationProblem, setMutationProblem] = useState<ApiProblem>();
  const [preview, setPreview] = useState<ScopedRouteResult>();
  const [publication, setPublication] = useState<ScopedRouteResult>();
  const [reloadKey, setReloadKey] = useState(0);

  const selectedModule = useMemo(
    () => modules.find((module) => module.id === selectedId),
    [modules, selectedId],
  );
  const selectedPreview = preview
    && preview.moduleId === selectedModule?.id
    && preview.moduleSlug === selectedModule.slug
    ? preview.result
    : undefined;
  const selectedPublication = publication
    && publication.moduleId === selectedModule?.id
    && publication.moduleSlug === selectedModule.slug
    ? publication.result
    : undefined;

  function normalizeProblem(error: unknown): ApiProblem {
    return error instanceof ManagementApiError
      ? error.problem
      : { kind: "server", message: t("management.unknownError"), retryable: true };
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setLoadProblem(undefined);
    setMutationProblem(undefined);
    setPreview(undefined);
    setPublication(undefined);
    listManagementResources<HostedModule>("/dealhost/api/hosting/modules/", controller.signal)
      .then((nextModules) => {
        setModules(nextModules);
        setSelectedId((current) => (
          nextModules.some((module) => module.id === current) ? current : nextModules[0]?.id
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
    setMutationProblem(undefined);
    setPreview(undefined);
    setPublication(undefined);
  }, [selectedModule?.id]);

  async function previewRoute() {
    if (!selectedModule || !selectedModule.enabled) return;
    const requestedModule = selectedModule;
    setIsSubmitting(true);
    setMutationProblem(undefined);
    setPublication(undefined);
    try {
      const result = await publishGatewayRoute(requestedModule.slug, true);
      if (!isStrongRoutePreviewEtag(result.etag)) {
        throw new ManagementApiError({
          kind: "server",
          message: t("management.route.previewTokenMissing"),
          retryable: true,
        });
      }
      setPreview({
        moduleId: requestedModule.id,
        moduleSlug: requestedModule.slug,
        result,
      });
    } catch (error) {
      setMutationProblem(normalizeProblem(error));
      setPreview(undefined);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function publishRoute() {
    if (
      !selectedModule
      || !selectedModule.enabled
      || !selectedPreview
      || selectedPreview.skipped
      || !selectedPreview.dry_run
      || !isStrongRoutePreviewEtag(selectedPreview.etag)
    ) return;
    if (!window.confirm(t("management.route.publishConfirm", { module: selectedModule.name }))) return;
    const requestedModule = selectedModule;
    setIsSubmitting(true);
    setMutationProblem(undefined);
    try {
      const result = await publishGatewayRoute(
        requestedModule.slug,
        false,
        selectedPreview.etag,
      );
      setPublication({
        moduleId: requestedModule.id,
        moduleSlug: requestedModule.slug,
        result,
      });
      setPreview(undefined);
    } catch (error) {
      const problem = normalizeProblem(error);
      setMutationProblem(problem);
      if (problem.status === 412 || problem.status === 428) {
        setPreview(undefined);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function renderResult(result: GatewayRouteResult, title: MessageKey) {
    const nodes = Object.keys(result.payload?.upstream?.nodes ?? {});
    return (
      <section className={`route-result${result.skipped ? " route-result--skipped" : ""}`}>
        <h3>{t(title)}</h3>
        <dl>
          <div>
            <dt>{t("management.route.result.routeId")}</dt>
            <dd><code>{result.route_id}</code></dd>
          </div>
          <div>
            <dt>{t("management.route.result.status")}</dt>
            <dd>
              {result.skipped
                ? t("management.route.result.skipped")
                : result.dry_run
                  ? t("management.route.result.previewed")
                  : t("management.route.result.published")}
            </dd>
          </div>
          <div>
            <dt>{t("management.route.result.etag")}</dt>
            <dd><code>{result.etag}</code></dd>
          </div>
          {result.reason ? (
            <div>
              <dt>{t("management.route.result.reason")}</dt>
              <dd>{result.reason}</dd>
            </div>
          ) : null}
          {result.payload?.uris?.length ? (
            <div>
              <dt>{t("management.route.result.uris")}</dt>
              <dd><code>{result.payload.uris.join(", ")}</code></dd>
            </div>
          ) : null}
          {nodes.length ? (
            <div>
              <dt>{t("management.route.result.upstream")}</dt>
              <dd><code>{nodes.join(", ")}</code></dd>
            </div>
          ) : null}
        </dl>
      </section>
    );
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>/dealhost/api/gateway/apisix/publish/</code>
          <button onClick={() => setReloadKey((value) => value + 1)} type="button">
            {t("management.retry")}
          </button>
        </div>

        <div className="management-notice management-notice--neutral">
          <strong>{t("management.route.noticeTitle")}</strong>
          <p>{t("management.route.noticeDetail")}</p>
        </div>

        {isLoading ? <p className="management-state">{t("management.loading")}</p> : null}
        {loadProblem ? (
          <div className={`management-notice management-notice--${loadProblem.kind}`} role="alert">
            <strong>{t(`management.error.${loadProblem.kind}` as MessageKey)}</strong>
            <p>{loadProblem.message}</p>
            {loadProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}

        {!isLoading && !loadProblem && modules.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.emptyDetail")}</p>
          </div>
        ) : null}

        {modules.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("management.route.listAria")} className="management-selector">
              {modules.map((module) => (
                <button
                  aria-current={module.id === selectedId ? "true" : undefined}
                  className={module.id === selectedId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  disabled={isSubmitting}
                  key={module.id}
                  onClick={() => setSelectedId(module.id)}
                  type="button"
                >
                  <strong>{module.name}</strong>
                  <code>{module.slug}</code>
                  <span>{t("management.routeMeta", {
                    path: module.public_path || t("management.noPublicRoute"),
                    target: module.deployment_target,
                  })}</span>
                </button>
              ))}
            </nav>

            {selectedModule ? (
              <section className="management-route-detail">
                <div className="management-detail-form__heading">
                  <div>
                    <h3>{t("management.route.detailTitle")}</h3>
                    <code>{selectedModule.slug}</code>
                  </div>
                  <span className="management-revision">
                    {selectedModule.enabled ? t("management.route.enabled") : t("management.route.disabled")}
                  </span>
                </div>
                <dl className="management-readonly-fields">
                  <div>
                    <dt>{t("management.route.publicPath")}</dt>
                    <dd><code>{selectedModule.public_path || t("management.noPublicRoute")}</code></dd>
                  </div>
                  <div>
                    <dt>{t("management.route.deploymentTarget")}</dt>
                    <dd>{selectedModule.deployment_target || "—"}</dd>
                  </div>
                  <div>
                    <dt>{t("management.route.upstream")}</dt>
                    <dd><code>{selectedModule.upstream_host ? `${selectedModule.upstream_host}:${selectedModule.upstream_port ?? "—"}` : "—"}</code></dd>
                  </div>
                </dl>
                <p className="management-detail-form__help">{t("management.route.readOnlyHelp")}</p>
                {!selectedModule.enabled ? (
                  <div className="management-notice management-notice--validation">
                    <strong>{t("management.route.disabledTitle")}</strong>
                    <p>{t("management.route.disabledDetail")}</p>
                  </div>
                ) : null}
                {mutationProblem ? (
                  <div className={`management-notice management-notice--${mutationProblem.kind}`} role="alert">
                    <strong>{t(`management.error.${mutationProblem.kind}` as MessageKey)}</strong>
                    <p>{mutationProblem.message}</p>
                    {mutationProblem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
                  </div>
                ) : null}
                <div className="management-detail-form__actions">
                  <button disabled={isSubmitting || !selectedModule.enabled} onClick={previewRoute} type="button">
                    {isSubmitting ? t("management.route.submitting") : t("management.route.preview")}
                  </button>
                  <button
                    className="management-button--danger"
                    disabled={isSubmitting || !selectedModule.enabled || !selectedPreview || Boolean(selectedPreview.skipped) || !selectedPreview.dry_run || !isStrongRoutePreviewEtag(selectedPreview.etag)}
                    onClick={publishRoute}
                    type="button"
                  >
                    {t("management.route.publish")}
                  </button>
                </div>
              </section>
            ) : null}
          </div>
        ) : null}

        {selectedPreview ? renderResult(selectedPreview, "management.route.previewResult") : null}
        {selectedPublication ? renderResult(selectedPublication, "management.route.publishResult") : null}
      </div>
    </article>
  );
}
