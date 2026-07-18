import { useI18n } from "../i18n/I18nProvider";
import type { DealModule, ModuleConnection, ModuleKey } from "../types";
import { StatusPill, type DisplayStatus } from "./StatusPill";

type ConnectionMap = Partial<Record<ModuleKey, ModuleConnection>>;

interface PlatformHealthProps {
  connections: ConnectionMap;
  isRefreshing: boolean;
  modules: DealModule[];
  onRefresh: () => void;
}

function formatCheckedAt(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export function PlatformHealth({ connections, isRefreshing, modules, onRefresh }: PlatformHealthProps) {
  const { language, t } = useI18n();
  const observedConnections = modules
    .map((module) => connections[module.key])
    .filter((connection): connection is ModuleConnection => Boolean(connection));
  const operationalCount = observedConnections.filter((connection) => connection.status === "online").length;
  const issueCount = observedConnections.length - operationalCount;
  const isPending = observedConnections.length < modules.length;
  const status: DisplayStatus = isPending
    ? "pending"
    : issueCount === 0
      ? "online"
      : operationalCount > 0 || observedConnections.some((connection) => connection.status === "degraded")
        ? "degraded"
        : "attention";
  const latestCheck = observedConnections
    .map((connection) => connection.checkedAt)
    .sort((left, right) => right.localeCompare(left))[0];
  const summary = isPending
    ? t("platform.checking")
    : issueCount === 0
      ? t("platform.allOperational")
      : t("platform.issueCount", { count: issueCount });

  return (
    <section className="platform-health reveal" aria-busy={isRefreshing} aria-label={t("platform.aria")}>
      <div className="platform-health__header">
        <div>
          <span className="platform-health__kicker">{t("platform.kicker")}</span>
          <span className="platform-health__environment">{t("platform.validationLabel")}</span>
        </div>
        <StatusPill status={status} />
      </div>

      <h2 aria-live="polite">{summary}</h2>

      <div className="platform-health__metrics">
        <div>
          <span>{t("platform.operational")}</span>
          <strong>
            {operationalCount}/{modules.length}
          </strong>
        </div>
        <div>
          <span>{t("platform.requiresAttention")}</span>
          <strong>{issueCount}</strong>
        </div>
      </div>

      <div className="platform-health__footer">
        {latestCheck ? (
          <time dateTime={latestCheck}>{t("platform.lastChecked", { time: formatCheckedAt(latestCheck, language) })}</time>
        ) : (
          <span>{t("platform.notChecked")}</span>
        )}
        <button disabled={isRefreshing} onClick={onRefresh} type="button">
          <span aria-hidden="true">↻</span>
          {isRefreshing ? t("service.checking") : t("service.refresh")}
        </button>
      </div>
    </section>
  );
}
