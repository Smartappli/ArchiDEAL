const state = {
  architecture: null,
  healthById: new Map(),
  activePlane: "all",
};

const publicBasePath = "/dealiot";

async function fetchJson(endpointName, options = {}) {
  const { headers = {}, ...requestOptions } = options;
  const init = {
    ...requestOptions,
    headers: { Accept: "application/json", ...headers },
  };
  let response;
  switch (endpointName) {
    case "architecture":
      response = await fetch(`${publicBasePath}/api/architecture`, init);
      break;
    case "health":
      response = await fetch(`${publicBasePath}/api/health`, init);
      break;
    case "zenodoExport":
      response = await fetch(`${publicBasePath}/api/datasets/zenodo/export`, init);
      break;
    case "openaireExport":
      response = await fetch(`${publicBasePath}/api/datasets/openaire/export`, init);
      break;
    default:
      throw new Error("Endpoint API non autorise");
  }
  if (!response.ok) {
    throw new Error(`${endpointName} returned ${response.status}`);
  }
  return response.json();
}

function query(selector) {
  const node = document.querySelector(selector);
  if (!node) {
    throw new Error(`Missing element: ${selector}`);
  }
  return node;
}

function text(value) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function textList(values) {
  return Array.isArray(values) ? values.map(text).join(", ") : text(values);
}

function cssToken(value) {
  return String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .slice(0, 80);
}

function appendChildren(parent, children) {
  const childList = Array.isArray(children) ? children : [children];
  childList.forEach((child) => {
    if (child === null || child === undefined) {
      return;
    }
    if (child instanceof Node) {
      parent.appendChild(child);
      return;
    }
    parent.appendChild(document.createTextNode(text(child)));
  });
}

function dataAttributeName(name) {
  switch (name) {
    case "action":
      return "data-action";
    case "datasetId":
      return "data-dataset-id";
    default:
      return null;
  }
}

function element(tagName, options = {}, children = []) {
  const node = document.createElement(tagName);
  if (options.className) {
    node.className = options.className;
  }
  if (options.textContent !== undefined) {
    node.textContent = text(options.textContent);
  }
  Object.entries(options.attrs || {}).forEach(([name, value]) => {
    if (value !== null && value !== undefined) {
      node.setAttribute(name, String(value));
    }
  });
  Object.entries(options.dataset || {}).forEach(([name, value]) => {
    const attributeName = dataAttributeName(name);
    if (attributeName && value !== null && value !== undefined) {
      node.setAttribute(attributeName, String(value));
    }
  });
  appendChildren(node, children);
  return node;
}

function replaceChildren(selector, children) {
  query(selector).replaceChildren(...(Array.isArray(children) ? children : [children]));
}

function strong(value) {
  return element("strong", { textContent: value });
}

function small(value) {
  return element("small", { textContent: value });
}

function pill(label, className = "") {
  const token = cssToken(className);
  return element("span", {
    className: token ? `pill ${token}` : "pill",
    textContent: label,
  });
}

function meta(children) {
  return element("div", { className: "meta" }, children);
}

function footer(children) {
  return element("footer", {}, children);
}

function td(children) {
  return element("td", {}, children);
}

function tr(cells) {
  return element("tr", {}, cells.map((cell) => td(cell)));
}

function actionButton(label, action, datasetId = "") {
  return element("button", {
    textContent: label,
    attrs: { type: "button" },
    dataset: { action, datasetId },
  });
}

function safeHttpUrl(value) {
  if (!value) {
    return null;
  }
  try {
    const parsed = new URL(String(value), window.location.origin);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
  } catch {
    return null;
  }
  return null;
}

function externalLink(value) {
  const href = safeHttpUrl(value);
  if (!href) {
    return null;
  }
  return element(
    "a",
    {
      className: "link-button",
      attrs: { href, target: "_blank", rel: "noreferrer noopener" },
    },
    "Ouvrir",
  );
}

function renderMetrics() {
  const components = state.architecture?.components || [];
  const summary = [...state.healthById.values()].reduce((acc, item) => {
    const status = text(item.status);
    acc.set(status, (acc.get(status) || 0) + 1);
    return acc;
  }, new Map());

  query("#metric-services").textContent = components.length;
  query("#metric-healthy").textContent = summary.get("healthy") || 0;
  query("#metric-unreachable").textContent = summary.get("unreachable") || 0;
  query("#metric-topics").textContent = state.architecture?.topics.length || 0;
}

function renderPlaneFilter() {
  const select = query("#plane-filter");
  const planes = [...new Set(state.architecture.components.map((item) => item.plane))].sort();
  const options = [
    element("option", { textContent: "Tous les plans", attrs: { value: "all" } }),
    ...planes.map((plane) => element("option", { textContent: plane, attrs: { value: plane } })),
  ];
  select.replaceChildren(...options);
  select.value = state.activePlane;
}

