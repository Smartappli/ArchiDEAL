import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  createRuntimeDeployment,
  createRuntimeIdempotencyKey,
  getRuntimeOperation,
  type ApiProblem,
  type HostedApplication,
  listManagementResources,
  listRuntimeDeployments,
  listRuntimeEnvironments,
  listRuntimeOperations,
  ManagementApiError,
  requestRuntimeDeploymentAction,
  requestRuntimeLogSnapshot,
  type RuntimeComponentConfiguration,
  type RuntimeDeployment,
  type RuntimeEnvironment,
  type RuntimeLogSnapshot,
  type RuntimeMutationResult,
  type RuntimeOperation,
  type RuntimeScaling,
  undeployRuntimeDeployment,
  updateRuntimeDeploymentConfiguration,
} from "../lib/managementApi";

interface RuntimeDeploymentPanelProps {
  areaDescription: string;
  areaTitle: string;
  moduleName: string;
}

const TRANSITIONAL_STATES = new Set(["pending", "reconciling", "deleting"]);
const STARTABLE_STATES = new Set(["stopped", "failed", "unknown"]);
const STOPPABLE_STATES = new Set(["running", "degraded", "failed", "unknown"]);
const RESTARTABLE_STATES = new Set(["running", "degraded"]);
const OPERATION_POLL_DELAY_MS = 1_500;
const OPERATION_POLL_MAX_DELAY_MS = 12_000;
const OPERATION_POLL_MAX_CONSECUTIVE_FAILURES = 5;
const MAX_LOG_TAIL_LINES = 1_000;
const MAX_LOG_SINCE_SECONDS = 604_800;

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

function prettyConfiguration(value: RuntimeComponentConfiguration | undefined) {
  return JSON.stringify(value ?? {}, null, 2);
}

function prettyScaling(value: RuntimeScaling | undefined) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseComponentConfiguration(value: string): RuntimeComponentConfiguration {
  const parsed: unknown = JSON.parse(value);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("root");
  }
  for (const componentValue of Object.values(parsed)) {
    if (
      typeof componentValue !== "object"
      || componentValue === null
      || Array.isArray(componentValue)
      || Object.values(componentValue).some((entry) => typeof entry !== "string")
    ) {
      throw new Error("component");
    }
  }
  return parsed as RuntimeComponentConfiguration;
}

function parseScaling(value: string): RuntimeScaling {
  const parsed: unknown = JSON.parse(value);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("root");
  }
  for (const componentValue of Object.values(parsed)) {
    if (typeof componentValue !== "object" || componentValue === null || Array.isArray(componentValue)) {
      throw new Error("component");
    }
    const scaling = componentValue as Record<string, unknown>;
    if (scaling.mode === "fixed") {
      if (
        !Number.isSafeInteger(scaling.replicas)
        || Number(scaling.replicas) < 1
        || Number(scaling.replicas) > 50
      ) {
        throw new Error("fixed");
      }
      continue;
    }
    if (scaling.mode === "autoscale") {
      if (
        !Number.isSafeInteger(scaling.min_replicas)
        || !Number.isSafeInteger(scaling.max_replicas)
        || !Number.isSafeInteger(scaling.target_cpu_utilization)
        || Number(scaling.min_replicas) < 1
        || Number(scaling.max_replicas) < Number(scaling.min_replicas)
        || Number(scaling.max_replicas) > 50
        || Number(scaling.target_cpu_utilization) < 10
        || Number(scaling.target_cpu_utilization) > 90
      ) {
        throw new Error("autoscale");
      }
      continue;
    }
    throw new Error("mode");
  }
  return parsed as RuntimeScaling;
}

function defaultScaling(): RuntimeScaling {
  // DEALHost expands an empty policy against the selected immutable release.
  // The mutable application catalog may no longer contain the same module slugs
  // when an operator rolls back to an older published version.
  return {};
}

function isRuntimeLogSnapshot(value: RuntimeOperation["result"]): value is RuntimeLogSnapshot {
  return Boolean(
    value
    && typeof value === "object"
    && "content" in value
    && typeof value.content === "string"
    && "component" in value
    && typeof value.component === "string",
  );
}

function isPendingOperation(operation: RuntimeOperation | undefined) {
  return operation?.status === "queued" || operation?.status === "running";
}

