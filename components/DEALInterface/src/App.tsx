import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { CommandCenter } from "./components/CommandCenter";
import { ControlProfile } from "./components/ControlProfile";
import { ActivityFeed } from "./components/ActivityFeed";
import { MetricsGrid } from "./components/MetricsGrid";
import { ModuleCard } from "./components/ModuleCard";
import { ModuleDetail } from "./components/ModuleDetail";
import {
  getDefaultWorkspaceArea,
  isWorkspaceArea,
  ModuleWorkspace,
} from "./components/ModuleWorkspace";
import { OperatorQueue } from "./components/OperatorQueue";
import { PlatformHealth } from "./components/PlatformHealth";
import { ServiceConnections } from "./components/ServiceConnections";
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

type AppRoute =
  | { view: "home" }
  | { view: "module"; moduleKey: ModuleKey; areaId: string };

const homeRoute: AppRoute = { view: "home" };
const homeHash = "#/";
const moduleKeys: readonly ModuleKey[] = ["dealhost", "dealiot", "dealdata"];

function parseHashRoute(hash: string): AppRoute | null {
  if (hash === homeHash) {
    return homeRoute;
  }

  const match = /^#\/modules\/([a-z]+)\/([a-z]+)$/.exec(hash);
  if (!match) {
    return null;
  }

  const moduleKey = match[1] as ModuleKey;
  const areaId = match[2];
  if (!moduleKeys.includes(moduleKey) || !isWorkspaceArea(moduleKey, areaId)) {
    return null;
  }

  return { view: "module", moduleKey, areaId };
}

function hashForRoute(route: AppRoute): string {
  if (route.view === "home") {
    return homeHash;
  }
  return `#/modules/${route.moduleKey}/${route.areaId}`;
}

function replaceCurrentHash(hash: string) {
  const url = `${window.location.pathname}${window.location.search}${hash}`;
  window.history.replaceState(window.history.state, "", url);
}

export default function App() {
  return (
    <I18nProvider>
      <AppContent />
    </I18nProvider>
  );
}

