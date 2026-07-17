import type { ModuleRuntimeConfig } from "../config/moduleRegistry";
import { useI18n } from "../i18n/I18nProvider";
import type { DealModule, ModuleConnection } from "../types";
import { StatusPill } from "./StatusPill";

const statusCopyKeys = {
  online: "status.copyOnline",
  degraded: "status.copyDegraded",
  attention: "status.copyAttention",
} as const;

interface ModuleDetailProps {
  module: DealModule;
  runtime: ModuleRuntimeConfig;
  connection?: ModuleConnection;
}

export function ModuleDetail({ module, runtime, connection }: ModuleDetailProps) {
  const { t } = useI18n();
  const healthUrl = `${runtime.apiBaseUrl}${runtime.healthPath}`;
  const liveDetail = connection
    ? t("module.liveProbesHealthy", {
        online: connection.probes.filter((probe) => probe.status === "online").length,
        total: connection.probes.length,
      })
    : t("module.waitingForProbe");

  return (
    <section className="panel module-detail" aria-labelledby="module-detail-title">
      <div className="panel__header module-detail__header">
        <div>
          <span className="section-kicker">{t("module.selected")}</span>
          <h2 id="module-detail-title">{module.name}</h2>
        </div>
        <StatusPill status={module.status} />
      </div>

      <p className="module-detail__summary">{t(statusCopyKeys[module.status])}</p>

      <div className="runtime-card">
        <span>{connection ? t("module.liveEndpoint") : t("module.runtimeEndpoint")}</span>
        <strong>{runtime.apiBaseUrl}</strong>
        <small>{liveDetail}</small>
        <a href={healthUrl} rel="noreferrer" target="_blank">
          {t("module.openHealthProbe")}
        </a>
      </div>

      <div className="module-detail__metrics">
        {module.metrics.map((metric) => (
          <article key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.trend}</small>
          </article>
        ))}
      </div>

      <div className="detail-columns">
        <div>
          <h3>{t("module.managedCapabilities")}</h3>
          <ul>
            {module.capabilities.map((capability) => (
              <li key={capability}>{capability}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3>{t("module.connectedSystems")}</h3>
          <ul>
            {module.integrations.map((integration) => (
              <li key={integration}>{integration}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
