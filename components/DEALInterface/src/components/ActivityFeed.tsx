import { useI18n } from "../i18n/I18nProvider";
import type { ActivityItem } from "../types";

interface ActivityFeedProps {
  items: ActivityItem[];
}

export function ActivityFeed({ items }: ActivityFeedProps) {
  const { t } = useI18n();

  return (
    <section className="panel activity-panel" aria-labelledby="activity-title">
      <div className="panel__header">
        <span className="section-kicker">{t("activity.kicker")}</span>
        <h2 id="activity-title">{t("activity.title")}</h2>
      </div>
      <div className="activity-list">
        {items.map((item) => (
          <article className="activity-item" key={`${item.module}-${item.title}`}>
            <span className={`activity-item__dot activity-item__dot--${item.severity}`} aria-hidden="true" />
            <div>
              <div className="activity-item__meta">
                <strong>{item.module}</strong>
                <span>{t("activity.ago", { time: item.time })}</span>
              </div>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
