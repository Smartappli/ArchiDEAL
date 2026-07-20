import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import type {
  HostedApplication,
  RuntimeDeployment,
  RuntimeEnvironment,
  RuntimeOperation,
} from "../lib/managementApi";
import { ManagementApiError } from "../lib/managementApi";
import { RuntimeDeploymentPanel } from "./RuntimeDeploymentPanel";

const api = vi.hoisted(() => ({
  createRuntimeDeployment: vi.fn(),
  createRuntimeIdempotencyKey: vi.fn(() => "runtime-command-001"),
  getRuntimeOperation: vi.fn(),
  listManagementResources: vi.fn(),
  listRuntimeDeployments: vi.fn(),
  listRuntimeEnvironments: vi.fn(),
  listRuntimeOperations: vi.fn(),
  requestRuntimeDeploymentAction: vi.fn(),
  requestRuntimeLogSnapshot: vi.fn(),
  undeployRuntimeDeployment: vi.fn(),
  updateRuntimeDeploymentConfiguration: vi.fn(),
}));

vi.mock("../lib/managementApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/managementApi")>()),
  ...api,
}));

const application: HostedApplication = {
  id: 4,
  name: "Field portal",
  slug: "field-portal",
  description: "Portal",
  current_version: "1.5.0",
  released_at: "2026-07-20T08:00:00Z",
  enabled: true,
  revision: 3,
  modules: [{ id: 9, name: "API", slug: "api" }],
  versions: [{
    id: 12,
    version: "1.5.0",
    notes: "Runtime release",
    source: "ci",
    created_at: "2026-07-20T08:00:00Z",
  }],
};

const environment: RuntimeEnvironment = {
  slug: "production",
  name: "Production",
  description: "Production Kubernetes cluster",
  orchestrator: "kubernetes",
  enabled: true,
  capabilities: {
    start_stop: true,
    restart: true,
    scaling: {
      fixed: { min_replicas: 1, max_replicas: 20 },
      autoscaling: { enabled: true, min_replicas: 2, max_replicas: 20 },
    },
    logs: { max_lines: 1000, max_bytes: 262144 },
    domains: false,
  },
  policy: {
    requires_image_digest: true,
    allowed_registries: ["ghcr.io/smartappli"],
    stateless_only: true,
  },
};

const deployment: RuntimeDeployment = {
  id: "3a8c6658-2976-45c1-b666-f72e79c23fc4",
  application: { id: application.id, name: application.name, slug: application.slug },
  environment: environment.slug,
  version: "1.5.0",
  desired_state: "running",
  observed_state: "running",
  revision: 5,
  configuration: { api: { FEATURE_FLAG: "true" } },
  secret_refs: { api: { DATABASE_URL: "database-url" } },
  scaling: { api: { mode: "fixed", replicas: 2 } },
  components: [{
    module_id: 9,
    slug: "api",
    image_digest: "ghcr.io/smartappli/api@sha256:abc",
    desired_replicas: 2,
    ready_replicas: 2,
    available_replicas: 2,
    state: "running",
    health: "healthy",
    restart_count: 0,
    last_error: null,
  }],
  last_error: null,
  last_reconciled_at: "2026-07-20T08:03:00Z",
  created_at: "2026-07-20T08:01:00Z",
  updated_at: "2026-07-20T08:03:00Z",
};

function operation(type: RuntimeOperation["type"], result: RuntimeOperation["result"] = {}): RuntimeOperation {
  return {
    id: `operation-${type}`,
    deployment_id: deployment.id,
    type,
    status: "succeeded",
    requested_at: "2026-07-20T08:04:00Z",
    started_at: "2026-07-20T08:04:01Z",
    finished_at: "2026-07-20T08:04:02Z",
    progress: { stage: "complete", percent: 100 },
    result,
    error: null,
  };
}

function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results };
}

function renderPanel() {
  return render(
    <I18nProvider>
      <RuntimeDeploymentPanel
        areaDescription="Manage Kubernetes runtimes"
        areaTitle="Runtime deployments"
        moduleName="DEALHost"
      />
    </I18nProvider>,
  );
}