function renderComponents() {
  const components = state.architecture.components.filter(
    (item) => state.activePlane === "all" || item.plane === state.activePlane,
  );

  replaceChildren(
    "#component-grid",
    components.map((component) => {
      const health = state.healthById.get(component.id) || {
        status: "unknown",
        detail: "not checked",
      };
      return element("article", { className: "component" }, [
        element("h3", { textContent: component.name }),
        element("p", { textContent: component.role }),
        meta([
          pill(component.plane),
          pill(health.status, health.status),
          pill(`risk ${component.risk}`, component.risk),
        ]),
        small(component.data_scope),
        footer([externalLink(component.ui)]),
      ]);
    }),
  );
}

function renderTopics() {
  replaceChildren(
    "#topic-table",
    state.architecture.topics.map((topic) =>
      tr([
        [strong(topic.name)],
        topic.plane,
        topic.classification,
        topic.retention,
      ]),
    ),
  );
}

function renderDatasets() {
  replaceChildren(
    "#dataset-table",
    (state.architecture.datasets || []).map((dataset) =>
      tr([
        [strong(dataset.title), small(dataset.dataset_id)],
        dataset.dataset_type,
        dataset.classification,
        dataset.access_mode,
        dataset.dmp_id,
        [actionButton("Draft", "zenodo-export", dataset.dataset_id)],
        [actionButton("Metadata", "openaire-export", dataset.dataset_id)],
      ]),
    ),
  );

  replaceChildren(
    "#zenodo-export-policy",
    (state.architecture.zenodo_export_policy || []).map((control) =>
      pill(control.id, control.status),
    ),
  );
  replaceChildren(
    "#openaire-export-policy",
    (state.architecture.openaire_export_policy || []).map((control) =>
      pill(control.id, control.status),
    ),
  );
  replaceChildren(
    "#dmp-table",
    (state.architecture.data_management_plans || []).map((dmp) =>
      tr([
        [strong(dmp.dmp_id), small(dmp.owner)],
        dmp.project_id,
        [pill(dmp.status, dmp.status)],
        dmp.access_policy,
        dmp.retention_policy,
      ]),
    ),
  );
  replaceChildren(
    "#dmp-control-list",
    (state.architecture.dmp_controls || []).map((control) =>
      element("article", { className: "control" }, [
        element("h3", { textContent: control.id }),
        element("p", { textContent: control.control }),
        meta([pill(control.status, control.status), pill(control.evidence)]),
      ]),
    ),
  );
}

function renderIntermediation() {
  replaceChildren(
    "#intermediation-flow",
    state.architecture.intermediation_flow.map((step) =>
      element("article", { className: "item" }, [
        element("h3", { textContent: `${step.step}. ${text(step.name)}` }),
        element("p", { textContent: step.control }),
        meta([pill(step.source)]),
      ]),
    ),
  );
  replaceChildren(
    "#consumer-profile-table",
    state.architecture.consumer_profiles.map((profile) =>
      tr([
        [strong(profile.name), small(profile.profile_id)],
        profile.consumer_type,
        textList(profile.default_access),
        profile.raw_access,
      ]),
    ),
  );
}

function renderDataAct() {
  replaceChildren(
    "#data-act-journey",
    (state.architecture.data_act_user_journey || []).map((step) =>
      element("article", { className: "item" }, [
        element("h3", { textContent: `${step.step}. ${text(step.name)}` }),
        element("p", { textContent: step.control }),
        meta([pill(step.evidence)]),
      ]),
    ),
  );
  replaceChildren(
    "#data-act-product-table",
    (state.architecture.data_act_connected_products || []).map((product) =>
      tr([
        [strong(product.connected_product), small(product.product_id)],
        textList(product.generated_data),
        product.default_access,
        product.third_party_sharing,
      ]),
    ),
  );
  replaceChildren(
    "#data-act-channel-table",
    (state.architecture.data_act_access_channels || []).map((channel) =>
      tr([
        [strong(channel.name), small(channel.channel_id)],
        channel.consumer,
        channel.delivery,
        textList(channel.evidence_topics),
      ]),
    ),
  );
  replaceChildren(
    "#data-act-obligation-list",
    (state.architecture.data_act_obligations || []).map((obligation) =>
      element("article", { className: "control" }, [
        element("h3", { textContent: obligation.article }),
        element("p", { textContent: obligation.control }),
        meta([pill(obligation.status, obligation.status)]),
      ]),
    ),
  );
}

