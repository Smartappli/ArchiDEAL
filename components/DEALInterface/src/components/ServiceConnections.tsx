import type { ModuleRuntimeConfig } from "../config/moduleRegistry";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import type { DealModule, ModuleConnection, ModuleKey, ModuleProbeResult, ProbeStatus } from "../types";
import { StatusPill } from "./StatusPill";

type ConnectionMap = Partial<Record<ModuleKey, ModuleConnection>>;

interface ServiceConnectionsProps {
  activeKey: ModuleKey;
  connections: ConnectionMap;
  isRefreshing: boolean;
  modules: DealModule[];
  runtimes: Record<ModuleKey, ModuleRuntimeConfig>;
  onRefresh: () => void;
  onSelectModule: (key: ModuleKey) => void;
}

const probeStatusLabels: Record<ProbeStatus, MessageKey> = {
  online: "service.statusOnline",
  degraded: "service.statusDegraded",
  attention: "service.statusAttention",
};

const probeSummaryLabels: Partial<Record<string, MessageKey>> = {
  degraded: "service.summaryDegraded",
  failed: "service.summaryFailed",
  healthy: "service.summaryHealthy",
  unavailable: "service.summaryUnavailable",
  unhealthy: "service.summaryUnhealthy",
  unknown: "service.summaryUnknown",
  unreachable: "service.summaryUnreachable",
};

function formatCheckedAt(value: string | undefined, locale: string) {
  if (!value) {
    return undefined;
  }

  return new Date(value).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatProbeDetail(probe: ModuleProbeResult, t: (key: MessageKey, params?: Record<string, string | number>) => string) {
  if (!probe.summary) {
    return probe.detail;
  }

  return Object.entries(probe.summary)
    .map(([key, count]) => {
      const messageKey = probeSummaryLabels[key];

      return messageKey ? t(messageKey, { count }) : `${count} ${key}`;
    })
    .join(", ");
}

function countOnline(probes: ModuleProbeResult[]) {
  return probes.filter((probe) => probe.status === "online").length;
}

export function ServiceConnections({
  activeKey,
  connections,
  isRefreshing,
  modules,
  runtimes,
  onRefresh,
  onSelectModule,
}: ServiceConnectionsProps) {
  const { language, t } = useI18n();
  const activeModule = modules.find((module) => module.key === activeKey) ?? modules[0];
  const activeConnection = connections[activeKey];
  const activeRuntime = runtimes[activeKey];

  return (
    <section
      className="panel service-connections"
      aria-busy={isRefreshing}
      aria-labelledby="service-connections-title"
    >
      <div className="panel__header">
        <div>
          <span className="section-kicker">{t("service.kicker")}</span>
          <h2 id="service-connections-title">{t("service.connectedApis")}</h2>
        </div>
        <button className="refresh-button" disabled={isRefreshing} onClick={onRefresh} type="button">
          {isRefreshing ? t("service.checking") : t("service.refresh")}
        </button>
      </div>

      <div className="connection-overview" aria-label={t("service.overviewAria")}>
        {modules.map((module) => {
          const connection = connections[module.key];
          const probeTotal = runtimes[module.key].probes.length;
          const onlineTotal = connection ? countOnline(connection.probes) : 0;
          const checkedAt = formatCheckedAt(connection?.checkedAt, language) ?? t("service.pending");

          return (
            <button
              aria-pressed={module.key === activeKey}
              className={`connection-tile ${module.key === activeKey ? "connection-tile--active" : ""}`}
              key={module.key}
              onClick={() => onSelectModule(module.key)}
              type="button"
            >
              <span>{module.name}</span>
              {connection ? <StatusPill status={connection.status} /> : <strong>{t("service.waitingTile")}</strong>}
              <small>{t("service.probeOverview", { online: onlineTotal, total: probeTotal, checkedAt })}</small>
            </button>
          );
        })}
      </div>

      <div
        className="probe-list"
        aria-label={t("service.endpointListAria", { module: activeModule.name })}
        aria-live="polite"
      >
        <div className="probe-list__header">
          <h3>{t("service.endpoints", { module: activeModule.name })}</h3>
          <span>{activeRuntime.apiBaseUrl}</span>
        </div>

        {(activeConnection?.probes ?? []).map((probe) => {
          const transport = probe.httpStatus ? t("service.httpStatus", { status: probe.httpStatus }) : t("service.network");
          const timing = probe.responseTimeMs !== undefined
            ? t("service.responseMs", { ms: probe.responseTimeMs })
            : t("service.noResponse");

          return (
            <article className={`probe-card probe-card--${probe.status}`} key={probe.id}>
              <div>
                <span>{probe.label}</span>
                <a href={probe.url} rel="noreferrer" target="_blank">
                  {probe.url}
                </a>
              </div>
              <div className="probe-card__status">
                <strong>{t(probeStatusLabels[probe.status])}</strong>
                <small>{t("service.probeTransport", { transport, timing })}</small>
              </div>
              <p>{formatProbeDetail(probe, t)}</p>
            </article>
          );
        })}

        {!activeConnection &&
          activeRuntime.probes.map((probe) => {
            const url = `${probe.baseUrl ?? activeRuntime.apiBaseUrl}${probe.path}`;

            return (
              <article className="probe-card probe-card--pending" key={probe.id}>
                <div>
                  <span>{probe.label}</span>
                  <a href={url} rel="noreferrer" target="_blank">
                    {url}
                  </a>
                </div>
                <div className="probe-card__status">
                  <strong>{t("service.pending")}</strong>
                  <small>{t("service.waitingCheck")}</small>
                </div>
                <p>{t("service.pendingDetail")}</p>
              </article>
            );
          })}
      </div>
    </section>
  );
}