beforeEach(() => {
  for (const mock of Object.values(api)) mock.mockReset();
  api.createRuntimeIdempotencyKey.mockReturnValue("runtime-command-001");
  api.listManagementResources.mockResolvedValue([application]);
  api.listRuntimeEnvironments.mockResolvedValue(page([environment]));
  api.listRuntimeDeployments.mockResolvedValue(page([]));
  api.listRuntimeOperations.mockResolvedValue(page([]));
  vi.restoreAllMocks();
});

it("creates an environment-specific deployment pinned to an immutable version", async () => {
  const deployed = { ...deployment, observed_state: "pending" as const };
  api.createRuntimeDeployment.mockResolvedValue({
    deployment: deployed,
    operation: operation("deploy"),
  });
  renderPanel();

  expect(await screen.findByText("No active runtime deployment")).toBeInTheDocument();
  const deployHeading = screen.getByRole("heading", { name: "Deploy this application" });
  const deployForm = deployHeading.closest("form");
  expect(deployForm).not.toBeNull();
  const form = within(deployForm as HTMLFormElement);
  fireEvent.change(form.getByLabelText("Non-secret environment variables by component (JSON)"), {
    target: { value: JSON.stringify({ api: { FEATURE_FLAG: "true" } }) },
  });
  await userEvent.click(form.getByRole("button", { name: "Deploy runtime" }));

  await waitFor(() => expect(api.createRuntimeDeployment).toHaveBeenCalledWith(
    application,
    {
      environment: "production",
      version: "1.5.0",
      scaling: { api: { mode: "fixed", replicas: 1 } },
      configuration: { api: { FEATURE_FLAG: "true" } },
      secret_refs: {},
    },
    "runtime-command-001",
  ));
  expect(screen.getByText("The runtime operation completed successfully.")).toBeInTheDocument();
});

it("reuses the same idempotency key when a timed-out deployment is retried", async () => {
  const user = userEvent.setup();
  api.createRuntimeIdempotencyKey
    .mockReturnValueOnce("runtime-command-first")
    .mockReturnValueOnce("runtime-command-second");
  api.createRuntimeDeployment
    .mockRejectedValueOnce(new ManagementApiError({
      kind: "network",
      message: "The request timed out.",
      retryable: true,
    }))
    .mockResolvedValueOnce({ deployment, operation: operation("deploy") });
  renderPanel();

  const deployButton = await screen.findByRole("button", { name: "Deploy runtime" });
  await user.click(deployButton);
  expect(await screen.findByText("The request timed out.")).toBeInTheDocument();
  await user.click(deployButton);

  await waitFor(() => expect(api.createRuntimeDeployment).toHaveBeenCalledTimes(2));
  expect(api.createRuntimeDeployment.mock.calls.map((call) => call[2])).toEqual([
    "runtime-command-first",
    "runtime-command-first",
  ]);
  expect(api.createRuntimeIdempotencyKey).toHaveBeenCalledTimes(1);
});