function renderResearch() {
  const context = state.architecture.research_context;
  replaceChildren(
    "#research-context",
    context
      ? [
          element("article", { className: "item" }, [
            element("h3", { textContent: context.primary_purpose }),
            element("p", { textContent: context.dga_mode }),
            meta((context.general_interest_objectives || []).map((objective) => pill(objective))),
          ]),
        ]
      : [],
  );
  replaceChildren(
    "#research-project-list",
    state.architecture.research_projects.map((project) =>
      element("article", { className: "component" }, [
        element("h3", { textContent: project.title }),
        element("p", { textContent: project.objective }),
        meta([
          pill(project.permission_model),
          pill(project.ethics_review_status, project.ethics_review_status),
        ]),
        small(project.sharing_layer),
      ]),
    ),
  );
  replaceChildren(
    "#research-control-list",
    state.architecture.research_controls.map((control) =>
      element("article", { className: "control" }, [
        element("h3", { textContent: control.id }),
        element("p", { textContent: control.control }),
        meta([pill(control.status, control.status)]),
      ]),
    ),
  );
}

function renderDga() {
  replaceChildren(
    "#dga-principles",
    (state.architecture.dga_obligations || [])
      .filter((item) => item.status === "implemented")
      .map((item) => pill(item.article, item.status)),
  );
  replaceChildren(
    "#data-product-table",
    state.architecture.data_products.map((product) =>
      tr([
        [strong(product.title), small(product.product_id)],
        product.data_category,
        product.access_mode,
        product.dga_gate,
      ]),
    ),
  );
  replaceChildren(
    "#dga-obligation-list",
    state.architecture.dga_obligations.map((obligation) =>
      element("article", { className: "control" }, [
        element("h3", { textContent: obligation.article }),
        element("p", { textContent: obligation.control }),
        meta([pill(obligation.status, obligation.status)]),
      ]),
    ),
  );
}

function renderSecurityResilience() {
  replaceChildren(
    "#security-scope-list",
    [
      "NIS2: secteur, taille et transposition nationale a confirmer",
      "DORA: applicable si perimetre financier ou fournisseur ICT finance",
      "CRA: applicable aux produits avec elements numeriques mis sur le marche UE",
    ].map((item) => pill(item)),
  );
  replaceChildren(
    "#security-gate-list",
    (state.architecture.security_resilience_gates || []).map((gate) =>
      element("article", { className: "item" }, [
        element("h3", { textContent: gate.gate }),
        element("p", { textContent: gate.control }),
        meta([pill(gate.status, gate.status), pill(gate.evidence)]),
      ]),
    ),
  );
  replaceChildren(
    "#security-control-table",
    (state.architecture.security_resilience_controls || []).map((control) =>
      tr([
        [strong(control.id), small(control.control)],
        control.regulation,
        control.domain,
        [control.evidence_topic, element("small", {}, [pill(control.status, control.status)])],
      ]),
    ),
  );
  replaceChildren(
    "#security-topic-table",
    (state.architecture.topics || [])
      .filter(
        (topic) =>
          topic.name.startsWith("security.") ||
          topic.name.startsWith("resilience.") ||
          topic.name.startsWith("compliance.") ||
          topic.name.startsWith("cra."),
      )
      .map((topic) => tr([[strong(topic.name)], topic.plane, topic.classification, topic.retention])),
  );
}

function renderOperations() {
  replaceChildren(
    "#operations-list",
    state.architecture.operations.map((operation) =>
      element("article", { className: "item" }, [
        element("h3", { textContent: operation.name }),
        element("p", { textContent: operation.description }),
        meta([pill(operation.method), pill(operation.scope)]),
        footer([
          operation.id === "refresh-health" ? actionButton("Executer", "refresh") : null,
        ]),
      ]),
    ),
  );
}

function renderRunbooks() {
  replaceChildren(
    "#runbook-list",
    state.architecture.runbooks.map((runbook) =>
      element("article", { className: "item" }, [
        element("h3", { textContent: runbook.name }),
        element("p", { textContent: runbook.scope }),
        meta([pill(runbook.path)]),
      ]),
    ),
  );
}

