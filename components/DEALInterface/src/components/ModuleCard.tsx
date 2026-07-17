import type { CSSProperties } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { DealModule, ModuleKey } from "../types";
import { StatusPill } from "./StatusPill";

interface ModuleCardProps {
  module: DealModule;
  isActive: boolean;
  onSelect: (key: ModuleKey) => void;
  order: number;
}

export function ModuleCard({ module, isActive, onSelect, order }: ModuleCardProps) {
  const { t } = useI18n();

  return (
    <button
      className={`module-card reveal ${isActive ? "module-card--active" : ""}`}
      onClick={() => onSelect(module.key)}
      style={{ "--accent": module.accent, "--order": order } as CSSProperties}
      type="button"
    >
      <span className="module-card__eyebrow">{module.endpointLabel}</span>
      <div className="module-card__head">
        <h3>{module.name}</h3>
        <StatusPill status={module.status} />
      </div>
      <p>{module.summary}</p>
      <div className="module-card__capabilities" aria-label={t("module.capabilitiesAria", { module: module.name })}>
        {module.capabilities.slice(0, 3).map((capability) => (
          <span key={capability}>{capability}</span>
        ))}
      </div>
    </button>
  );
}
