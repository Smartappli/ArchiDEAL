export type ModuleKey = "dealhost" | "dealiot" | "dealdata";

export type ModuleHealth = "online" | "degraded" | "attention" | "protected";

export type ActionPriority = "critical" | "high" | "normal";

export type ActionState = "open" | "in_progress" | "blocked" | "scheduled";

export type ProbeStatus = "online" | "degraded" | "attention" | "protected";

export interface DealModule {
  key: ModuleKey;
  name: string;
  shortName: string;
  summary: string;
  owner: string;
  status: ModuleHealth;
  accent: string;
  endpointLabel: string;
  capabilities: string[];
  metrics: Array<{
    label: string;
    value: string;
    trend: string;
  }>;
  integrations: string[];
}

export interface DashboardMetric {
  label: string;
  value: string;
  detail: string;
}

export interface ActivityItem {
  module: string;
  title: string;
  detail: string;
  time: string;
  severity: ModuleHealth;
}

export interface OperatorAction {
  id: string;
  moduleKey: ModuleKey;
  title: string;
  detail: string;
  owner: string;
  due: string;
  priority: ActionPriority;
  state: ActionState;
}

export interface ModuleWorkflow {
  id: string;
  title: string;
  description: string;
  cadence: string;
  automation: string;
  requiredRoles: string[];
}

export interface ModuleControlProfile {
  moduleKey: ModuleKey;
  environment: string;
  releaseWindow: string;
  slaTarget: string;
  escalation: string;
  workflows: ModuleWorkflow[];
}

export interface ModuleProbeResult {
  id: string;
  label: string;
  url: string;
  status: ProbeStatus;
  httpStatus?: number;
  responseTimeMs?: number;
  detail: string;
  summary?: Record<string, number>;
  checkedAt: string;
}

export interface ModuleConnection {
  moduleKey: ModuleKey;
  status: ProbeStatus;
  checkedAt: string;
  probes: ModuleProbeResult[];
}