function renderCompliance() {
  replaceChildren(
    "#legal-finalization-table",
    (state.architecture.legal_finalization_items || []).map((item) =>
      tr([
        [strong(item.id)],
        [pill(item.status, item.status)],
        item.owner,
        item.decision,
        item.evidence,
      ]),
    ),
  );
  replaceChildren(
    "#legal-dossier-table",
    (state.architecture.legal_compliance_dossier || []).map((item) =>
      tr([
        [strong(item.id), small(item.artifact)],
        item.regulation,
        [pill(item.status, item.status)],
        item.evidence_topic,
        item.required_before,
      ]),
    ),
  );
  replaceChildren(
    "#legal-release-gate-list",
    (state.architecture.legal_release_gates || []).map((gate) =>
      element("article", { className: "control" }, [
        element("h3", { textContent: gate.id }),
        element("p", { textContent: gate.before }),
        small(gate.required_artifacts),
        meta([pill(gate.status, gate.status)]),
        footer([gate.block_rule]),
      ]),
    ),
  );
  replaceChildren(
    "#legal-template-table",
    (state.architecture.legal_templates || []).map((template) =>
      tr([
        [strong(template.id)],
        template.regulation,
        template.purpose,
        template.path,
      ]),
    ),
  );
  replaceChildren(
    "#compliance-readiness-table",
    (state.architecture.compliance_readiness || []).map((item) =>
      tr([
        [strong(item.regulation), small(item.technical_status)],
        [pill(item.readiness, item.readiness)],
        item.blocking_gap,
        item.next_action,
      ]),
    ),
  );
  replaceChildren(
    "#compliance-scope-table",
    (state.architecture.compliance_scope_decisions || []).map((item) =>
      tr([
        [strong(item.regulation), small(item.basis)],
        [pill(item.scope_status, item.scope_status)],
        item.owner,
        item.evidence_topic,
      ]),
    ),
  );
  replaceChildren(
    "#compliance-reporting-table",
    (state.architecture.compliance_reporting_channels || []).map((item) =>
      tr([
        [strong(item.regulation)],
        item.trigger,
        [pill(item.channel_status, item.channel_status)],
        item.evidence_topic,
      ]),
    ),
  );
  replaceChildren(
    "#additional-legislation-table",
    (state.architecture.additional_legislation || []).map((item) =>
      tr([
        [strong(item.regulation), small(item.evidence_topic)],
        [pill(item.applicability, item.applicability)],
        item.reason,
        item.architecture_action,
      ]),
    ),
  );
  replaceChildren(
    "#compliance-list",
    state.architecture.compliance_controls.map((control) =>
      element("article", { className: "control" }, [
        element("h3", { textContent: control.regulation }),
        element("p", { textContent: control.control }),
        meta([pill(control.status, control.status)]),
      ]),
    ),
  );
}

function renderAll() {
  renderMetrics();
  renderPlaneFilter();
  renderComponents();
  renderTopics();
  renderDatasets();
  renderIntermediation();
  renderDataAct();
  renderResearch();
  renderDga();
  renderSecurityResilience();
  renderOperations();
  renderRunbooks();
  renderCompliance();
}

async function refreshHealth() {
  const health = await fetchJson("health");
  state.healthById = new Map(health.checks.map((item) => [item.id, item]));
  renderMetrics();
  renderComponents();
}

async function exportDatasetToZenodo(datasetId) {
  const result = query("#zenodo-export-result");
  try {
    result.textContent = "Export Zenodo en cours...";
    const payload = await fetchJson("zenodoExport", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    result.textContent = `Draft Zenodo cree pour ${text(payload.dataset_id)}: ${text(
      payload.record_url,
    )}`;
  } catch (error) {
    result.textContent = error instanceof Error ? error.message : "Export Zenodo impossible";
  }
}

async function exportDatasetToOpenAire(datasetId) {
  const result = query("#openaire-export-result");
  try {
    result.textContent = "Export OpenAIRE en cours...";
    const payload = await fetchJson("openaireExport", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    result.textContent = `Package OpenAIRE cree pour ${text(payload.dataset_id)}: ${textList(
      payload.files,
    )}`;
  } catch (error) {
    result.textContent = error instanceof Error ? error.message : "Export OpenAIRE impossible";
  }
}

async function init() {
  state.architecture = await fetchJson("architecture");
  renderAll();
  await refreshHealth();
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target.closest("button") : null;
  if (!target) {
    return;
  }
  const action = target.dataset.action;
  if (target.matches("#refresh-health") || action === "refresh") {
    refreshHealth().catch((error) => console.error(error));
  }
  if (action === "zenodo-export") {
    void exportDatasetToZenodo(target.dataset.datasetId);
  }
  if (action === "openaire-export") {
    void exportDatasetToOpenAire(target.dataset.datasetId);
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (target instanceof HTMLSelectElement && target.matches("#plane-filter")) {
    state.activePlane = target.value;
    renderComponents();
  }
});

init().catch((error) => {
  document.body.replaceChildren(
    element("main", { className: "fatal" }, [
      element("h1", { textContent: "Console indisponible" }),
      element("p", { textContent: error.message }),
    ]),
  );
});