it("exposes lifecycle actions, component scaling configuration and bounded logs", async () => {
  const user = userEvent.setup();
  api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
  api.listRuntimeOperations.mockResolvedValue(page([operation("deploy")]));
  api.requestRuntimeDeploymentAction.mockImplementation(async (_deployment, payload) => ({
    deployment: payload.action === "stop"
      ? { ...deployment, desired_state: "stopped", observed_state: "stopped", revision: 6 }
      : deployment,
    operation: operation(payload.action),
  }));
  api.updateRuntimeDeploymentConfiguration.mockResolvedValue({
    deployment: {
      ...deployment,
      revision: 6,
      configuration: { api: { FEATURE_FLAG: "false" } },
      scaling: { api: { mode: "fixed", replicas: 3 } },
    },
    operation: operation("configure"),
  });
  const logOperation = operation("log_snapshot", {
    component: "api",
    container: "api",
    content: "ready\n<script>not executable</script>",
    truncated: false,
    line_count: 2,
    captured_at: "2026-07-20T08:05:00Z",
    expires_at: "2026-07-20T08:10:00Z",
  });
  api.requestRuntimeLogSnapshot.mockResolvedValue(logOperation);
  renderPanel();

  expect(await screen.findByRole("heading", { name: "Runtime deployment" })).toBeInTheDocument();
  expect(screen.getAllByText("2 / 2")).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "Stop" }));
  await waitFor(() => expect(api.requestRuntimeDeploymentAction).toHaveBeenCalledWith(
    deployment,
    { action: "stop" },
    "runtime-command-001",
  ));

  const configurationHeading = screen.getByRole("heading", { name: "Runtime configuration and scaling" });
  const configurationForm = configurationHeading.closest("form");
  expect(configurationForm).not.toBeNull();
  const configurationQueries = within(configurationForm as HTMLFormElement);
  fireEvent.change(configurationQueries.getByLabelText("Non-secret environment variables by component (JSON)"), {
    target: { value: JSON.stringify({ api: { FEATURE_FLAG: "false" } }) },
  });
  fireEvent.change(configurationQueries.getByLabelText("Scaling policy by component (JSON)"), {
    target: { value: JSON.stringify({ api: { mode: "fixed", replicas: 3 } }) },
  });
  await user.click(configurationQueries.getByRole("button", { name: "Apply configuration and scaling" }));
  await waitFor(() => expect(api.updateRuntimeDeploymentConfiguration).toHaveBeenCalledWith(
    expect.objectContaining({ id: deployment.id, revision: 6 }),
    {
      configuration: { api: { FEATURE_FLAG: "false" } },
      secret_refs: deployment.secret_refs,
      scaling: { api: { mode: "fixed", replicas: 3 } },
    },
    "runtime-command-001",
  ));

  await user.click(screen.getByRole("button", { name: "Request log snapshot" }));
  await waitFor(() => expect(api.requestRuntimeLogSnapshot).toHaveBeenCalledWith(
    expect.objectContaining({ id: deployment.id }),
    { component: "api", tail_lines: 200, since_seconds: 3600 },
    "runtime-command-001",
  ));
  expect(screen.getByText(/not executable/)).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
});

it("refuses malformed component configuration without issuing a mutation", async () => {
  api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
  renderPanel();

  const configurationHeading = await screen.findByRole("heading", { name: "Runtime configuration and scaling" });
  const configurationForm = configurationHeading.closest("form");
  const form = within(configurationForm as HTMLFormElement);
  fireEvent.change(form.getByLabelText("Non-secret environment variables by component (JSON)"), {
    target: { value: JSON.stringify({ api: { DATABASE_PASSWORD: { value: "unsafe" } } }) },
  });
  await userEvent.click(form.getByRole("button", { name: "Apply configuration and scaling" }));

  expect(await screen.findByText(/must be valid component-keyed JSON objects/i)).toBeInTheDocument();
  expect(api.updateRuntimeDeploymentConfiguration).not.toHaveBeenCalled();
});

