import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import type { DealModule, ModuleConnection, ModuleKey } from "../types";
import { ApplicationManagementPanel } from "./ApplicationManagementPanel";
import { DatasetAccessPanel } from "./DatasetAccessPanel";
import { DatasetManagementPanel } from "./DatasetManagementPanel";
import { DeviceManagementPanel } from "./DeviceManagementPanel";
import { ManagementAreaPanel } from "./ManagementAreaPanel";
import { RoutePublicationPanel } from "./RoutePublicationPanel";
import { StatusPill } from "./StatusPill";

interface WorkspaceArea {
  id: string;
  title: MessageKey;
  description: MessageKey;
}

interface WorkspaceCopy {
  title: MessageKey;
  summary: MessageKey;
  areas: WorkspaceArea[];
}

const workspaceCopy: Record<ModuleKey, WorkspaceCopy> = {
  dealiot: {
    title: "workspace.dealiot.title",
    summary: "workspace.dealiot.summary",
    areas: [
      {
        id: "devices",
        title: "workspace.dealiot.devices.title",
        description: "workspace.dealiot.devices.description",
      },
      {
        id: "telemetry",
        title: "workspace.dealiot.telemetry.title",
        description: "workspace.dealiot.telemetry.description",
      },
      {
        id: "rules",
        title: "workspace.dealiot.rules.title",
        description: "workspace.dealiot.rules.description",
      },
    ],
  },
  dealhost: {
    title: "workspace.dealhost.title",
    summary: "workspace.dealhost.summary",
    areas: [
      {
        id: "deployments",
        title: "workspace.dealhost.deployments.title",
        description: "workspace.dealhost.deployments.description",
      },
      {
        id: "apps",
        title: "workspace.dealhost.apps.title",
        description: "workspace.dealhost.apps.description",
      },
      {
        id: "domains",
        title: "workspace.dealhost.domains.title",
        description: "workspace.dealhost.domains.description",
      },
    ],
  },
  dealdata: {
    title: "workspace.dealdata.title",
    summary: "workspace.dealdata.summary",
    areas: [
      {
        id: "datasets",
        title: "workspace.dealdata.datasets.title",
        description: "workspace.dealdata.datasets.description",
      },
      {
        id: "access",
        title: "workspace.dealdata.access.title",
        description: "workspace.dealdata.access.description",
      },
      {
        id: "governance",
        title: "workspace.dealdata.governance.title",
        description: "workspace.dealdata.governance.description",
      },
    ],
  },
};

export function getDefaultWorkspaceArea(moduleKey: ModuleKey): string {
  return workspaceCopy[moduleKey].areas[0].id;
}

export function isWorkspaceArea(moduleKey: ModuleKey, areaId: string): boolean {
  return workspaceCopy[moduleKey].areas.some((area) => area.id === areaId);
}

interface ModuleWorkspaceProps {
  activeAreaId: string;
  connection?: ModuleConnection;
  module: DealModule;
  onBackHome: () => void;
  onSelectArea: (areaId: string) => void;
}

export function ModuleWorkspace({
  activeAreaId,
  connection,
  module,
  onBackHome,
  onSelectArea,
}: ModuleWorkspaceProps) {
  const { t } = useI18n();
  const copy = workspaceCopy[module.key];
  const activeArea = copy.areas.find((area) => area.id === activeAreaId) ?? copy.areas[0];

  function renderActiveArea() {
    const sharedProps = {
      areaDescription: t(activeArea.description),
      areaTitle: t(activeArea.title),
      moduleName: module.name,
    };

    if (module.key === "dealiot" && activeArea.id === "devices") {
      return <DeviceManagementPanel {...sharedProps} />;
    }
    if (module.key === "dealhost" && activeArea.id === "apps") {
      return <ApplicationManagementPanel {...sharedProps} mode="applications" />;
    }
    if (module.key === "dealhost" && activeArea.id === "deployments") {
      return <ApplicationManagementPanel {...sharedProps} mode="releases" />;
    }
    if (module.key === "dealhost" && activeArea.id === "domains") {
      return <RoutePublicationPanel {...sharedProps} />;
    }
    if (module.key === "dealdata" && activeArea.id === "access") {
      return <DatasetAccessPanel {...sharedProps} />;
    }
    if (module.key === "dealdata" && activeArea.id === "datasets") {
      return <DatasetManagementPanel {...sharedProps} />;
    }
    return (
      <ManagementAreaPanel
        {...sharedProps}
        areaId={activeArea.id}
        moduleKey={module.key}
      />
    );
  }

  return (
    <section className="module-workspace" aria-labelledby="workspace-title">
      <div className="module-workspace__header">
        <button className="module-workspace__back" onClick={onBackHome} type="button">
          {t("workspace.backHome")}
        </button>
        <span className="section-kicker">{t("workspace.kicker")}</span>
        <div className="module-workspace__heading">
          <div>
            <h1 id="workspace-title">{t(copy.title)}</h1>
            <p>{t(copy.summary)}</p>
          </div>
          <StatusPill status={connection ? module.status : "pending"} />
        </div>
      </div>

      <div className="module-workspace__body">
        <nav aria-label={t("workspace.managedAreas", { module: module.name })} className="module-workspace__nav">
          {copy.areas.map((area) => (
            <button
              aria-current={area.id === activeArea.id ? "page" : undefined}
              className={area.id === activeArea.id ? "module-workspace__nav-item module-workspace__nav-item--active" : "module-workspace__nav-item"}
              key={area.id}
              onClick={() => onSelectArea(area.id)}
              type="button"
            >
              {t(area.title)}
            </button>
          ))}
        </nav>

        {renderActiveArea()}
      </div>
    </section>
  );
}
