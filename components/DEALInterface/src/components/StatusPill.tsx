import { useI18n } from "../i18n/I18nProvider";
import type { ModuleHealth } from "../types";

const statusLabelKeys = {
  online: "status.online",
  degraded: "status.degraded",
  attention: "status.attention",
  protected: "status.protected",
  pending: "status.pending",
} as const;

export type DisplayStatus = ModuleHealth | "pending";

interface StatusPillProps {
  status: DisplayStatus;
}

export function StatusPill({ status }: StatusPillProps) {
  const { t } = useI18n();

  return <span className={`status-pill status-pill--${status}`}>{t(statusLabelKeys[status])}</span>;
}