it("confirms asynchronous undeployment and uses the selected runtime revision", async () => {
  api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
  api.undeployRuntimeDeployment.mockResolvedValue({
    deployment: { ...deployment, desired_state: "absent", observed_state: "deleting", revision: 6 },
    operation: operation("undeploy"),
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPanel();

  await userEvent.click(await screen.findByRole("button", { name: "Undeploy runtime" }));
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Field portal"));
  await waitFor(() => expect(api.undeployRuntimeDeployment).toHaveBeenCalledWith(
    deployment,
    "runtime-command-001",
  ));
});

it("resumes a queued operation from history and retries a transient polling failure", async () => {
  const queuedOperation: RuntimeOperation = {
    ...operation("deploy"),
    status: "queued",
    started_at: null,
    finished_at: null,
    progress: { stage: "queued", percent: null },
    result: null,
  };
  const completedOperation: RuntimeOperation = {
    ...queuedOperation,
    status: "succeeded",
    started_at: "2026-07-20T08:04:01Z",
    finished_at: "2026-07-20T08:04:02Z",
    progress: { stage: "complete", percent: 100 },
    result: {},
  };
  api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
  api.listRuntimeOperations
    .mockResolvedValueOnce(page([queuedOperation]))
    .mockResolvedValue(page([completedOperation]));
  api.getRuntimeOperation
    .mockRejectedValueOnce(new ManagementApiError({
      kind: "network",
      message: "The operation status is temporarily unavailable.",
      retryable: true,
    }))
    .mockResolvedValueOnce(completedOperation);
  renderPanel();

  expect((await screen.findAllByText("Queued")).length).toBeGreaterThanOrEqual(1);
  expect(await screen.findByText("The operation status is temporarily unavailable.", {}, {
    timeout: 2_500,
  })).toBeInTheDocument();
  await waitFor(() => expect(api.getRuntimeOperation).toHaveBeenCalledTimes(2), {
    timeout: 6_000,
  });
  expect(await screen.findByText("The runtime operation completed successfully.")).toBeInTheDocument();
}, 8_000);

it.each([
  ["stopped", true, false, false],
  ["failed", true, true, false],
  ["unknown", true, true, false],
  ["running", false, true, true],
  ["degraded", false, true, true],
] as const)(
  "matches backend lifecycle transitions from %s",
  async (observedState, startEnabled, stopEnabled, restartEnabled) => {
    api.listRuntimeDeployments.mockResolvedValue(page([{
      ...deployment,
      observed_state: observedState,
    }]));
    renderPanel();

    await screen.findByRole("heading", { name: "Runtime deployment" });
    expect(screen.getByRole("button", { name: "Start" })).toHaveProperty("disabled", !startEnabled);
    expect(screen.getByRole("button", { name: "Stop" })).toHaveProperty("disabled", !stopEnabled);
    expect(screen.getByRole("button", { name: "Restart" })).toHaveProperty("disabled", !restartEnabled);
  },
);

it("shows operation-history errors and retries every runtime data source", async () => {
  api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
  api.listRuntimeOperations
    .mockRejectedValueOnce(new ManagementApiError({
      kind: "network",
      message: "Operation history is unavailable.",
      retryable: true,
    }))
    .mockResolvedValue(page([]));
  renderPanel();

  expect(await screen.findByText("Operation history is unavailable.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));

  await waitFor(() => {
    expect(api.listManagementResources).toHaveBeenCalledTimes(2);
    expect(api.listRuntimeEnvironments).toHaveBeenCalledTimes(2);
    expect(api.listRuntimeDeployments).toHaveBeenCalledTimes(2);
    expect(api.listRuntimeOperations).toHaveBeenCalledTimes(2);
  });
  expect(screen.queryByText("Operation history is unavailable.")).not.toBeInTheDocument();
});

it.each([
  [100, 100],
  [5_000, 1_000],
] as const)(
  "limits log requests to the lower of the environment cap %i and the API cap",
  async (environmentLimit, expectedLimit) => {
    api.listRuntimeEnvironments.mockResolvedValue(page([{
      ...environment,
      capabilities: {
        ...environment.capabilities,
        logs: { ...environment.capabilities.logs, max_lines: environmentLimit },
      },
    }]));
    api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
    renderPanel();

    await screen.findByRole("heading", { name: "Runtime logs" });
    const tailLines = screen.getByLabelText("Maximum lines");
    const sinceSeconds = screen.getByLabelText("Look-back period (seconds)");
    expect(tailLines).toHaveAttribute("max", String(expectedLimit));
    expect(sinceSeconds).toHaveAttribute("max", "604800");
    if (environmentLimit < 200) {
      await waitFor(() => expect(tailLines).toHaveValue(expectedLimit));
    }
  },
);

it("rejects a log look-back period outside the backend contract", async () => {
  api.listRuntimeDeployments.mockResolvedValue(page([deployment]));
  renderPanel();

  await screen.findByRole("heading", { name: "Runtime logs" });
  const sinceSeconds = screen.getByLabelText("Look-back period (seconds)");
  fireEvent.change(sinceSeconds, { target: { value: "604801" } });
  fireEvent.submit(sinceSeconds.closest("form") as HTMLFormElement);

  expect(await screen.findByText(/Log requests require 1 to 1,000 lines/)).toBeInTheDocument();
  expect(api.requestRuntimeLogSnapshot).not.toHaveBeenCalled();
});
