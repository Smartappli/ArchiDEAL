import type { CSSProperties } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import type { ActionPriority, ActionState, DealModule, ModuleKey, OperatorAction } from "../types";

interface OperatorQueueProps {
  actions: OperatorAction[];
  activeKey: ModuleKey;
  modules: DealModule[];
  onSelectModule: (key: ModuleKey) => void;
}

const priorityLabels: Record<ActionPriority, MessageKey> = {
  critical: "operator.priorityCritical",
  high: "operator.priorityHigh",
  normal: "operator.priorityNormal",
};

const priorityRank: Record<ActionPriority, number> = {
  critical: 0,
  high: 1,
  normal: 2,
};

const stateLabels: Record<ActionState, MessageKey> = {
  open: "operator.stateOpen",
  in_progress: "operator.stateInProgress",
  blocked: "operator.stateBlocked",
  scheduled: "operator.stateScheduled",
};

export function OperatorQueue({ actions, activeKey, modules, onSelectModule }: OperatorQueueProps) {
  const { t } = useI18n();
  const moduleLookup = new Map(modules.map((module) => [module.key, module]));
  const activeActions = actions.filter((action) => action.moduleKey === activeKey);
  const orderedActions = [...actions].sort((left, right) => {
    const activeDelta = Number(right.moduleKey === activeKey) - Number(left.moduleKey === activeKey);

    if (activeDelta !== 0) {
      return activeDelta;
    }

    return priorityRank[left.priority] - priorityRank[right.priority];
  });

  return (
    <section className="panel action-queue" aria-labelledby="action-queue-title">
      <div className="panel__header">
        <div>
          <span className="section-kicker">{t("operator.kicker")}</span>
          <h2 id="action-queue-title">{t("operator.title")}</h2>
        </div>
        <strong className="queue-count">
          {activeActions.length}
          <span>{t("operator.focused")}</span>
        </strong>
      </div>

      <div className="action-list">
        {orderedActions.map((action) => {
          const module = moduleLookup.get(action.moduleKey);

          if (!module) {
            return null;
          }

          const isActive = action.moduleKey === activeKey;

          return (
            <article
              className={`action-card action-card--${action.priority} ${isActive ? "action-card--active" : ""}`}
              key={action.id}
              style={{ "--accent": module.accent } as CSSProperties}
            >
              <div className="action-card__top">
                <button
                  aria-current={isActive ? "true" : undefined}
                  className="action-card__module"
                  onClick={() => onSelectModule(action.moduleKey)}
                  type="button"
                >
                  {module.name}
                </button>
                <span className={`action-card__state action-card__state--${action.state}`}>
                  {t(stateLabels[action.state])}
                </span>
              </div>

              <h3>{action.title}</h3>
              <p>{action.detail}</p>

              <dl className="action-card__meta">
                <div>
                  <dt>{t("operator.owner")}</dt>
                  <dd>{action.owner}</dd>
                </div>
                <div>
                  <dt>{t("operator.due")}</dt>
                  <dd>{action.due}</dd>
                </div>
                <div>
                  <dt>{t("operator.priority")}</dt>
                  <dd>{t(priorityLabels[action.priority])}</dd>
                </div>
              </dl>
            </article>
          );
        })}
      </div>
    </section>
  );
}