export function RuntimeDeploymentPanel({
  areaDescription,
  areaTitle,
  moduleName,
}: RuntimeDeploymentPanelProps) {
  const { t } = useI18n();
  const [applications, setApplications] = useState<HostedApplication[]>([]);
  const [environments, setEnvironments] = useState<RuntimeEnvironment[]>([]);
  const [selectedApplicationId, setSelectedApplicationId] = useState<number>();
  const [deployments, setDeployments] = useState<RuntimeDeployment[]>([]);
  const [selectedDeploymentId, setSelectedDeploymentId] = useState<string>();
  const [operations, setOperations] = useState<RuntimeOperation[]>([]);
  const [activeOperation, setActiveOperation] = useState<RuntimeOperation>();
  const [logSnapshot, setLogSnapshot] = useState<RuntimeLogSnapshot>();
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(true);
  const [isLoadingDeployments, setIsLoadingDeployments] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [catalogProblem, setCatalogProblem] = useState<ApiProblem>();
  const [deploymentProblem, setDeploymentProblem] = useState<ApiProblem>();
  const [operationHistoryProblem, setOperationHistoryProblem] = useState<ApiProblem>();
  const [mutationProblem, setMutationProblem] = useState<ApiProblem>();
  const [successKey, setSuccessKey] = useState<MessageKey>();
  const [readOnly, setReadOnly] = useState(false);
  const [catalogReloadKey, setCatalogReloadKey] = useState(0);
  const [deploymentReloadKey, setDeploymentReloadKey] = useState(0);
  const [operationReloadKey, setOperationReloadKey] = useState(0);
  const [configurationText, setConfigurationText] = useState("{}");
  const [secretRefsText, setSecretRefsText] = useState("{}");
  const [scalingText, setScalingText] = useState("{}");
  const [configurationDirty, setConfigurationDirty] = useState(false);
  const [deployEnvironment, setDeployEnvironment] = useState("");
  const [deployVersion, setDeployVersion] = useState("");
  const [deployConfigurationText, setDeployConfigurationText] = useState("{}");
  const [deploySecretRefsText, setDeploySecretRefsText] = useState("{}");
  const [deployScalingText, setDeployScalingText] = useState("{}");
  const [logComponent, setLogComponent] = useState("");
  const [logTailLines, setLogTailLines] = useState(200);
  const [logSinceSeconds, setLogSinceSeconds] = useState(3600);
  const idempotencyKeys = useRef(new Map<string, string>());

  const selectedApplication = useMemo(
    () => applications.find((application) => application.id === selectedApplicationId),
    [applications, selectedApplicationId],
  );
  const activeDeployments = useMemo(
    () => deployments.filter((deployment) => deployment.observed_state !== "deleted"),
    [deployments],
  );
  const selectedDeployment = useMemo(
    () => activeDeployments.find((deployment) => deployment.id === selectedDeploymentId),
    [activeDeployments, selectedDeploymentId],
  );
  const selectedEnvironment = useMemo(
    () => environments.find((environment) => environment.slug === selectedDeployment?.environment),
    [environments, selectedDeployment?.environment],
  );
  const availableEnvironments = useMemo(() => {
    const occupied = new Set(activeDeployments.map((deployment) => deployment.environment));
    return environments.filter((environment) => environment.enabled && !occupied.has(environment.slug));
  }, [activeDeployments, environments]);
  const versionOptions = selectedApplication?.versions ?? [];
  const operationPending = isPendingOperation(activeOperation);
  const logOperationPending = operationPending && activeOperation?.type === "log_snapshot";
  const mutationOperationPending = operationPending && activeOperation?.type !== "log_snapshot";
  const runtimeUnavailable = Boolean(selectedDeployment && selectedEnvironment?.enabled !== true);
  const runtimeTransitionBusy = isMutating || mutationOperationPending || Boolean(
    selectedDeployment && TRANSITIONAL_STATES.has(selectedDeployment.observed_state),
  );
  const runtimeBusy = runtimeTransitionBusy || runtimeUnavailable;
  const configuredMaxLogLines = selectedEnvironment?.capabilities.logs.max_lines;
  const maxLogLines = Math.min(
    MAX_LOG_TAIL_LINES,
    Number.isSafeInteger(configuredMaxLogLines) && Number(configuredMaxLogLines) > 0
      ? Number(configuredMaxLogLines)
      : MAX_LOG_TAIL_LINES,
  );

  function normalizeProblem(error: unknown): ApiProblem {
    return error instanceof ManagementApiError
      ? error.problem
      : { kind: "server", message: t("management.unknownError"), retryable: true };
  }

  function registerMutationProblem(error: unknown) {
    const problem = normalizeProblem(error);
    setMutationProblem(problem);
    if (problem.kind === "authorization") setReadOnly(true);
  }

  function registerLocalConfigurationProblem() {
    setMutationProblem({
      kind: "validation",
      message: t("management.runtime.configurationInvalid"),
      retryable: false,
    });
  }

  function registerLocalLogProblem() {
    setMutationProblem({
      kind: "validation",
      message: t("management.runtime.logRequestInvalid"),
      retryable: false,
    });
  }

  function reloadRuntimeData() {
    setCatalogReloadKey((value) => value + 1);
    setDeploymentReloadKey((value) => value + 1);
    setOperationReloadKey((value) => value + 1);
  }

  function commandKey(fingerprint: string) {
    const current = idempotencyKeys.current.get(fingerprint);
    if (current) return current;
    const created = createRuntimeIdempotencyKey();
    idempotencyKeys.current.set(fingerprint, created);
    return created;
  }

  function settleCommandKey(fingerprint: string, error?: unknown) {
    if (error === undefined || !normalizeProblem(error).retryable) {
      idempotencyKeys.current.delete(fingerprint);
    }
  }

  function applyMutationResult(result: RuntimeMutationResult, queuedKey: MessageKey) {
    setDeployments((current) => {
      const present = current.some((deployment) => deployment.id === result.deployment.id);
      return present
        ? current.map((deployment) => (
          deployment.id === result.deployment.id ? result.deployment : deployment
        ))
        : [...current, result.deployment];
    });
    setSelectedDeploymentId(result.deployment.id);
    setActiveOperation(result.operation);
    setSuccessKey(result.operation.status === "succeeded"
      ? "management.runtime.operationSucceeded"
      : queuedKey);
    setOperationReloadKey((value) => value + 1);
  }

  function registerLogOperation(operation: RuntimeOperation) {
    setActiveOperation(operation);
    if (operation.status === "succeeded" && isRuntimeLogSnapshot(operation.result)) {
      setLogSnapshot(operation.result);
      setSuccessKey("management.runtime.logsReady");
    } else {
      setSuccessKey("management.runtime.operationQueued");
    }
    setOperationReloadKey((value) => value + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoadingCatalog(true);
    setCatalogProblem(undefined);
    Promise.all([
      listManagementResources<HostedApplication>(
        "/dealhost/api/hosting/applications/",
        controller.signal,
      ),
      listRuntimeEnvironments(controller.signal),
    ])
      .then(([nextApplications, environmentPage]) => {
        setApplications(nextApplications);
        setEnvironments(environmentPage.results);
        setSelectedApplicationId((current) => (
          nextApplications.some((application) => application.id === current)
            ? current
            : nextApplications[0]?.id
        ));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCatalogProblem(normalizeProblem(error));
      })
      .finally(() => setIsLoadingCatalog(false));
    return () => controller.abort();
  }, [catalogReloadKey, t]);

  useEffect(() => {
    if (!selectedApplication) {
      setDeployments([]);
      setSelectedDeploymentId(undefined);
      return;
    }
    const controller = new AbortController();
    setIsLoadingDeployments(true);
    setDeploymentProblem(undefined);
    listRuntimeDeployments(selectedApplication.id, controller.signal)
      .then((page) => {
        setDeployments(page.results);
        const available = page.results.filter((deployment) => deployment.observed_state !== "deleted");
        setSelectedDeploymentId((current) => (
          available.some((deployment) => deployment.id === current)
            ? current
            : available[0]?.id
        ));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDeploymentProblem(normalizeProblem(error));
      })
      .finally(() => setIsLoadingDeployments(false));
    return () => controller.abort();
  }, [deploymentReloadKey, selectedApplication?.id, t]);

  useEffect(() => {
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    setActiveOperation(undefined);
    setOperations([]);
    setOperationHistoryProblem(undefined);
    setLogSnapshot(undefined);
  }, [selectedApplication?.id]);

  useEffect(() => {
    if (!selectedDeployment) {
      setConfigurationText("{}");
      setSecretRefsText("{}");
      setScalingText("{}");
      setConfigurationDirty(false);
      setOperations([]);
      setOperationHistoryProblem(undefined);
      setActiveOperation(undefined);
      setLogComponent("");
      return;
    }
    setOperations([]);
    setOperationHistoryProblem(undefined);
    setActiveOperation((current) => (
      current?.deployment_id === selectedDeployment.id ? current : undefined
    ));
    setConfigurationText(prettyConfiguration(selectedDeployment.configuration));
    setSecretRefsText(prettyConfiguration(selectedDeployment.secret_refs));
    setScalingText(prettyScaling(selectedDeployment.scaling));
    setConfigurationDirty(false);
    setLogComponent(selectedDeployment.components[0]?.slug ?? "");
    setLogSnapshot(undefined);
  }, [selectedDeployment?.id]);

  useEffect(() => {
    if (!selectedDeployment || configurationDirty) return;
    setConfigurationText(prettyConfiguration(selectedDeployment.configuration));
    setSecretRefsText(prettyConfiguration(selectedDeployment.secret_refs));
    setScalingText(prettyScaling(selectedDeployment.scaling));
  }, [configurationDirty, selectedDeployment?.revision]);

  useEffect(() => {
    if (!selectedDeployment) return;
    const controller = new AbortController();
    setOperationHistoryProblem(undefined);
    listRuntimeOperations(selectedDeployment.id, controller.signal)
      .then((page) => {
        setOperations(page.results);
        const resumableOperation = page.results.find(isPendingOperation);
        setActiveOperation((current) => {
          if (current?.deployment_id !== selectedDeployment.id) return resumableOperation;
          if (!isPendingOperation(current)) return resumableOperation ?? current;
          const listedCurrent = page.results.find((operation) => operation.id === current.id);
          return isPendingOperation(listedCurrent) ? listedCurrent : current;
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setOperationHistoryProblem(normalizeProblem(error));
      });
    return () => controller.abort();
  }, [operationReloadKey, selectedDeployment?.id, t]);

  useEffect(() => {
    const versions = selectedApplication?.versions ?? [];
    const preferred = versions.some((version) => version.version === selectedApplication?.current_version)
      ? selectedApplication?.current_version
      : versions[0]?.version;
    setDeployVersion(preferred ?? "");
    setDeployConfigurationText("{}");
    setDeploySecretRefsText("{}");
    setDeployScalingText(prettyScaling(defaultScaling()));
  }, [selectedApplication?.id]);

  useEffect(() => {
    if (!availableEnvironments.some((environment) => environment.slug === deployEnvironment)) {
      setDeployEnvironment(availableEnvironments[0]?.slug ?? "");
    }
  }, [availableEnvironments, deployEnvironment]);

  useEffect(() => {
    setLogTailLines((current) => (
      Number.isSafeInteger(current)
        ? Math.min(Math.max(current, 1), maxLogLines)
        : Math.min(200, maxLogLines)
    ));
  }, [maxLogLines]);

  useEffect(() => {
    if (!activeOperation || !operationPending) return;
    const operationId = activeOperation.id;
    const controller = new AbortController();
    let timeoutId: number | undefined;
    let consecutiveFailures = 0;

    function schedulePoll(delay: number) {
      timeoutId = window.setTimeout(poll, delay);
    }

    async function poll() {
      try {
        const nextOperation = await getRuntimeOperation(operationId, controller.signal);
        consecutiveFailures = 0;
        setMutationProblem(undefined);
        setActiveOperation(nextOperation);
        if (isPendingOperation(nextOperation)) {
          schedulePoll(OPERATION_POLL_DELAY_MS);
          return;
        }
        setOperationReloadKey((value) => value + 1);
        setDeploymentReloadKey((value) => value + 1);
        if (nextOperation.status === "failed") {
          setMutationProblem({
            kind: "server",
            message: nextOperation.error?.detail ?? t("management.runtime.operationFailed"),
            retryable: nextOperation.error?.retryable ?? true,
          });
          setSuccessKey(undefined);
          return;
        }
        if (isRuntimeLogSnapshot(nextOperation.result)) {
          setLogSnapshot(nextOperation.result);
          setSuccessKey("management.runtime.logsReady");
        } else {
          setSuccessKey("management.runtime.operationSucceeded");
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const problem = normalizeProblem(error);
        setMutationProblem(problem);
        consecutiveFailures += 1;
        if (problem.retryable && consecutiveFailures < OPERATION_POLL_MAX_CONSECUTIVE_FAILURES) {
          schedulePoll(Math.min(
            OPERATION_POLL_DELAY_MS * (2 ** consecutiveFailures),
            OPERATION_POLL_MAX_DELAY_MS,
          ));
        }
      }
    }

    schedulePoll(OPERATION_POLL_DELAY_MS);
    return () => {
      controller.abort();
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [activeOperation?.id, operationPending, operationReloadKey, t]);

  async function deployApplication(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication) return;
    let configuration: RuntimeComponentConfiguration;
    let secretRefs: RuntimeComponentConfiguration;
    let scaling: RuntimeScaling;
    try {
      configuration = parseComponentConfiguration(deployConfigurationText);
      secretRefs = parseComponentConfiguration(deploySecretRefsText);
      scaling = parseScaling(deployScalingText);
    } catch {
      registerLocalConfigurationProblem();
      return;
    }
    setIsMutating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    const fingerprint = JSON.stringify({
      command: "deploy",
      application: selectedApplication.id,
      revision: selectedApplication.revision,
      environment: deployEnvironment,
      version: deployVersion,
      scaling,
      configuration,
      secretRefs,
    });
    try {
      const result = await createRuntimeDeployment(
        selectedApplication,
        {
          environment: deployEnvironment,
          version: deployVersion,
          scaling,
          configuration,
          secret_refs: secretRefs,
        },
        commandKey(fingerprint),
      );
      settleCommandKey(fingerprint);
      applyMutationResult(result, "management.runtime.operationQueued");
    } catch (error) {
      settleCommandKey(fingerprint, error);
      registerMutationProblem(error);
    } finally {
      setIsMutating(false);
    }
  }

  async function performAction(action: "start" | "stop" | "restart") {
    if (!selectedDeployment) return;
    setIsMutating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    const fingerprint = JSON.stringify({
      command: action,
      deployment: selectedDeployment.id,
      revision: selectedDeployment.revision,
    });
    try {
      const result = await requestRuntimeDeploymentAction(
        selectedDeployment,
        { action },
        commandKey(fingerprint),
      );
      settleCommandKey(fingerprint);
      applyMutationResult(result, "management.runtime.operationQueued");
    } catch (error) {
      settleCommandKey(fingerprint, error);
      registerMutationProblem(error);
    } finally {
      setIsMutating(false);
    }
  }

  async function undeploy() {
    if (!selectedDeployment) return;
    if (!window.confirm(t("management.runtime.undeployConfirm", {
      application: selectedDeployment.application.name,
      environment: selectedDeployment.environment,
    }))) return;
    setIsMutating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    const fingerprint = JSON.stringify({
      command: "undeploy",
      deployment: selectedDeployment.id,
      revision: selectedDeployment.revision,
    });
    try {
      const result = await undeployRuntimeDeployment(
        selectedDeployment,
        commandKey(fingerprint),
      );
      settleCommandKey(fingerprint);
      applyMutationResult(result, "management.runtime.operationQueued");
    } catch (error) {
      settleCommandKey(fingerprint, error);
      registerMutationProblem(error);
    } finally {
      setIsMutating(false);
    }
  }

  async function saveConfiguration(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDeployment) return;
    let configuration: RuntimeComponentConfiguration;
    let secretRefs: RuntimeComponentConfiguration;
    let scaling: RuntimeScaling;
    try {
      configuration = parseComponentConfiguration(configurationText);
      secretRefs = parseComponentConfiguration(secretRefsText);
      scaling = parseScaling(scalingText);
    } catch {
      registerLocalConfigurationProblem();
      return;
    }
    setIsMutating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    const fingerprint = JSON.stringify({
      command: "configure",
      deployment: selectedDeployment.id,
      revision: selectedDeployment.revision,
      configuration,
      secretRefs,
      scaling,
    });
    try {
      const result = await updateRuntimeDeploymentConfiguration(
        selectedDeployment,
        { configuration, secret_refs: secretRefs, scaling },
        commandKey(fingerprint),
      );
      settleCommandKey(fingerprint);
      applyMutationResult(result, "management.runtime.operationQueued");
      setConfigurationText(prettyConfiguration(result.deployment.configuration));
      setSecretRefsText(prettyConfiguration(result.deployment.secret_refs));
      setScalingText(prettyScaling(result.deployment.scaling));
      setConfigurationDirty(false);
    } catch (error) {
      settleCommandKey(fingerprint, error);
      registerMutationProblem(error);
    } finally {
      setIsMutating(false);
    }
  }

  async function requestLogs(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDeployment || !logComponent) return;
    if (
      !Number.isSafeInteger(logTailLines)
      || logTailLines < 1
      || logTailLines > maxLogLines
      || !Number.isSafeInteger(logSinceSeconds)
      || logSinceSeconds < 1
      || logSinceSeconds > MAX_LOG_SINCE_SECONDS
    ) {
      registerLocalLogProblem();
      return;
    }
    setIsMutating(true);
    setMutationProblem(undefined);
    setSuccessKey(undefined);
    setLogSnapshot(undefined);
    const fingerprint = JSON.stringify({
      command: "log_snapshot",
      deployment: selectedDeployment.id,
      revision: selectedDeployment.revision,
      component: logComponent,
      tailLines: logTailLines,
      sinceSeconds: logSinceSeconds,
    });
    try {
      const operation = await requestRuntimeLogSnapshot(
        selectedDeployment,
        {
          component: logComponent,
          tail_lines: logTailLines,
          since_seconds: logSinceSeconds,
        },
        commandKey(fingerprint),
      );
      settleCommandKey(fingerprint);
      registerLogOperation(operation);
    } catch (error) {
      settleCommandKey(fingerprint, error);
      registerMutationProblem(error);
    } finally {
      setIsMutating(false);
    }
  }

  function renderProblem(problem: ApiProblem) {
    return (
      <div className={`management-notice management-notice--${problem.kind}`} role="alert">
        <strong>{t(`management.error.${problem.kind}` as MessageKey)}</strong>
        <p>{problem.message}</p>
        {problem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
        {problem.status === 412 ? (
          <button
            onClick={() => {
              setMutationProblem(undefined);
              setConfigurationDirty(false);
              setCatalogReloadKey((value) => value + 1);
              setDeploymentReloadKey((value) => value + 1);
            }}
            type="button"
          >
            {t("management.runtime.reloadAfterConflict")}
          </button>
        ) : null}
      </div>
    );
  }

  const canStart = Boolean(
    selectedDeployment && STARTABLE_STATES.has(selectedDeployment.observed_state),
  );
  const canStop = Boolean(
    selectedDeployment && STOPPABLE_STATES.has(selectedDeployment.observed_state),
  );
  const canRestart = Boolean(
    selectedDeployment && RESTARTABLE_STATES.has(selectedDeployment.observed_state),
  );
  const totalReadyReplicas = selectedDeployment?.components.reduce(
    (total, component) => total + component.ready_replicas,
    0,
  ) ?? 0;
  const totalDesiredReplicas = selectedDeployment?.components.reduce(
    (total, component) => total + component.desired_replicas,
    0,
  ) ?? 0;

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>/dealhost/api/hosting/deployments/</code>
          <button onClick={reloadRuntimeData} type="button">
            {t("management.retry")}
          </button>
        </div>

        <div className="management-notice management-notice--neutral">
          <strong>{t("management.runtime.noticeTitle")}</strong>
          <p>{t("management.runtime.noticeDetail")}</p>
        </div>

        {isLoadingCatalog ? <p className="management-state">{t("management.loading")}</p> : null}
        {catalogProblem ? renderProblem(catalogProblem) : null}
        {!isLoadingCatalog && !catalogProblem && applications.length === 0 ? (
          <div className="management-empty">
            <strong>{t("management.emptyTitle")}</strong>
            <p>{t("management.runtime.noApplications")}</p>
          </div>
        ) : null}

        {applications.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("management.application.listAria")} className="management-selector">
              {applications.map((application) => (
                <button
                  aria-current={application.id === selectedApplicationId ? "true" : undefined}
                  className={application.id === selectedApplicationId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  key={application.id}
                  onClick={() => setSelectedApplicationId(application.id)}
                  type="button"
                >
                  <strong>{application.name}</strong>
                  <code>{application.slug}</code>
                  <span>{t("management.applicationMeta", { version: application.current_version || t("management.noRelease") })}</span>
                </button>
              ))}
            </nav>

            <div className="runtime-stack">
              {isLoadingDeployments ? <p className="management-state">{t("management.runtime.loading")}</p> : null}
              {deploymentProblem ? renderProblem(deploymentProblem) : null}

              {!isLoadingDeployments && !deploymentProblem && activeDeployments.length > 0 ? (
                <section className="runtime-detail" aria-labelledby="runtime-detail-title">
                  <div className="runtime-detail__heading">
                    <div>
                      <h3 id="runtime-detail-title">{t("management.runtime.detailTitle")}</h3>
                      <code>{selectedDeployment?.id}</code>
                    </div>
                    {selectedDeployment ? (
                      <span className={`runtime-status runtime-status--${selectedDeployment.observed_state}`} role="status">
                        {t(`management.runtime.status.${selectedDeployment.observed_state}` as MessageKey)}
                      </span>
                    ) : null}
                  </div>

                  {activeDeployments.length > 1 ? (
                    <label className="runtime-detail__selector">
                      <span>{t("management.runtime.deployedEnvironment")}</span>
                      <select
                        onChange={(event) => setSelectedDeploymentId(event.target.value)}
                        value={selectedDeploymentId}
                      >
                        {activeDeployments.map((deployment) => (
                          <option key={deployment.id} value={deployment.id}>
                            {deployment.environment} — {t(`management.runtime.status.${deployment.observed_state}` as MessageKey)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}

                  {selectedDeployment ? (
                    <>
                      <dl className="runtime-summary">
                        <div><dt>{t("management.runtime.environment")}</dt><dd>{selectedDeployment.environment}</dd></div>
                        <div><dt>{t("management.runtime.version")}</dt><dd>{selectedDeployment.version}</dd></div>
                        <div><dt>{t("management.runtime.desiredState")}</dt><dd>{t(`management.runtime.desired.${selectedDeployment.desired_state}` as MessageKey)}</dd></div>
                        <div><dt>{t("management.runtime.replicas")}</dt><dd>{totalReadyReplicas} / {totalDesiredReplicas}</dd></div>
                        <div><dt>{t("management.runtime.revision")}</dt><dd>{selectedDeployment.revision}</dd></div>
                        <div><dt>{t("management.runtime.lastReconciled")}</dt><dd>{selectedDeployment.last_reconciled_at ?? t("management.runtime.never")}</dd></div>
                      </dl>

                      {selectedDeployment.last_error ? (
                        <div className="management-notice management-notice--server" role="alert">
                          <strong>{t("management.runtime.lastError")}</strong>
                          <p>{selectedDeployment.last_error}</p>
                        </div>
                      ) : null}
                      {runtimeUnavailable ? (
                        <div className="management-notice management-notice--network" role="alert">
                          <strong>{t("management.runtime.environmentUnavailableTitle")}</strong>
                          <p>{t("management.runtime.environmentUnavailableDetail")}</p>
                        </div>
                      ) : null}
                      {activeOperation ? (
                        <div className="runtime-operation" aria-live="polite">
                          <strong>{t(`management.runtime.operation.${activeOperation.type}` as MessageKey)}</strong>
                          <span>{t(`management.runtime.operationStatus.${activeOperation.status}` as MessageKey)}</span>
                          {activeOperation.progress.percent !== null ? (
                            <progress max={100} value={activeOperation.progress.percent}>
                              {activeOperation.progress.percent}%
                            </progress>
                          ) : null}
                          {activeOperation.progress.stage ? <small>{activeOperation.progress.stage}</small> : null}
                        </div>
                      ) : null}
                      {mutationProblem ? renderProblem(mutationProblem) : null}
                      {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}

                      <div className="runtime-actions" aria-label={t("management.runtime.actionsAria")}>
                        <button disabled={readOnly || runtimeBusy || !canStart || selectedEnvironment?.capabilities.start_stop === false} onClick={() => performAction("start")} type="button">
                          {t("management.runtime.start")}
                        </button>
                        <button disabled={readOnly || runtimeBusy || !canStop || selectedEnvironment?.capabilities.start_stop === false} onClick={() => performAction("stop")} type="button">
                          {t("management.runtime.stop")}
                        </button>
                        <button disabled={readOnly || runtimeBusy || !canRestart || selectedEnvironment?.capabilities.restart === false} onClick={() => performAction("restart")} type="button">
                          {t("management.runtime.restart")}
                        </button>
                        <button className="management-button--danger" disabled={readOnly || runtimeTransitionBusy} onClick={undeploy} type="button">
                          {t("management.runtime.undeploy")}
                        </button>
                      </div>

                      <section className="runtime-components" aria-labelledby="runtime-components-title">
                        <h4 id="runtime-components-title">{t("management.runtime.components")}</h4>
                        {selectedDeployment.components.length ? (
                          <ul>
                            {selectedDeployment.components.map((component) => (
                              <li key={component.module_id}>
                                <div><strong>{component.slug}</strong><code>{component.image_digest}</code></div>
                                <span>{component.ready_replicas} / {component.desired_replicas}</span>
                                <span>{component.health}</span>
                                <span>{t("management.runtime.restarts", { count: component.restart_count })}</span>
                                {component.last_error ? <p>{component.last_error}</p> : null}
                              </li>
                            ))}
                          </ul>
                        ) : <p>{t("management.runtime.noComponents")}</p>}
                      </section>

                      <form className="management-detail-form runtime-configuration" onSubmit={saveConfiguration}>
                        <div className="management-detail-form__heading">
                          <div><h3>{t("management.runtime.configurationTitle")}</h3></div>
                        </div>
                        <label className="management-detail-form__wide">
                          <span>{t("management.runtime.configuration")}</span>
                          <textarea disabled={readOnly || runtimeBusy} onChange={(event) => {
                            setConfigurationText(event.target.value);
                            setConfigurationDirty(true);
                          }} rows={9} value={configurationText} />
                        </label>
                        <label className="management-detail-form__wide">
                          <span>{t("management.runtime.secretRefs")}</span>
                          <textarea disabled={readOnly || runtimeBusy} onChange={(event) => {
                            setSecretRefsText(event.target.value);
                            setConfigurationDirty(true);
                          }} rows={7} value={secretRefsText} />
                        </label>
                        <label className="management-detail-form__wide">
                          <span>{t("management.runtime.scaling")}</span>
                          <textarea disabled={readOnly || runtimeBusy} onChange={(event) => {
                            setScalingText(event.target.value);
                            setConfigurationDirty(true);
                          }} rows={7} value={scalingText} />
                        </label>
                        <p className="management-detail-form__help">{t("management.runtime.configurationHelp")}</p>
                        <div className="management-detail-form__actions">
                          <button disabled={readOnly || runtimeBusy} type="submit">{t("management.runtime.saveConfiguration")}</button>
                        </div>
                      </form>

                      <section className="runtime-logs" aria-labelledby="runtime-logs-title">
                        <div>
                          <h3 id="runtime-logs-title">{t("management.runtime.logsTitle")}</h3>
                          <p>{t("management.runtime.logsHelp")}</p>
                        </div>
                        <form onSubmit={requestLogs}>
                          <label>
                            <span>{t("management.runtime.component")}</span>
                            <select disabled={readOnly || runtimeBusy || logOperationPending} onChange={(event) => setLogComponent(event.target.value)} required value={logComponent}>
                              {selectedDeployment.components.map((component) => <option key={component.module_id} value={component.slug}>{component.slug}</option>)}
                            </select>
                          </label>
                          <label>
                            <span>{t("management.runtime.tailLines")}</span>
                            <input disabled={readOnly || runtimeBusy || logOperationPending} max={maxLogLines} min={1} onChange={(event) => setLogTailLines(event.target.valueAsNumber)} required type="number" value={logTailLines} />
                          </label>
                          <label>
                            <span>{t("management.runtime.sinceSeconds")}</span>
                            <input disabled={readOnly || runtimeBusy || logOperationPending} max={MAX_LOG_SINCE_SECONDS} min={1} onChange={(event) => setLogSinceSeconds(event.target.valueAsNumber)} required type="number" value={logSinceSeconds} />
                          </label>
                          <button disabled={readOnly || runtimeBusy || logOperationPending || !logComponent || selectedEnvironment?.capabilities.logs === undefined} type="submit">{t("management.runtime.requestLogs")}</button>
                        </form>
                        {logSnapshot ? (
                          <div className="runtime-logs__snapshot">
                            <p>{t("management.runtime.logMeta", { component: logSnapshot.component, lines: logSnapshot.line_count })}</p>
                            {logSnapshot.truncated ? <strong>{t("management.runtime.logTruncated")}</strong> : null}
                            <pre tabIndex={0}>{logSnapshot.content}</pre>
                          </div>
                        ) : null}
                      </section>

                      <section className="management-history runtime-history" aria-labelledby="runtime-history-title">
                        <h3 id="runtime-history-title">{t("management.runtime.operationHistory")}</h3>
                        {operationHistoryProblem ? renderProblem(operationHistoryProblem) : null}
                        {operations.length ? (
                          <ul>
                            {operations.map((operation) => (
                              <li key={operation.id}>
                                <strong>{t(`management.runtime.operation.${operation.type}` as MessageKey)}</strong>
                                <span>{t(`management.runtime.operationStatus.${operation.status}` as MessageKey)}</span>
                                {operation.error?.detail ? <p>{operation.error.detail}</p> : null}
                              </li>
                            ))}
                          </ul>
                        ) : operationHistoryProblem ? null : <p>{t("management.runtime.noOperations")}</p>}
                      </section>
                    </>
                  ) : null}
                </section>
              ) : null}

              {!isLoadingDeployments && !deploymentProblem && activeDeployments.length === 0 ? (
                <div className="management-empty">
                  <strong>{t("management.runtime.notDeployedTitle")}</strong>
                  <p>{t("management.runtime.notDeployedDetail")}</p>
                </div>
              ) : null}

              {selectedApplication && activeDeployments.length === 0 && availableEnvironments.length === 0 ? (
                <div className="management-notice management-notice--network" role="alert">
                  <strong>{t("management.runtime.environmentUnavailableTitle")}</strong>
                  <p>{t("management.runtime.environmentUnavailableDetail")}</p>
                </div>
              ) : null}

              {selectedApplication && availableEnvironments.length > 0 ? (
                <form className="management-detail-form runtime-create" onSubmit={deployApplication}>
                  <div className="management-detail-form__heading">
                    <div>
                      <h3>{activeDeployments.length ? t("management.runtime.deployAnother") : t("management.runtime.deployTitle")}</h3>
                      <code>{selectedApplication.slug}</code>
                    </div>
                    <span className="management-revision">{t("management.application.revision", { revision: selectedApplication.revision })}</span>
                  </div>
                  {!selectedApplication.enabled ? (
                    <div className="management-notice management-notice--validation">
                      <strong>{t("management.runtime.applicationDisabledTitle")}</strong>
                      <p>{t("management.runtime.applicationDisabledDetail")}</p>
                    </div>
                  ) : null}
                  {!versionOptions.length ? (
                    <div className="management-notice management-notice--validation">
                      <strong>{t("management.runtime.releaseRequiredTitle")}</strong>
                      <p>{t("management.runtime.releaseRequiredDetail")}</p>
                    </div>
                  ) : null}
                  {!selectedDeployment && mutationProblem ? renderProblem(mutationProblem) : null}
                  {!selectedDeployment && successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}
                  <label>
                    <span>{t("management.runtime.environment")}</span>
                    <select disabled={readOnly || isMutating} onChange={(event) => setDeployEnvironment(event.target.value)} required value={deployEnvironment}>
                      {availableEnvironments.map((environment) => <option key={environment.slug} value={environment.slug}>{environment.name}</option>)}
                    </select>
                  </label>
                  <label>
                    <span>{t("management.runtime.version")}</span>
                    <select disabled={readOnly || isMutating || !versionOptions.length} onChange={(event) => setDeployVersion(event.target.value)} required value={deployVersion}>
                      {versionOptions.map((version) => <option key={version.id} value={version.version}>{version.version}</option>)}
                    </select>
                  </label>
                  <label className="management-detail-form__wide">
                    <span>{t("management.runtime.configuration")}</span>
                    <textarea disabled={readOnly || isMutating} onChange={(event) => setDeployConfigurationText(event.target.value)} rows={7} value={deployConfigurationText} />
                  </label>
                  <label className="management-detail-form__wide">
                    <span>{t("management.runtime.secretRefs")}</span>
                    <textarea disabled={readOnly || isMutating} onChange={(event) => setDeploySecretRefsText(event.target.value)} rows={6} value={deploySecretRefsText} />
                  </label>
                  <label className="management-detail-form__wide">
                    <span>{t("management.runtime.scaling")}</span>
                    <textarea disabled={readOnly || isMutating} onChange={(event) => setDeployScalingText(event.target.value)} rows={6} value={deployScalingText} />
                  </label>
                  <p className="management-detail-form__help">{t("management.runtime.deployHelp")}</p>
                  <div className="management-detail-form__actions">
                    <button disabled={readOnly || isMutating || !selectedApplication.enabled || !versionOptions.length || !deployEnvironment} type="submit">
                      {isMutating ? t("management.runtime.submitting") : t("management.runtime.deploy")}
                    </button>
                  </div>
                </form>
              ) : null}
            </div>
          </div>
        ) : null}

        {readOnly ? (
          <div className="management-notice management-notice--authorization">
            <strong>{t("management.readOnlyTitle")}</strong>
            <p>{t("management.readOnlyDetail")}</p>
          </div>
        ) : null}
      </div>
    </article>
  );
}
