import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";

const commandGroups: Array<{ titleKey: MessageKey; itemKeys: MessageKey[] }> = [
  {
    titleKey: "command.access",
    itemKeys: ["command.tenantOnboarding", "command.roleApprovals", "command.serviceAccounts"],
  },
  {
    titleKey: "command.operations",
    itemKeys: ["command.incidentQueue", "command.slaChecks", "command.releaseWindows"],
  },
  {
    titleKey: "command.governance",
    itemKeys: ["command.auditExports", "command.usageReports", "command.policyExceptions"],
  },
];

export function CommandCenter() {
  const { t } = useI18n();

  return (
    <section className="panel command-center" aria-labelledby="command-title">
      <div className="panel__header">
        <span className="section-kicker">{t("command.kicker")}</span>
        <h2 id="command-title">{t("command.title")}</h2>
      </div>
      <div className="command-grid">
        {commandGroups.map((group) => (
          <article key={group.titleKey}>
            <h3>{t(group.titleKey)}</h3>
            <ul>
              {group.itemKeys.map((itemKey) => (
                <li key={itemKey}>{t(itemKey)}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
