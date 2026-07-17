import type { CSSProperties } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { DealModule, ModuleKey } from "../types";

interface TopologyMapProps {
  modules: DealModule[];
  activeKey: ModuleKey;
}

export function TopologyMap({ modules, activeKey }: TopologyMapProps) {
  const { t } = useI18n();

  return (
    <section className="panel topology-panel" aria-labelledby="topology-title">
      <div className="panel__header">
        <span className="section-kicker">{t("topology.kicker")}</span>
        <h2 id="topology-title">{t("topology.title")}</h2>
      </div>
      <div className="topology-map">
        <div className="topology-core">
          <span>IAM</span>
          <strong>DEALInterface</strong>
          <small>{t("topology.coreDetail")}</small>
        </div>
        {modules.map((module, index) => (
          <div
            className={`topology-node topology-node--${index + 1} ${module.key === activeKey ? "topology-node--active" : ""}`}
            key={module.key}
            style={{ "--accent": module.accent } as CSSProperties}
          >
            <span>{module.shortName}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
