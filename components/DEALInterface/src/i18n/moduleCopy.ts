import type { DealModule, ModuleKey } from "../types";
import type { MessageKey, MessageParams } from "./messages";

type Translate = (key: MessageKey, params?: MessageParams) => string;

interface ModuleCopyKeys {
  summary: MessageKey;
  endpointLabel: MessageKey;
  capabilities: MessageKey[];
  integrations: MessageKey[];
}

const moduleCopyKeys: Record<ModuleKey, ModuleCopyKeys> = {
  dealhost: {
    summary: "moduleCopy.dealhost.summary",
    endpointLabel: "moduleCopy.dealhost.endpoint",
    capabilities: [
      "moduleCopy.dealhost.capabilityApplicationCatalog",
      "moduleCopy.dealhost.capabilityReleaseMetadata",
      "moduleCopy.dealhost.capabilityApisixRoutes",
      "moduleCopy.dealhost.capabilityHealthProbes",
    ],
    integrations: [
      "moduleCopy.dealhost.integrationApisix",
      "moduleCopy.dealhost.integrationValkey",
      "moduleCopy.dealhost.integrationNats",
      "moduleCopy.dealhost.integrationDjango",
    ],
  },
  dealiot: {
    summary: "moduleCopy.dealiot.summary",
    endpointLabel: "moduleCopy.dealiot.endpoint",
    capabilities: [
      "moduleCopy.dealiot.capabilityDeviceRegistry",
      "moduleCopy.dealiot.capabilityTelemetry",
      "moduleCopy.dealiot.capabilityRulesEngine",
      "moduleCopy.dealiot.capabilityEdgeUpdates",
    ],
    integrations: [
      "moduleCopy.dealiot.integrationMqtt",
      "moduleCopy.dealiot.integrationNats",
      "moduleCopy.dealiot.integrationEdgeAgents",
      "moduleCopy.dealiot.integrationAlerting",
    ],
  },
  dealdata: {
    summary: "moduleCopy.dealdata.summary",
    endpointLabel: "moduleCopy.dealdata.endpoint",
    capabilities: [
      "moduleCopy.dealdata.capabilityPipelines",
      "moduleCopy.dealdata.capabilityCatalog",
      "moduleCopy.dealdata.capabilityLineage",
      "moduleCopy.dealdata.capabilityAccessPolicies",
    ],
    integrations: [
      "moduleCopy.dealdata.integrationObjectStorage",
      "moduleCopy.dealdata.integrationWarehouse",
      "moduleCopy.dealdata.integrationIam",
      "moduleCopy.dealdata.integrationAuditLogs",
    ],
  },
};

export function localizeModules(modules: DealModule[], t: Translate): DealModule[] {
  return modules.map((module) => {
    const copy = moduleCopyKeys[module.key];

    return {
      ...module,
      summary: t(copy.summary),
      endpointLabel: t(copy.endpointLabel),
      capabilities: copy.capabilities.map((key) => t(key)),
      integrations: copy.integrations.map((key) => t(key)),
    };
  });
}
