import type { CSSProperties } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { DashboardMetric } from "../types";

interface MetricsGridProps {
  metrics: DashboardMetric[];
}

export function MetricsGrid({ metrics }: MetricsGridProps) {
  const { t } = useI18n();

  return (
    <section className="metrics-grid" aria-label={t("metrics.aria")}>
      {metrics.map((metric, index) => (
        <article className="metric-card reveal" key={metric.label} style={{ "--order": index } as CSSProperties}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          <p>{metric.detail}</p>
        </article>
      ))}
    </section>
  );
}
