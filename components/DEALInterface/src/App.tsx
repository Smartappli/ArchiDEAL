import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import { CommandCenter } from "./components/CommandCenter";
import { ControlProfile } from "./components/ControlProfile";
import { ActivityFeed } from "./components/ActivityFeed";
import { MetricsGrid } from "./components/MetricsGrid";
import { ModuleCard } from "./components/ModuleCard";
import { ModuleDetail } from "./components/ModuleDetail";
import { OperatorQueue } from "./components/OperatorQueue";
import { PlatformHealth } from "./components/PlatformHealth";
import { ServiceConnections } from "./components/ServiceConnections";
import { TopologyMap } from "./components/TopologyMap";
import { LanguageSelector } from "./components/LanguageSelector";
import { moduleRuntimeConfig } from "./config/moduleRegistry";
import { showDemoData } from "./config/runtimeMode";
import { activityFeed, dashboardMetrics, dealModules, moduleControlProfiles, operatorActions } from "./data/dashboard";
import { useModuleConnections } from "./hooks/useModuleConnections";
import { I18nProvider, useI18n } from "./i18n/I18nProvider";
import { localizeModules } from "./i18n/moduleCopy";
import type { ActionPriority, ModuleKey } from "./types";

const actionPriorityRank: Record<ActionPriority, number> = {
  critical: 0,
  high: 1,
  normal: 2,
};

export default function App() {
  return (
    <I18nProvider>
      <AppContent />
    </I18nProvider>
  );
}

function AppContent() {
  const { t } = useI18n();
  const [activeKey, setActiveKey] = useState<ModuleKey>("dealhost");
  const { connections, isRefreshing, refresh } = useModuleConnections(moduleRuntimeConfig);
  const localizedModules = useMemo(() => localizeModules(dealModules, t), [t]);
  const liveModules = useMemo(
    () =>
      localizedModules.map((module) => ({
        ...module,
        metrics: showDemoData ? module.metrics : [],
        status:
          connections[module.key]?.status ?? (showDemoData ? module.status : "attention"),
      })),
    [connections, localizedModules],
  );
  const activeModule = useMemo(
    () => liveModules.find((module) => module.key === activeKey) ?? liveModules[0],
    [activeKey, liveModules],
  );
  const activeProfile = moduleControlProfiles[activeModule.key];
  const nextAction = useMemo(
    () =>
      showDemoData
        ? [...operatorActions].sort(
            (left, right) => actionPriorityRank[left.priority] - actionPriorityRank[right.priority],
          )[0] ?? null
        : null,
    [],
  );
  const nextActionModule = nextAction ? liveModules.find((module) => module.key === nextAction.moduleKey) : undefined;

  return (
    <>
      <a className="skip-link" href="#main-content">
        {t("app.skipToContent")}
      </a>
      <div className="app-shell">
      <aside className="sidebar" aria-label={t("app.navigationAria")}>
        <a className="brand" href="#main-content" aria-label={t("app.homeAria")}>
          <span className="brand__mark">DI</span>
          <span>
            <strong>DEALInterface</strong>
            <small>{t("app.brandSubtitle")}</small>
          </span>
        </a>

        <LanguageSelector />

        <nav className="module-nav" aria-label={t("app.moduleNavigationAria")}>
          {liveModules.map((module) => (
            <button
              aria-pressed={module.key === activeKey}
              className={module.key === activeKey ? "module-nav__item module-nav__item--active" : "module-nav__item"}
              key={module.key}
              onClick={() => setActiveKey(module.key)}
              type="button"
            >
              <span className="module-nav__indicator" style={{ background: module.accent }} aria-hidden="true" />
              <span className="module-nav__label">{module.name}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-card">
          <span>{t("operator.next")}</span>
          {nextAction ? (
            <>
              <strong>{nextAction.title}</strong>
              <p>
                {nextActionModule?.name} / {nextAction.due}. {nextAction.detail}
              </p>
            </>
          ) : (
            <>
              <strong>{t("operator.noPending")}</strong>
              <p>{t("operator.noPendingDetail")}</p>
            </>
          )}
        </div>
      </aside>

      <main className="main-surface" id="main-content" tabIndex={-1}>
        <section className={showDemoData ? "hero" : "hero hero--live"}>
          <div className="hero__content reveal" style={{ "--order": 0 } as CSSProperties}>
            <span className="section-kicker">{t("hero.kicker")}</span>
            <h1>{t("hero.title")}</h1>
            <p>{t("hero.lede")}</p>
            <div className="hero__actions" aria-label={t("hero.actionsAria")}>
              <a href="#modules">{t("hero.inspectModules")}</a>
              <a href="#control-plane">{t("hero.openWorkflows")}</a>
            </div>
          </div>

          {showDemoData ? (
            <div className="hero-console reveal" style={{ "--order": 1 } as CSSProperties}>
              <span>{t("hero.consoleTitle")}</span>
              <strong>84%</strong>
              <p>{t("hero.consoleDescription")}</p>
              <div className="hero-console__bar" aria-hidden="true">
                <span />
              </div>
            </div>
          ) : (
            <PlatformHealth
              connections={connections}
              isRefreshing={isRefreshing}
              modules={liveModules}
              onRefresh={refresh}
            />
          )}
        </section>

        {showDemoData ? <MetricsGrid metrics={dashboardMetrics} /> : null}

        <section className="module-section" id="modules" aria-labelledby="modules-title">
          <div className="section-heading">
            <span className="section-kicker">{t("modules.kicker")}</span>
            <h2 id="modules-title">{t("modules.title")}</h2>
          </div>
          <div className="module-grid">
            {liveModules.map((module, index) => (
              <ModuleCard
                isActive={module.key === activeKey}
                isPending={!connections[module.key]}
                key={module.key}
                module={module}
                onSelect={setActiveKey}
                order={index + 2}
              />
            ))}
          </div>
        </section>

        <section className="dashboard-grid" id="control-plane">
          <ModuleDetail
            connection={connections[activeModule.key]}
            module={activeModule}
            runtime={moduleRuntimeConfig[activeModule.key]}
          />
          <ServiceConnections
            activeKey={activeKey}
            connections={connections}
            isRefreshing={isRefreshing}
            modules={liveModules}
            onRefresh={refresh}
            onSelectModule={setActiveKey}
            runtimes={moduleRuntimeConfig}
          />
          {showDemoData ? (
            <OperatorQueue
              actions={operatorActions}
              activeKey={activeKey}
              modules={liveModules}
              onSelectModule={setActiveKey}
            />
          ) : null}
          {showDemoData ? <ControlProfile module={activeModule} profile={activeProfile} /> : null}
          <TopologyMap activeKey={activeKey} modules={liveModules} />
          {showDemoData ? <CommandCenter /> : null}
          {showDemoData ? <ActivityFeed items={activityFeed} /> : null}
        </section>
      </main>
      </div>
    </>
  );
}
