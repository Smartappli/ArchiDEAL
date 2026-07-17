import type { CSSProperties } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { DealModule, ModuleControlProfile } from "../types";

interface ControlProfileProps {
  module: DealModule;
  profile: ModuleControlProfile;
}

export function ControlProfile({ module, profile }: ControlProfileProps) {
  const { t } = useI18n();
  const profileFacts = [
    { label: t("control.environment"), value: profile.environment },
    { label: t("control.releaseWindow"), value: profile.releaseWindow },
    { label: t("control.slaTarget"), value: profile.slaTarget },
    { label: t("control.escalation"), value: profile.escalation },
  ];

  return (
    <section
      className="panel control-profile"
      style={{ "--accent": module.accent } as CSSProperties}
      aria-labelledby="control-profile-title"
    >
      <div className="panel__header">
        <div>
          <span className="section-kicker">{t("control.kicker")}</span>
          <h2 id="control-profile-title">{t("control.operatingModel", { module: module.name })}</h2>
        </div>
        <span className="control-profile__owner">{module.owner}</span>
      </div>

      <div className="control-profile__facts">
        {profileFacts.map((fact) => (
          <article key={fact.label}>
            <span>{fact.label}</span>
            <strong>{fact.value}</strong>
          </article>
        ))}
      </div>

      <div className="workflow-list" aria-label={t("control.workflowsAria", { module: module.name })}>
        {profile.workflows.map((workflow) => (
          <article className="workflow-card" key={workflow.id}>
            <div>
              <span>{workflow.cadence}</span>
              <h3>{workflow.title}</h3>
              <p>{workflow.description}</p>
            </div>
            <div className="workflow-card__footer">
              <strong>{workflow.automation}</strong>
              <div aria-label={t("control.requiredRoles")}>
                {workflow.requiredRoles.map((role) => (
                  <span key={role}>{role}</span>
                ))}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