function AppContent() {
  const { t } = useI18n();
  const [route, setRoute] = useState<AppRoute>(() => parseHashRoute(window.location.hash) ?? homeRoute);
  const [activeKey, setActiveKey] = useState<ModuleKey>(() => {
    const initialRoute = parseHashRoute(window.location.hash);
    return initialRoute?.view === "module" ? initialRoute.moduleKey : "dealhost";
  });
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

  useEffect(() => {
    const syncRouteFromLocation = () => {
      const nextRoute = parseHashRoute(window.location.hash);
      if (!nextRoute) {
        setRoute(homeRoute);
        replaceCurrentHash(homeHash);
        return;
      }

      setRoute(nextRoute);
      if (nextRoute.view === "module") {
        setActiveKey(nextRoute.moduleKey);
      }
    };

    syncRouteFromLocation();
    window.addEventListener("hashchange", syncRouteFromLocation);
    return () => window.removeEventListener("hashchange", syncRouteFromLocation);
  }, []);

  const navigateToRoute = (nextRoute: AppRoute) => {
    setRoute(nextRoute);
    if (nextRoute.view === "module") {
      setActiveKey(nextRoute.moduleKey);
    }

    const nextHash = hashForRoute(nextRoute);
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash;
    }
  };

  const selectModule = (key: ModuleKey) => {
    navigateToRoute({
      view: "module",
      moduleKey: key,
      areaId: getDefaultWorkspaceArea(key),
    });
  };
  const backHome = () => navigateToRoute(homeRoute);
  const selectArea = (areaId: string) => {
    if (route.view === "module" && isWorkspaceArea(route.moduleKey, areaId)) {
      navigateToRoute({ ...route, areaId });
    }
  };
  const focusMainContent = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    document.getElementById("main-content")?.focus();
  };
  const inspectModules = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    const section = document.getElementById("modules");
    section?.scrollIntoView();
    section?.focus();
  };

  return (
    <>
      <a className="skip-link" href="#main-content" onClick={focusMainContent}>
        {t("app.skipToContent")}
      </a>
      <div className="app-shell">
      <aside className="sidebar" aria-label={t("app.navigationAria")}>
        <a
          className="brand"
          href={homeHash}
          aria-label={t("app.homeAria")}
          onClick={(event) => {
            event.preventDefault();
            backHome();
          }}
        >
          <span className="brand__mark">DI</span>
          <span>
            <strong>DEALInterface</strong>
            <small>{t("app.brandSubtitle")}</small>
          </span>
        </a>

        <LanguageSelector />

        <nav className="module-nav" aria-label={t("app.moduleNavigationAria")}>
          <button
            aria-current={route.view === "home" ? "page" : undefined}
            aria-label={t("app.homeAria")}
            className={route.view === "home" ? "module-nav__item module-nav__item--active module-nav__home" : "module-nav__item module-nav__home"}
            onClick={backHome}
            type="button"
          >
            <span className="module-nav__icon" aria-hidden="true">⌂</span>
            <span className="module-nav__copy">
              <span className="module-nav__label">{t("workspace.backHome")}</span>
              <small>{t("hero.kicker")}</small>
            </span>
          </button>
          {liveModules.map((module) => (
            <button
              aria-label={module.name}
              aria-pressed={route.view === "module" && module.key === activeKey}
              className={route.view === "module" && module.key === activeKey ? "module-nav__item module-nav__item--active" : "module-nav__item"}
              data-module-key={module.key}
              key={module.key}
              onClick={() => selectModule(module.key)}
              type="button"
            >
              <span className="module-nav__indicator" style={{ background: module.accent }} aria-hidden="true" />
              <span className="module-nav__copy">
                <span className="module-nav__label">{module.name}</span>
                <small>{module.capabilities[0]}</small>
              </span>
              <span className={`module-nav__status module-nav__status--${module.status}`} aria-hidden="true" />
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
        {route.view === "home" ? (
          <>
            <section className={showDemoData ? "hero" : "hero hero--live"}>
              <div className="hero__content reveal" style={{ "--order": 0 } as CSSProperties}>
                <span className="section-kicker">{t("hero.kicker")}</span>
                <h1>{t("hero.title")}</h1>
                <p>{t("hero.lede")}</p>
                <div className="hero__actions" aria-label={t("hero.actionsAria")}>
                  <a href="#modules" onClick={inspectModules}>{t("hero.inspectModules")}</a>
                  <a
                    href={hashForRoute({
                      view: "module",
                      moduleKey: "dealhost",
                      areaId: getDefaultWorkspaceArea("dealhost"),
                    })}
                    onClick={(event) => {
                      event.preventDefault();
                      selectModule("dealhost");
                    }}
                  >
                    {t("hero.openWorkflows")}
                  </a>
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

            <section className="module-section" id="modules" aria-label={t("modules.kicker")} tabIndex={-1}>
              <div className="section-heading">
                <span className="section-kicker">{t("modules.kicker")}</span>
              </div>
              <div className="module-grid">
                {liveModules.map((module, index) => (
                  <ModuleCard
                    isActive={false}
                    isPending={!connections[module.key]}
                    key={module.key}
                    module={module}
                    onSelect={selectModule}
                    order={index + 2}
                  />
                ))}
              </div>
            </section>

            <section className="dashboard-grid" id="control-plane">
              <ServiceConnections
                activeKey={activeKey}
                connections={connections}
                isRefreshing={isRefreshing}
                modules={liveModules}
                onRefresh={refresh}
                onSelectModule={selectModule}
                runtimes={moduleRuntimeConfig}
              />
              {showDemoData ? (
                <OperatorQueue
                  actions={operatorActions}
                  activeKey={activeKey}
                  modules={liveModules}
                  onSelectModule={selectModule}
                />
              ) : null}
              {showDemoData ? <CommandCenter /> : null}
              {showDemoData ? <ActivityFeed items={activityFeed} /> : null}
            </section>
          </>
        ) : (
          <>
            <ModuleWorkspace
              activeAreaId={route.areaId}
              connection={connections[activeModule.key]}
              module={activeModule}
              onBackHome={backHome}
              onSelectArea={selectArea}
            />
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
                onSelectModule={selectModule}
                runtimes={moduleRuntimeConfig}
              />
              {showDemoData ? <ControlProfile module={activeModule} profile={activeProfile} /> : null}
            </section>
          </>
        )}
        <footer className="app-footer">© 2026 Smartappli</footer>
      </main>
      </div>
    </>
  );
}
