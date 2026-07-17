from __future__ import annotations

from typing import Any

COMPONENTS: list[dict[str, Any]] = [
    {
        "id": "vernemq",
        "name": "VerneMQ",
        "service": "vernemq1",
        "plane": "ingestion",
        "role": "MQTT broker cluster for device telemetry and WildFi gateways.",
        "probe": "tcp://vernemq1:1883",
        "ui": None,
        "depends_on": [],
        "data_scope": "device identifiers, telemetry, GPS and media metadata topics.",
        "risk": "high",
    },
    {
        "id": "mqtt-kafka-bridge",
        "name": "MQTT to Kafka bridge",
        "service": "mqtt-kafka-bridge",
        "plane": "ingestion",
        "role": "Validates and routes MQTT payloads to raw Kafka topics or DLQ.",
        "probe": None,
        "ui": None,
        "depends_on": ["vernemq", "kafka"],
        "data_scope": "raw payloads, device identifiers, MQTT topics and timestamps.",
        "risk": "high",
    },
    {
        "id": "kafka",
        "name": "Kafka KRaft cluster",
        "service": "kafka1",
        "plane": "backbone",
        "role": "Event backbone for raw, derived, state and platform topics.",
        "probe": "tcp://kafka1:9092",
        "ui": None,
        "depends_on": [],
        "data_scope": "all platform event streams.",
        "risk": "high",
    },
    {
        "id": "kafka-connect",
        "name": "Kafka Connect",
        "service": "kafka-connect",
        "plane": "backbone",
        "role": "Runs Debezium and integration connectors.",
        "probe": "http://kafka-connect:8083/connectors",
        "ui": None,
        "depends_on": ["kafka", "timescaledb"],
        "data_scope": "database change events and connector offsets.",
        "risk": "medium",
    },
    {
        "id": "apicurio",
        "name": "Apicurio Registry",
        "service": "apicurio-registry",
        "plane": "backbone",
        "role": "Schema registry and event contract governance.",
        "probe": "http://apicurio-registry:9000/health/ready",
        "ui": "http://localhost:8888",
        "depends_on": ["kafka"],
        "data_scope": "schema metadata and registry events.",
        "risk": "medium",
    },
    {
        "id": "seaweedfs",
        "name": "SeaweedFS S3",
        "service": "seaweedfs-s3",
        "plane": "storage",
        "role": "S3-compatible object storage for raw media and processing state.",
        "probe": "http://seaweedfs-s3:8333/",
        "ui": "http://localhost:8889",
        "depends_on": ["seaweedfs-filer"],
        "data_scope": "media objects, Flink checkpoints and savepoints.",
        "risk": "high",
    },
    {
        "id": "timescaledb",
        "name": "TimescaleDB HA",
        "service": "haproxy",
        "plane": "storage",
        "role": "HA PostgreSQL/TimescaleDB entrypoint through HAProxy.",
        "probe": "tcp://haproxy:5432",
        "ui": "http://localhost:5050",
        "depends_on": ["etcd"],
        "data_scope": "application database records and derived state.",
        "risk": "high",
    },
    {
        "id": "flink",
        "name": "Flink",
        "service": "flink-jobmanager",
        "plane": "processing",
        "role": "Stateful stream processing and latest-state projection.",
        "probe": "http://flink-jobmanager:8081/overview",
        "ui": "http://localhost:8081",
        "depends_on": ["kafka", "seaweedfs"],
        "data_scope": "raw events, features, state and checkpoint data.",
        "risk": "high",
    },
    {
        "id": "beam",
        "name": "Beam job server",
        "service": "beam-jobserver",
        "plane": "processing",
        "role": "Portable batch/stream pipeline execution endpoint.",
        "probe": "tcp://beam-jobserver:8099",
        "ui": None,
        "depends_on": ["flink"],
        "data_scope": "pipeline artifacts and runtime data depending on submitted jobs.",
        "risk": "medium",
    },
    {
        "id": "airflow",
        "name": "Airflow",
        "service": "airflow-apiserver",
        "plane": "orchestration",
        "role": "Schedules backfills and operational workflows.",
        "probe": "http://airflow-apiserver:8080/api/v2/version",
        "ui": "http://localhost:8088",
        "depends_on": ["airflow-postgres", "airflow-redis", "kafka", "seaweedfs"],
        "data_scope": "DAG metadata, task logs, replay windows and object references.",
        "risk": "medium",
    },
    {
        "id": "prometheus",
        "name": "Prometheus",
        "service": "prometheus",
        "plane": "observability",
        "role": "Metrics collection, retention and alert evaluation.",
        "probe": "http://prometheus:9090/-/ready",
        "ui": "http://localhost:9090",
        "depends_on": [],
        "data_scope": "operational metrics and service labels.",
        "risk": "medium",
    },
    {
        "id": "grafana",
        "name": "Grafana",
        "service": "grafana",
        "plane": "observability",
        "role": "Operational dashboards for streaming, storage, database and alerts.",
        "probe": "http://grafana:3000/api/health",
        "ui": "http://localhost:3000",
        "depends_on": ["prometheus"],
        "data_scope": "dashboards, users and metrics queries.",
        "risk": "medium",
    },
    {
        "id": "data-governance",
        "name": "DGA intermediation gateway",
        "service": "management-console",
        "plane": "governance",
        "role": "Mediates access between collected data, applications and researchers.",
        "probe": "http://management-console:8080/healthz",
        "ui": "http://localhost:8090",
        "depends_on": ["kafka", "apicurio", "flink"],
        "data_scope": (
            "data product catalogue, access decisions, permissions and activity evidence."
        ),
        "risk": "high",
    },
    {
        "id": "security-resilience",
        "name": "Security and resilience evidence plane",
        "service": "management-console",
        "plane": "governance",
        "role": "Tracks cyber risk, incidents, vulnerabilities, SBOMs and resilience evidence.",
        "probe": "http://management-console:8080/healthz",
        "ui": "http://localhost:8090",
        "depends_on": ["kafka", "apicurio", "prometheus", "grafana"],
        "data_scope": "security incidents, vulnerability findings, SBOMs and resilience tests.",
        "risk": "high",
    },
]

TOPICS: list[dict[str, str]] = [
    {
        "name": "raw.gps",
        "plane": "raw",
        "owner": "ingestion",
        "classification": "personal-location",
        "retention": "define before production",
    },
    {
        "name": "raw.sensor",
        "plane": "raw",
        "owner": "ingestion",
        "classification": "personal-or-device",
        "retention": "define before production",
    },
    {
        "name": "raw.image2d.meta",
        "plane": "raw",
        "owner": "media",
        "classification": "media-metadata",
        "retention": "define before production",
    },
    {
        "name": "raw.image3d.meta",
        "plane": "raw",
        "owner": "media",
        "classification": "media-metadata",
        "retention": "define before production",
    },
    {
        "name": "raw.video2d.meta",
        "plane": "raw",
        "owner": "media",
        "classification": "media-metadata",
        "retention": "define before production",
    },
    {
        "name": "raw.video3d.meta",
        "plane": "raw",
        "owner": "media",
        "classification": "media-metadata",
        "retention": "define before production",
    },
    {
        "name": "features.events",
        "plane": "derived",
        "owner": "processing",
        "classification": "derived",
        "retention": "define before production",
    },
    {
        "name": "state.latest",
        "plane": "state",
        "owner": "processing",
        "classification": "derived-current-state",
        "retention": "compacted plus delete tombstones",
    },
    {
        "name": "dlq.events",
        "plane": "platform",
        "owner": "platform",
        "classification": "raw-error-copy",
        "retention": "short retention required",
    },
    {
        "name": "governance.data.products",
        "plane": "governance",
        "owner": "data-governance",
        "classification": "metadata",
        "retention": "compacted catalogue",
    },
    {
        "name": "governance.access.requests",
        "plane": "governance",
        "owner": "data-governance",
        "classification": "access-decision-record",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "governance.permission.events",
        "plane": "governance",
        "owner": "data-governance",
        "classification": "consent-or-permission-record",
        "retention": "compacted with withdrawal evidence",
    },
    {
        "name": "governance.intermediation.log",
        "plane": "governance",
        "owner": "data-governance",
        "classification": "intermediation-activity-log",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "governance.transfer.notices",
        "plane": "governance",
        "owner": "data-governance",
        "classification": "incident-notice-record",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "governance.research.projects",
        "plane": "governance",
        "owner": "research-governance",
        "classification": "research-project-record",
        "retention": "compacted project register",
    },
    {
        "name": "governance.research.outputs",
        "plane": "governance",
        "owner": "research-governance",
        "classification": "research-output-record",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "governance.dataset.catalog",
        "plane": "governance",
        "owner": "data-stewardship",
        "classification": "dataset-catalog-record",
        "retention": "compacted dataset register",
    },
    {
        "name": "governance.data_management_plans",
        "plane": "governance",
        "owner": "research-governance",
        "classification": "data-management-plan-record",
        "retention": "compacted DMP register",
    },
    {
        "name": "governance.repository.exports",
        "plane": "governance",
        "owner": "research-governance",
        "classification": "repository-export-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "dataact.product.catalog",
        "plane": "governance",
        "owner": "data-act-governance",
        "classification": "connected-product-metadata",
        "retention": "compacted catalogue",
    },
    {
        "name": "dataact.user.access.requests",
        "plane": "governance",
        "owner": "data-act-governance",
        "classification": "user-access-request",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "dataact.third_party.sharing",
        "plane": "governance",
        "owner": "data-act-governance",
        "classification": "third-party-sharing-authorization",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "dataact.user.exports",
        "plane": "governance",
        "owner": "data-act-governance",
        "classification": "user-export-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "dataact.safeguards",
        "plane": "governance",
        "owner": "data-act-governance",
        "classification": "trade-secret-security-safeguard",
        "retention": "compacted control register",
    },
    {
        "name": "dataact.legal_basis.checks",
        "plane": "governance",
        "owner": "data-act-governance",
        "classification": "personal-data-release-check",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "security.asset.inventory",
        "plane": "security",
        "owner": "security",
        "classification": "asset-inventory",
        "retention": "compacted inventory",
    },
    {
        "name": "security.incident.events",
        "plane": "security",
        "owner": "security",
        "classification": "incident-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "security.vulnerability.findings",
        "plane": "security",
        "owner": "security",
        "classification": "vulnerability-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "security.sbom.attestations",
        "plane": "security",
        "owner": "security",
        "classification": "supply-chain-evidence",
        "retention": "compacted artifact register",
    },
    {
        "name": "security.patch.events",
        "plane": "security",
        "owner": "security",
        "classification": "security-update-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "resilience.backup.tests",
        "plane": "resilience",
        "owner": "platform",
        "classification": "continuity-test-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "resilience.operational.risk",
        "plane": "resilience",
        "owner": "platform-risk",
        "classification": "ict-risk-register",
        "retention": "compacted risk register",
    },
    {
        "name": "resilience.third_party.risk",
        "plane": "resilience",
        "owner": "platform-risk",
        "classification": "supplier-risk-register",
        "retention": "compacted supplier register",
    },
    {
        "name": "compliance.scope.decisions",
        "plane": "compliance",
        "owner": "compliance",
        "classification": "regulatory-scope-decision",
        "retention": "compacted scope register",
    },
    {
        "name": "compliance.control.assessments",
        "plane": "compliance",
        "owner": "compliance",
        "classification": "control-assessment-evidence",
        "retention": "one year minimum, site policy required",
    },
    {
        "name": "compliance.reporting.channels",
        "plane": "compliance",
        "owner": "compliance",
        "classification": "regulatory-reporting-channel",
        "retention": "compacted channel register",
    },
    {
        "name": "compliance.legal.dossier",
        "plane": "compliance",
        "owner": "legal-compliance",
        "classification": "legal-compliance-dossier",
        "retention": "compacted legal evidence register",
    },
    {
        "name": "cra.product.lifecycle",
        "plane": "security",
        "owner": "product-security",
        "classification": "product-support-lifecycle",
        "retention": "compacted product register",
    },
]

DATA_PRODUCTS: list[dict[str, Any]] = [
    {
        "product_id": "telemetry.raw.gps",
        "title": "Raw GPS telemetry",
        "data_category": "personal",
        "source_topics": ["raw.gps"],
        "allowed_purposes": [
            "scientific research",
            "livestock behaviour research",
            "agronomic research",
        ],
        "access_mode": "mediated",
        "format": "JSON",
        "interoperability_standard": "Apicurio JSON Schema",
        "dga_gate": "requires approved research project, permission and GPS minimisation",
    },
    {
        "product_id": "telemetry.raw.sensor",
        "title": "Raw sensor telemetry",
        "data_category": "mixed",
        "source_topics": ["raw.sensor"],
        "allowed_purposes": [
            "scientific research",
            "device reliability research",
            "environmental research",
        ],
        "access_mode": "mediated",
        "format": "JSON",
        "interoperability_standard": "Apicurio JSON Schema",
        "dga_gate": "requires approved research project and field minimisation",
    },
    {
        "product_id": "media.metadata",
        "title": "Media object metadata",
        "data_category": "mixed",
        "source_topics": [
            "raw.image2d.meta",
            "raw.image3d.meta",
            "raw.video2d.meta",
            "raw.video3d.meta",
        ],
        "allowed_purposes": ["scientific research", "computer vision research"],
        "access_mode": "restricted",
        "format": "JSON",
        "interoperability_standard": "Apicurio JSON Schema",
        "dga_gate": "requires ethics review and object-level access controls",
    },
    {
        "product_id": "features.latest-state",
        "title": "Derived features and latest state",
        "data_category": "mixed",
        "source_topics": ["features.events", "state.latest"],
        "allowed_purposes": ["scientific research", "aggregate analytics"],
        "access_mode": "mediated",
        "format": "JSON",
        "interoperability_standard": "DEALIoT normalized event contract",
        "dga_gate": "preferred research sharing layer over raw topics",
    },
]

DATASETS: list[dict[str, Any]] = [
    {
        "dataset_id": "dataset.telemetry.raw-gps-restricted",
        "title": "Restricted raw GPS telemetry dataset",
        "dataset_type": "raw",
        "classification": "personal",
        "data_products": ["telemetry.raw.gps"],
        "source_topics": ["raw.gps"],
        "access_mode": "restricted",
        "license_policy": "research agreement required",
        "retention_policy": "site policy required before production",
        "fair_status": "metadata template defined; persistent identifier pending",
        "dmp_id": "dmp.livestock-behaviour.template",
    },
    {
        "dataset_id": "dataset.telemetry.sensor-minimised",
        "title": "Minimised sensor telemetry research dataset",
        "dataset_type": "derived",
        "classification": "mixed",
        "data_products": ["telemetry.raw.sensor", "features.latest-state"],
        "source_topics": ["raw.sensor", "features.events"],
        "access_mode": "mediated",
        "license_policy": "research purpose and recipient terms required",
        "retention_policy": "project DMP retention schedule",
        "fair_status": "schema and provenance available; repository target pending",
        "dmp_id": "dmp.precision-agriculture.template",
    },
    {
        "dataset_id": "dataset.features.latest-state",
        "title": "Derived latest-state and feature dataset",
        "dataset_type": "aggregate",
        "classification": "mixed",
        "data_products": ["features.latest-state"],
        "source_topics": ["features.events", "state.latest"],
        "access_mode": "mediated",
        "license_policy": "Data Act or research access package required",
        "retention_policy": "short operational retention plus approved exports",
        "fair_status": "preferred publication layer for research and third-party access",
        "dmp_id": "dmp.platform-derived-data.template",
    },
]

DATA_MANAGEMENT_PLANS: list[dict[str, Any]] = [
    {
        "dmp_id": "dmp.livestock-behaviour.template",
        "project_id": "research.template.livestock-behaviour",
        "status": "draft",
        "owner": "research-governance",
        "datasets": ["dataset.telemetry.raw-gps-restricted"],
        "metadata_standard": "Apicurio JSON Schema plus project metadata",
        "legal_basis": "data holder permission or data subject consent where applicable",
        "access_policy": "raw GPS restricted; derived and pseudonymised access preferred",
        "retention_policy": "define before production release",
        "preservation_plan": "approved exports only; repository target pending",
        "security_controls": ["pseudonymisation", "least privilege", "publication review"],
    },
    {
        "dmp_id": "dmp.precision-agriculture.template",
        "project_id": "research.template.precision-agriculture",
        "status": "draft",
        "owner": "research-governance",
        "datasets": ["dataset.telemetry.sensor-minimised"],
        "metadata_standard": "Apicurio JSON Schema plus FAIR project metadata",
        "legal_basis": "data holder permission and research protocol",
        "access_policy": "mediated dataset package; no direct raw topic subscriptions",
        "retention_policy": "project DMP retention schedule",
        "preservation_plan": "curated derived dataset with disclosure review",
        "security_controls": ["field minimisation", "access logging", "supplier review"],
    },
    {
        "dmp_id": "dmp.platform-derived-data.template",
        "project_id": "platform.data-sharing",
        "status": "draft",
        "owner": "data-governance",
        "datasets": ["dataset.features.latest-state"],
        "metadata_standard": "DEALIoT normalized event contract",
        "legal_basis": "Data Act entitlement or approved research governance",
        "access_policy": "direct secure API, minimised export or DGA-mediated package",
        "retention_policy": "align with user request, project protocol and backup policy",
        "preservation_plan": "export evidence in dataact.user.exports",
        "security_controls": ["legal-basis check", "scope review", "export expiry"],
    },
]

DMP_CONTROLS: list[dict[str, str]] = [
    {
        "id": "dataset-catalog",
        "status": "implemented",
        "control": "Register every shareable dataset before access or publication.",
        "evidence": "governance.dataset.catalog",
    },
    {
        "id": "dmp-required",
        "status": "partial",
        "control": "Link every research dataset to a project Data Management Plan.",
        "evidence": "governance.data_management_plans",
    },
    {
        "id": "fair-metadata",
        "status": "partial",
        "control": "Record metadata standard, schema references, provenance and access policy.",
        "evidence": "governance.dataset.catalog",
    },
    {
        "id": "preservation-retention",
        "status": "todo",
        "control": "Define retention, preservation location and disposal schedule per dataset.",
        "evidence": "governance.data_management_plans",
    },
    {
        "id": "publication-reuse",
        "status": "partial",
        "control": "Review license, disclosure risk and reuse limits before publication.",
        "evidence": "governance.research.outputs",
    },
    {
        "id": "zenodo-export",
        "status": "partial",
        "control": "Create Zenodo drafts only after dataset catalogue and DMP checks.",
        "evidence": "governance.repository.exports",
    },
]

ZENODO_EXPORT_POLICY: list[dict[str, str]] = [
    {
        "id": "draft-first",
        "status": "implemented",
        "control": "Zenodo exports create a draft record by default; publication is opt-in.",
        "evidence": "governance.repository.exports",
    },
    {
        "id": "manifest-upload",
        "status": "implemented",
        "control": "Each export uploads a dataset/DMP manifest for reproducibility.",
        "evidence": "governance.repository.exports",
    },
    {
        "id": "staged-files-only",
        "status": "implemented",
        "control": "Dataset files can be uploaded only from ZENODO_EXPORT_STAGING_DIR.",
        "evidence": "governance.repository.exports",
    },
    {
        "id": "legal-publication-gate",
        "status": "implemented",
        "control": "Publication requires legal_review_approved=true.",
        "evidence": "compliance.control.assessments",
    },
    {
        "id": "non-public-open-release-block",
        "status": "implemented",
        "control": "Open release is blocked for internal, restricted or personal datasets.",
        "evidence": "dataact.legal_basis.checks",
    },
]

OPENAIRE_EXPORT_POLICY: list[dict[str, str]] = [
    {
        "id": "metadata-first",
        "status": "implemented",
        "control": "OpenAIRE export creates metadata packages, not raw dataset uploads.",
        "evidence": "governance.repository.exports",
    },
    {
        "id": "datacite-profile",
        "status": "implemented",
        "control": "Export uses DataCite XML aligned with OpenAIRE Data Archive guidelines.",
        "evidence": "governance.repository.exports",
    },
    {
        "id": "provide-registration",
        "status": "partial",
        "control": "OpenAIRE discovery requires a repository or OAI-PMH source in PROVIDE.",
        "evidence": "compliance.legal.dossier",
    },
    {
        "id": "classification-gate",
        "status": "implemented",
        "control": "Open access metadata is blocked for non-public datasets.",
        "evidence": "dataact.legal_basis.checks",
    },
    {
        "id": "legal-discovery-gate",
        "status": "partial",
        "control": "Discovery export requires catalogue, DMP and legal dossier approval.",
        "evidence": "compliance.legal.dossier",
    },
]

DATA_ACT_CONNECTED_PRODUCTS: list[dict[str, Any]] = [
    {
        "product_id": "connected-device.telemetry",
        "connected_product": "DEALIoT connected telemetry devices",
        "related_services": ["MQTT ingestion", "WildFi decoding", "media metadata ingestion"],
        "generated_data": ["raw.gps", "raw.sensor", "media object metadata"],
        "user_roles": ["device owner", "field operator", "research data holder"],
        "access_channels": ["dataact.direct-access", "dataact.research-mediated"],
        "default_access": "available through mediated access, not unrestricted raw topics",
        "third_party_sharing": "allowed only after user authorization and scope review",
        "contract_status": "terms and user notices required before production",
    },
    {
        "product_id": "related-service.analytics",
        "connected_product": "DEALIoT derived analytics service",
        "related_services": ["Flink feature projection", "latest-state API consumers"],
        "generated_data": ["features.events", "state.latest"],
        "user_roles": ["service customer", "research sponsor"],
        "access_channels": ["dataact.direct-access", "dataact.third-party-transfer"],
        "default_access": "preferred Data Act release layer for applications and researchers",
        "third_party_sharing": "supported through scoped application or research packages",
        "contract_status": "recipient terms and misuse restrictions required",
    },
]

DATA_ACT_ACCESS_CHANNELS: list[dict[str, Any]] = [
    {
        "channel_id": "dataact.direct-access",
        "name": "User direct access",
        "consumer": "user",
        "delivery": "secure API, controlled object access or minimised export",
        "default_policy": "grant access to generated data after identity and entitlement checks",
        "evidence_topics": [
            "dataact.user.access.requests",
            "dataact.legal_basis.checks",
            "dataact.user.exports",
            "governance.intermediation.log",
        ],
    },
    {
        "channel_id": "dataact.third-party-transfer",
        "name": "Third-party sharing by user request",
        "consumer": "third party selected by user",
        "delivery": "purpose-bound service account, signed export or controlled data package",
        "default_policy": "share only fields, time windows and purpose authorized by the user",
        "evidence_topics": [
            "dataact.third_party.sharing",
            "dataact.safeguards",
            "governance.transfer.notices",
        ],
    },
    {
        "channel_id": "dataact.research-mediated",
        "name": "Research access package",
        "consumer": "scientist or research organisation",
        "delivery": "DGA-mediated data product with Data Act user entitlement evidence",
        "default_policy": "prefer derived or pseudonymised datasets before raw generated data",
        "evidence_topics": [
            "governance.research.projects",
            "governance.access.requests",
            "dataact.user.access.requests",
            "dataact.legal_basis.checks",
        ],
    },
]

DATA_ACT_OBLIGATIONS: list[dict[str, str]] = [
    {
        "id": "user-access",
        "article": "Data Act Ch. II",
        "status": "partial",
        "control": (
            "Expose generated connected-product data to entitled users through clear channels."
        ),
    },
    {
        "id": "third-party-sharing",
        "article": "Data Act Ch. II",
        "status": "partial",
        "control": (
            "Enable user-authorized sharing to third parties with purpose and scope records."
        ),
    },
    {
        "id": "fair-contractual-terms",
        "article": "Data Act Ch. IV",
        "status": "todo",
        "control": "Review data-sharing terms for unfair clauses and transparent restrictions.",
    },
    {
        "id": "interoperability-export",
        "article": "Data Act Ch. VIII",
        "status": "implemented",
        "control": "Use JSON schemas, explicit formats and logged exports for portability.",
    },
    {
        "id": "trade-secret-safeguards",
        "article": "Data Act Ch. II",
        "status": "partial",
        "control": "Record proportionate safeguards before sharing sensitive generated data.",
    },
    {
        "id": "personal-data-legal-basis",
        "article": "Data Act and GDPR interface",
        "status": "partial",
        "control": (
            "Check GDPR legal basis before releasing personal data to users or third parties."
        ),
    },
    {
        "id": "no-dark-pattern-release",
        "article": "Data Act Ch. II",
        "status": "todo",
        "control": "Define SLA, UX copy and operational path so user access is not obstructed.",
    },
]

DATA_ACT_USER_JOURNEY: list[dict[str, str]] = [
    {
        "step": "1",
        "name": "Connected product inventory",
        "control": "Register product, related service, generated data and user role.",
        "evidence": "dataact.product.catalog",
    },
    {
        "step": "2",
        "name": "User request",
        "control": "Capture entitlement, requested scope, time range, purpose and recipient.",
        "evidence": "dataact.user.access.requests",
    },
    {
        "step": "3",
        "name": "Safeguard check",
        "control": "Apply security, privacy, trade-secret and misuse controls before release.",
        "evidence": "dataact.safeguards",
    },
    {
        "step": "4",
        "name": "Delivery or third-party share",
        "control": (
            "Deliver data in a transparent format or transfer it to the user-selected party."
        ),
        "evidence": "dataact.user.exports, dataact.third_party.sharing",
    },
    {
        "step": "5",
        "name": "Audit and withdrawal",
        "control": "Log access, stop sharing on withdrawal and retain evidence under policy.",
        "evidence": "governance.intermediation.log",
    },
]

INTERMEDIATION_FLOW: list[dict[str, Any]] = [
    {
        "step": 1,
        "name": "Collected data landing",
        "source": "MQTT, media object storage, Kafka raw topics",
        "control": "raw data is retained in restricted ingestion/storage zones",
    },
    {
        "step": 2,
        "name": "Data product registration",
        "source": "governance.data.products",
        "control": "purpose, format, category, source topics and sharing mode are declared",
    },
    {
        "step": 3,
        "name": "Access request and review",
        "source": "governance.access.requests",
        "control": "application or researcher requests are reviewed against purpose and policy",
    },
    {
        "step": 4,
        "name": "Permission and project checks",
        "source": "governance.permission.events, governance.research.projects",
        "control": "permission, consent, protocol and ethics status are verified",
    },
    {
        "step": 5,
        "name": "Mediated delivery",
        "source": "derived topics, minimised exports, controlled object access",
        "control": "raw access is exceptional; derived or pseudonymised datasets are preferred",
    },
    {
        "step": 6,
        "name": "Activity and output logging",
        "source": "governance.intermediation.log, governance.research.outputs",
        "control": "retrieval, sharing, conversion, withdrawal and publication review are logged",
    },
]

CONSUMER_PROFILES: list[dict[str, Any]] = [
    {
        "profile_id": "application.operational",
        "name": "Operational application",
        "consumer_type": "application",
        "default_access": ["features.latest-state"],
        "raw_access": "denied by default",
        "required_evidence": ["access request", "service purpose", "least privilege scope"],
    },
    {
        "profile_id": "application.analytics",
        "name": "Analytics or decision-support application",
        "consumer_type": "application",
        "default_access": ["features.latest-state", "telemetry.raw.sensor"],
        "raw_access": "exceptional and field-minimised",
        "required_evidence": ["access request", "data protection review", "retention scope"],
    },
    {
        "profile_id": "researcher.internal",
        "name": "Internal scientist",
        "consumer_type": "researcher",
        "default_access": ["features.latest-state", "telemetry.raw.sensor"],
        "raw_access": "requires protocol and ethics status",
        "required_evidence": ["research project", "permission model", "publication review"],
    },
    {
        "profile_id": "researcher.external",
        "name": "External researcher or research organisation",
        "consumer_type": "researcher",
        "default_access": ["features.latest-state"],
        "raw_access": "restricted and contract-bound",
        "required_evidence": [
            "research project",
            "data sharing agreement",
            "permission or consent",
            "third-country check if applicable",
        ],
    },
]

RESEARCH_CONTEXT: dict[str, Any] = {
    "primary_purpose": "scientific research",
    "dga_mode": "research collection with possible data altruism workflow",
    "general_interest_objectives": [
        "livestock welfare research",
        "precision agriculture research",
        "environmental monitoring research",
    ],
    "required_release_gates": [
        "documented research protocol",
        "approved Data Management Plan for each released dataset",
        "ethics review decision or documented exemption",
        "DPIA or risk assessment for GPS, media and linked identifiers",
        "data holder permission or data subject consent where applicable",
        "pseudonymisation before researcher access",
        "publication disclosure review before external release",
    ],
    "intermediation_position": (
        "applications and scientists consume data through mediated data products, not direct raw "
        "topic access"
    ),
}

RESEARCH_PROJECTS: list[dict[str, Any]] = [
    {
        "project_id": "research.template.livestock-behaviour",
        "title": "Livestock behaviour and welfare research",
        "objective": "Analyse telemetry and derived movement patterns for animal welfare research.",
        "data_products": ["telemetry.raw.gps", "telemetry.raw.sensor", "features.latest-state"],
        "permission_model": "data_holder_permission",
        "ethics_review_status": "pending",
        "sharing_layer": "derived data preferred; raw GPS restricted",
    },
    {
        "project_id": "research.template.precision-agriculture",
        "title": "Precision agriculture and environmental research",
        "objective": "Study environmental telemetry and field context for agronomic research.",
        "data_products": ["telemetry.raw.sensor", "features.latest-state"],
        "permission_model": "data_holder_permission",
        "ethics_review_status": "pending",
        "sharing_layer": "minimised sensor fields and aggregated outputs",
    },
]

RESEARCH_CONTROLS: list[dict[str, str]] = [
    {
        "id": "research-protocol",
        "status": "todo",
        "control": "Register each research protocol before data access.",
    },
    {
        "id": "ethics-review",
        "status": "todo",
        "control": "Record ethics approval, rejection or exemption for each project.",
    },
    {
        "id": "research-permission",
        "status": "partial",
        "control": "Link project access to data holder permission or data subject consent.",
    },
    {
        "id": "research-minimisation",
        "status": "partial",
        "control": "Prefer derived, pseudonymised and aggregated data over raw GPS/media.",
    },
    {
        "id": "publication-review",
        "status": "todo",
        "control": "Review outputs for re-identification risk before publication or sharing.",
    },
    {
        "id": "data-management-plan",
        "status": "partial",
        "control": "Maintain a DMP with FAIR metadata, access, retention and preservation rules.",
    },
]

DGA_OBLIGATIONS: list[dict[str, str]] = [
    {
        "id": "notification",
        "article": "DGA Art. 11",
        "status": "organisational",
        "control": (
            "Notify the competent authority if research sharing becomes data intermediation."
        ),
    },
    {
        "id": "neutrality",
        "article": "DGA Art. 12(a)-(b)",
        "status": "partial",
        "control": (
            "Keep intermediation logically separated and do not use mediated data for own purposes."
        ),
    },
    {
        "id": "activity-metadata-purpose",
        "article": "DGA Art. 12(c)",
        "status": "implemented",
        "control": (
            "Use intermediation activity metadata only to operate, secure and improve the service."
        ),
    },
    {
        "id": "format-interoperability",
        "article": "DGA Art. 12(d),(i)",
        "status": "implemented",
        "control": (
            "Publish data products through explicit JSON schemas and avoid conversion by default."
        ),
    },
    {
        "id": "fair-access",
        "article": "DGA Art. 12(f)",
        "status": "implemented",
        "control": "Track access requests, decisions and reasons in governance.access.requests.",
    },
    {
        "id": "dataset-catalog-dmp",
        "article": "DGA, FAIR research governance",
        "status": "partial",
        "control": "Link mediated datasets to catalogue records and Data Management Plans.",
    },
    {
        "id": "abuse-prevention",
        "article": "DGA Art. 12(g)",
        "status": "todo",
        "control": "Define sanctions, suspension and exclusion workflow for abusive data users.",
    },
    {
        "id": "continuity",
        "article": "DGA Art. 12(h)",
        "status": "partial",
        "control": "Back up governance topics and document retrieval/transfer procedures.",
    },
    {
        "id": "security",
        "article": "DGA Art. 12(j)-(l)",
        "status": "partial",
        "control": "Require mediated delivery, TLS/SASL/mTLS and least privilege scopes.",
    },
    {
        "id": "consent-permission",
        "article": "DGA Art. 12(n), Art. 21, Art. 25",
        "status": "partial",
        "control": "Provide tools to give and withdraw research consent or permission.",
    },
    {
        "id": "intermediation-log",
        "article": "DGA Art. 12(o)",
        "status": "implemented",
        "control": (
            "Reserve governance.intermediation.log as immutable evidence of sharing activity."
        ),
    },
]

SECURITY_RESILIENCE_CONTROLS: list[dict[str, str]] = [
    {
        "id": "asset-inventory",
        "regulation": "NIS2, DORA, CRA",
        "status": "implemented",
        "domain": "risk-management",
        "evidence_topic": "security.asset.inventory",
        "control": "Maintain critical assets, owners, dependencies and data classifications.",
    },
    {
        "id": "cyber-risk-register",
        "regulation": "NIS2, DORA",
        "status": "partial",
        "domain": "risk-management",
        "evidence_topic": "resilience.operational.risk",
        "control": "Track ICT risk scenarios, severity, owners, mitigations and review dates.",
    },
    {
        "id": "incident-reporting",
        "regulation": "NIS2, DORA, CRA",
        "status": "partial",
        "domain": "incident-management",
        "evidence_topic": "security.incident.events",
        "control": (
            "Log incidents with severity, affected assets, deadlines and reporting channels."
        ),
    },
    {
        "id": "vulnerability-handling",
        "regulation": "CRA, NIS2",
        "status": "partial",
        "domain": "secure-development",
        "evidence_topic": "security.vulnerability.findings",
        "control": (
            "Track vulnerabilities, CVEs, affected assets, due dates and remediation status."
        ),
    },
    {
        "id": "sbom-provenance",
        "regulation": "CRA, NIS2, DORA",
        "status": "implemented",
        "domain": "supply-chain",
        "evidence_topic": "security.sbom.attestations",
        "control": "Record SBOM, provenance, digest and signature evidence for released artifacts.",
    },
    {
        "id": "security-updates",
        "regulation": "CRA, NIS2, DORA",
        "status": "partial",
        "domain": "change-management",
        "evidence_topic": "security.patch.events",
        "control": "Track security updates, tests, deployment state, rollback plan and approver.",
    },
    {
        "id": "continuity-testing",
        "regulation": "NIS2, DORA",
        "status": "partial",
        "domain": "business-continuity",
        "evidence_topic": "resilience.backup.tests",
        "control": "Record restore tests, RPO/RTO results, evidence and next test due date.",
    },
    {
        "id": "third-party-ict-risk",
        "regulation": "NIS2, DORA, CRA",
        "status": "partial",
        "domain": "supplier-risk",
        "evidence_topic": "resilience.third_party.risk",
        "control": "Review suppliers, subcontracting, exit plans and security requirements.",
    },
    {
        "id": "dora-scope",
        "regulation": "DORA",
        "status": "conditional",
        "domain": "scope",
        "evidence_topic": "resilience.operational.risk",
        "control": (
            "Apply DORA controls when DEALIoT is used by a financial entity or ICT provider."
        ),
    },
    {
        "id": "scope-decisions",
        "regulation": "DGA, Data Act, NIS2, DORA, CRA",
        "status": "partial",
        "domain": "scope",
        "evidence_topic": "compliance.scope.decisions",
        "control": "Record in-scope, out-of-scope or conditional decisions with owner and basis.",
    },
    {
        "id": "control-assessments",
        "regulation": "DGA, Data Act, NIS2, DORA, CRA",
        "status": "partial",
        "domain": "assurance",
        "evidence_topic": "compliance.control.assessments",
        "control": "Assess each control with evidence, gap, next action and due date.",
    },
    {
        "id": "reporting-channels",
        "regulation": "DGA, NIS2, DORA, CRA",
        "status": "todo",
        "domain": "regulatory-reporting",
        "evidence_topic": "compliance.reporting.channels",
        "control": "Record competent authority, reporting trigger, deadline, template and owner.",
    },
    {
        "id": "cra-product-lifecycle",
        "regulation": "CRA",
        "status": "todo",
        "domain": "product-security",
        "evidence_topic": "cra.product.lifecycle",
        "control": "Record support period, update channel and vulnerability disclosure details.",
    },
]

NIS2_OBLIGATIONS: list[dict[str, str]] = [
    {
        "id": "risk-management",
        "status": "partial",
        "control": "Operate a documented cybersecurity risk-management baseline.",
        "evidence": "security.asset.inventory, resilience.operational.risk",
    },
    {
        "id": "incident-handling",
        "status": "partial",
        "control": "Classify, contain, recover and report significant cyber incidents.",
        "evidence": "security.incident.events",
    },
    {
        "id": "business-continuity",
        "status": "partial",
        "control": "Test backups, disaster recovery and crisis procedures.",
        "evidence": "resilience.backup.tests",
    },
    {
        "id": "supply-chain-security",
        "status": "partial",
        "control": "Assess provider and software supply-chain risks.",
        "evidence": "security.sbom.attestations, resilience.third_party.risk",
    },
    {
        "id": "secure-access",
        "status": "partial",
        "control": "Enforce TLS, least privilege, strong authentication and cryptography.",
        "evidence": "production dependency contract and security hardening runbook",
    },
]

DORA_OBLIGATIONS: list[dict[str, str]] = [
    {
        "id": "scope-assessment",
        "status": "conditional",
        "control": (
            "Confirm whether deployment supports a financial entity or critical ICT service."
        ),
        "evidence": "resilience.operational.risk",
    },
    {
        "id": "ict-risk-management",
        "status": "partial",
        "control": "Maintain ICT risks, controls, dependencies and residual-risk decisions.",
        "evidence": "resilience.operational.risk",
    },
    {
        "id": "ict-incident-reporting",
        "status": "partial",
        "control": "Classify major ICT incidents and retain reporting evidence.",
        "evidence": "security.incident.events",
    },
    {
        "id": "resilience-testing",
        "status": "partial",
        "control": "Perform restore, failover, vulnerability and operational resilience tests.",
        "evidence": "resilience.backup.tests, security.vulnerability.findings",
    },
    {
        "id": "ict-third-party-risk",
        "status": "partial",
        "control": "Track ICT providers, criticality, subcontracting and exit plans.",
        "evidence": "resilience.third_party.risk",
    },
]

CRA_OBLIGATIONS: list[dict[str, str]] = [
    {
        "id": "secure-by-design",
        "status": "partial",
        "control": "Document secure defaults, hardening, access control and security tests.",
        "evidence": "security.asset.inventory, security.vulnerability.findings",
    },
    {
        "id": "vulnerability-management",
        "status": "partial",
        "control": "Track and remediate vulnerabilities throughout the support period.",
        "evidence": "security.vulnerability.findings, security.patch.events",
    },
    {
        "id": "sbom-and-provenance",
        "status": "implemented",
        "control": "Record SBOM and provenance for product images and release artifacts.",
        "evidence": "security.sbom.attestations",
    },
    {
        "id": "security-updates",
        "status": "partial",
        "control": "Plan, test, deploy and roll back security updates.",
        "evidence": "security.patch.events",
    },
    {
        "id": "support-period",
        "status": "todo",
        "control": "Define product support period, update channel and security documentation.",
        "evidence": "cra.product.lifecycle",
    },
    {
        "id": "incident-notification",
        "status": "todo",
        "control": "Define external notification workflow for exploited vulnerabilities/incidents.",
        "evidence": "security.incident.events",
    },
]

SECURITY_RESILIENCE_GATES: list[dict[str, str]] = [
    {
        "gate": "asset-scope",
        "status": "partial",
        "evidence": "security.asset.inventory",
        "control": "All critical services, topics, buckets, secrets and providers have owners.",
    },
    {
        "gate": "release-supply-chain",
        "status": "partial",
        "evidence": "security.sbom.attestations",
        "control": "Every released image has SBOM, provenance and signature evidence.",
    },
    {
        "gate": "known-vulnerabilities",
        "status": "partial",
        "evidence": "security.vulnerability.findings",
        "control": "No unaccepted critical vulnerability remains open at release.",
    },
    {
        "gate": "incident-readiness",
        "status": "partial",
        "evidence": "security.incident.events",
        "control": "Incident classification and regulatory reporting channels are configured.",
    },
    {
        "gate": "recovery-proof",
        "status": "partial",
        "evidence": "resilience.backup.tests",
        "control": "Restore tests prove target RPO/RTO before production sharing.",
    },
]

COMPLIANCE_SCOPE_DECISIONS: list[dict[str, str]] = [
    {
        "regulation": "DGA",
        "scope_status": "conditional",
        "owner": "legal-compliance",
        "basis": "Triggered if DEALIoT offers regulated data intermediation or altruism services.",
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "Data Act",
        "scope_status": "conditional",
        "owner": "data-governance",
        "basis": "Triggered for connected-product or related-service generated data.",
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "NIS2",
        "scope_status": "pending",
        "owner": "security",
        "basis": "Depends on sector, size, Member State transposition and entity classification.",
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "DORA",
        "scope_status": "conditional",
        "owner": "platform-risk",
        "basis": "Triggered for financial entities or ICT third-party provider use cases.",
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "CRA",
        "scope_status": "conditional",
        "owner": "product-security",
        "basis": "Triggered when DEALIoT is made available as a product with digital elements.",
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "GDPR",
        "scope_status": "in_scope",
        "owner": "privacy",
        "basis": (
            "Device identifiers, GPS, timestamps, media metadata and research exports may "
            "identify a person or operator."
        ),
        "evidence_topic": "dataact.legal_basis.checks",
    },
    {
        "regulation": "ePrivacy",
        "scope_status": "conditional",
        "owner": "privacy",
        "basis": (
            "Triggered by terminal-equipment access, electronic communications metadata or "
            "tracking rules under Member State law."
        ),
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "AI Act",
        "scope_status": "conditional",
        "owner": "ai-governance",
        "basis": "Triggered when AI systems or GPAI components are deployed by DEALIoT.",
        "evidence_topic": "compliance.control.assessments",
    },
    {
        "regulation": "Trade Secrets Directive",
        "scope_status": "conditional",
        "owner": "data-governance",
        "basis": "Triggered when shared generated data includes protected know-how.",
        "evidence_topic": "dataact.safeguards",
    },
    {
        "regulation": "Radio Equipment Directive",
        "scope_status": "conditional",
        "owner": "product-compliance",
        "basis": "Triggered if DEALIoT gateways or devices are placed on the EU market.",
        "evidence_topic": "cra.product.lifecycle",
    },
    {
        "regulation": "General Product Safety Regulation",
        "scope_status": "conditional",
        "owner": "product-compliance",
        "basis": "Triggered if connected products are consumer products made available in the EU.",
        "evidence_topic": "cra.product.lifecycle",
    },
    {
        "regulation": "Product Liability Directive",
        "scope_status": "conditional",
        "owner": "product-compliance",
        "basis": "Relevant for defective connected products, software or security updates.",
        "evidence_topic": "cra.product.lifecycle",
    },
    {
        "regulation": "Open Data Directive",
        "scope_status": "conditional",
        "owner": "data-governance",
        "basis": "Triggered only for public-sector or publicly funded research-data reuse.",
        "evidence_topic": "governance.dataset.catalog",
    },
    {
        "regulation": "EHDS",
        "scope_status": "conditional",
        "owner": "data-governance",
        "basis": "Triggered only if datasets include personal electronic health data.",
        "evidence_topic": "governance.dataset.catalog",
    },
]

COMPLIANCE_REPORTING_CHANNELS: list[dict[str, str]] = [
    {
        "regulation": "DGA",
        "trigger": "data intermediation notification or unauthorised data use notice",
        "channel_status": "todo",
        "evidence_topic": "compliance.reporting.channels",
        "control": "Record competent authority, template, owner and notification evidence.",
    },
    {
        "regulation": "NIS2",
        "trigger": "significant cyber incident",
        "channel_status": "todo",
        "evidence_topic": "compliance.reporting.channels",
        "control": "Configure CSIRT/competent authority contact path and reporting deadline.",
    },
    {
        "regulation": "DORA",
        "trigger": "major ICT-related incident or financial-sector customer requirement",
        "channel_status": "conditional",
        "evidence_topic": "compliance.reporting.channels",
        "control": "Configure financial supervisory reporting when DORA scope is confirmed.",
    },
    {
        "regulation": "CRA",
        "trigger": "actively exploited vulnerability or severe product-security incident",
        "channel_status": "todo",
        "evidence_topic": "compliance.reporting.channels",
        "control": "Configure CSIRT/ENISA reporting path for in-scope product releases.",
    },
    {
        "regulation": "GDPR",
        "trigger": "personal-data breach or data-subject rights workflow",
        "channel_status": "todo",
        "evidence_topic": "compliance.reporting.channels",
        "control": "Configure supervisory authority and data-subject communication paths.",
    },
]

COMPLIANCE_READINESS: list[dict[str, str]] = [
    {
        "regulation": "DGA",
        "readiness": "partial",
        "technical_status": "evidence plane implemented",
        "blocking_gap": "legal role decision, notification evidence and operating procedures.",
        "next_action": "Record DGA scope decision and competent authority channel.",
    },
    {
        "regulation": "Data Act",
        "readiness": "partial",
        "technical_status": "connected-product access and sharing evidence implemented",
        "blocking_gap": "production access workflow, notices, terms and personal-data legal basis.",
        "next_action": "Record legal-basis checks and test user/third-party release workflow.",
    },
    {
        "regulation": "NIS2",
        "readiness": "partial",
        "technical_status": "risk, incident, vulnerability and continuity topics implemented",
        "blocking_gap": "entity classification and national reporting channel not recorded.",
        "next_action": "Record NIS2 scope decision and incident reporting contact path.",
    },
    {
        "regulation": "DORA",
        "readiness": "conditional",
        "technical_status": "ICT-risk, resilience and third-party evidence implemented",
        "blocking_gap": "DORA scope depends on financial-sector use or ICT provider role.",
        "next_action": "Record financial-sector scope decision before claiming applicability.",
    },
    {
        "regulation": "CRA",
        "readiness": "partial",
        "technical_status": "SBOM, vulnerability and patch evidence implemented",
        "blocking_gap": "product lifecycle, support period and reporting channel not operational.",
        "next_action": "Record CRA product lifecycle and vulnerability disclosure channel.",
    },
    {
        "regulation": "GDPR",
        "readiness": "partial",
        "technical_status": "inventory, legal-basis and dataset/DMP evidence implemented",
        "blocking_gap": "DPIA, retention enforcement, rights handling and processor terms.",
        "next_action": "Record DPIA outcome and retention schedule before production research use.",
    },
    {
        "regulation": "ePrivacy",
        "readiness": "conditional",
        "technical_status": "scope decision and consent/notice evidence can be recorded",
        "blocking_gap": "terminal access and national ePrivacy implementation not assessed.",
        "next_action": "Classify terminal access and telemetry metadata collection per country.",
    },
    {
        "regulation": "AI Act",
        "readiness": "conditional",
        "technical_status": "AI governance placeholder exists",
        "blocking_gap": "no AI-system inventory, risk class or model lifecycle evidence.",
        "next_action": "Create AI-system inventory before deploying models or decision support.",
    },
]

LEGAL_COMPLIANCE_DOSSIER: list[dict[str, str]] = [
    {
        "id": "ropa-register",
        "regulation": "GDPR",
        "owner": "privacy",
        "status": "todo",
        "artifact": "Record of processing activities for telemetry, research and sharing.",
        "control": "Record controller, processor, purposes, categories, recipients and transfers.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "production-go-live",
    },
    {
        "id": "dpia-aipd",
        "regulation": "GDPR",
        "owner": "privacy",
        "status": "todo",
        "artifact": "DPIA/AIPD decision and assessment file for high-risk research processing.",
        "control": "Decide whether a DPIA is required and record mitigations before collection.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "production-go-live",
    },
    {
        "id": "privacy-notices",
        "regulation": "GDPR, ePrivacy, Data Act",
        "owner": "privacy",
        "status": "todo",
        "artifact": "Privacy and device notices for telemetry collection and research reuse.",
        "control": "Publish notice text covering purposes, rights, retention and recipients.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "data-collection",
    },
    {
        "id": "data-subject-rights",
        "regulation": "GDPR",
        "owner": "privacy",
        "status": "todo",
        "artifact": (
            "Procedure for access, erasure, objection, restriction and portability requests."
        ),
        "control": "Route requests to owners and record fulfilment or refusal evidence.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "production-go-live",
    },
    {
        "id": "processor-dpa",
        "regulation": "GDPR",
        "owner": "legal-compliance",
        "status": "todo",
        "artifact": "Processor, joint-controller and sub-processor contract pack.",
        "control": "Bind hosting, research partners and processors to written terms.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "third-party-sharing",
    },
    {
        "id": "data-act-user-notice",
        "regulation": "Data Act",
        "owner": "data-act-governance",
        "status": "todo",
        "artifact": "Pre-contractual user notice and access terms for generated data.",
        "control": "Explain data generated, access method, format, frequency and holder identity.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "connected-product-release",
    },
    {
        "id": "data-sharing-agreement",
        "regulation": "DGA, Data Act, GDPR, Trade Secrets Directive",
        "owner": "legal-compliance",
        "status": "todo",
        "artifact": "Data sharing agreement and third-party recipient checklist.",
        "control": "Bind purpose, categories, safeguards, confidentiality and onward-use limits.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "third-party-sharing",
    },
    {
        "id": "dga-role-notification",
        "regulation": "DGA",
        "owner": "legal-compliance",
        "status": "todo",
        "artifact": "DGA role decision and notification evidence if intermediation is regulated.",
        "control": "Record service separation, neutrality, no own reuse and authority channel.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "mediated-data-service",
    },
    {
        "id": "nis2-entity-classification",
        "regulation": "NIS2",
        "owner": "security",
        "status": "todo",
        "artifact": "Entity classification and Member State transposition mapping.",
        "control": "Record essential/important/out-of-scope decision and national contact path.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "production-go-live",
    },
    {
        "id": "dora-scope-decision",
        "regulation": "DORA",
        "owner": "platform-risk",
        "status": "conditional",
        "artifact": "Financial-sector scope decision and ICT third-party provider role.",
        "control": "Record DORA in-scope or out-of-scope decision before financial use.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "financial-sector-use",
    },
    {
        "id": "cra-conformity-file",
        "regulation": "CRA",
        "owner": "product-security",
        "status": "todo",
        "artifact": "Product classification, conformity and support-period file.",
        "control": "Record product role, vulnerability handling and security update commitment.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "product-market-release",
    },
    {
        "id": "ai-system-inventory",
        "regulation": "AI Act",
        "owner": "ai-governance",
        "status": "conditional",
        "artifact": "AI system inventory, risk class and prohibited-use check.",
        "control": "Block AI deployment until purpose, datasets, oversight and monitoring exist.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "ai-deployment",
    },
    {
        "id": "eprivacy-terminal-assessment",
        "regulation": "ePrivacy",
        "owner": "privacy",
        "status": "conditional",
        "artifact": "Terminal equipment and communications metadata assessment.",
        "control": "Record country rules, notice/consent basis and telemetry minimisation.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "data-collection",
    },
    {
        "id": "retention-schedule",
        "regulation": "GDPR, Data Act, DGA",
        "owner": "data-stewardship",
        "status": "todo",
        "artifact": "Retention and deletion schedule for topics, buckets, backups and exports.",
        "control": "Bind each dataset and raw store to retention, deletion and archive rules.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "production-go-live",
    },
    {
        "id": "incident-notification-playbook",
        "regulation": "GDPR, NIS2, DORA, CRA",
        "owner": "security",
        "status": "todo",
        "artifact": "Regulatory incident notification playbook and table-top exercise record.",
        "control": "Record severity triggers, deadlines, templates and authority contacts.",
        "evidence_topic": "compliance.legal.dossier",
        "required_before": "production-go-live",
    },
    {
        "id": "zenodo-publication-approval",
        "regulation": "GDPR, DGA, Data Act, Open Data Directive",
        "owner": "research-governance",
        "status": "partial",
        "artifact": "Dataset publication approval bound to catalogue, DMP and Zenodo draft.",
        "control": "Block publication unless legal review approves access right and licence.",
        "evidence_topic": "governance.repository.exports",
        "required_before": "repository-publication",
    },
    {
        "id": "openaire-discovery-approval",
        "regulation": "GDPR, DGA, Data Act, Open Data Directive",
        "owner": "research-governance",
        "status": "partial",
        "artifact": "OpenAIRE discovery approval bound to catalogue, DMP and metadata rights.",
        "control": "Block external discovery metadata until access rights and legal gates match.",
        "evidence_topic": "governance.repository.exports",
        "required_before": "external-catalog-discovery",
    },
]

LEGAL_RELEASE_GATES: list[dict[str, str]] = [
    {
        "id": "production-go-live",
        "status": "blocked",
        "before": "Production telemetry collection or external data access.",
        "required_artifacts": (
            "ropa-register, dpia-aipd, privacy-notices, data-subject-rights, "
            "retention-schedule, incident-notification-playbook"
        ),
        "block_rule": "No production go-live until mandatory legal dossier items are approved.",
    },
    {
        "id": "dataset-sharing",
        "status": "blocked",
        "before": "Any dataset release to applications, scientists or third parties.",
        "required_artifacts": (
            "dataset catalogue, active DMP, legal-basis check, sharing agreement, "
            "retention schedule"
        ),
        "block_rule": "No sharing without purpose, recipients, safeguards and access policy.",
    },
    {
        "id": "zenodo-publication",
        "status": "blocked",
        "before": "Zenodo publication action.",
        "required_artifacts": (
            "zenodo-publication-approval, DMP, disclosure review, licence and access-right decision"
        ),
        "block_rule": "Only draft creation is allowed until legal_review_approved is true.",
    },
    {
        "id": "external-catalog-discovery",
        "status": "blocked",
        "before": "OpenAIRE or external catalogue discovery exposure.",
        "required_artifacts": (
            "openaire-discovery-approval, dataset catalogue, DMP, landing page and "
            "metadata rights decision"
        ),
        "block_rule": "No public discovery metadata until access right matches classification.",
    },
    {
        "id": "third-party-sharing",
        "status": "blocked",
        "before": "Data Act third-party transfer or DGA-mediated external release.",
        "required_artifacts": "processor-dpa, data-sharing-agreement, data-act-user-notice",
        "block_rule": "No external recipient access without signed terms and user authority.",
    },
    {
        "id": "ai-deployment",
        "status": "conditional",
        "before": "AI model or decision-support deployment.",
        "required_artifacts": "ai-system-inventory, DPIA decision and dataset lineage.",
        "block_rule": "No AI system without inventory, risk class and human oversight record.",
    },
    {
        "id": "product-market-release",
        "status": "blocked",
        "before": "Software, gateway image or device made available on the EU market.",
        "required_artifacts": "cra-conformity-file, SBOM, support period and disclosure channel.",
        "block_rule": "No market release until product role and CRA obligations are recorded.",
    },
    {
        "id": "incident-reporting",
        "status": "blocked",
        "before": "Operational incident management in production.",
        "required_artifacts": "incident-notification-playbook and reporting channels.",
        "block_rule": "No production run without authority contacts, deadlines and templates.",
    },
]

LEGAL_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "ropa-template",
        "regulation": "GDPR",
        "path": "docs/compliance/templates/ropa-template.md",
        "purpose": "Record processing activities for telemetry, research and releases.",
    },
    {
        "id": "dpia-template",
        "regulation": "GDPR",
        "path": "docs/compliance/templates/dpia-template.md",
        "purpose": "DPIA/AIPD decision, risk assessment and mitigations.",
    },
    {
        "id": "privacy-notice-template",
        "regulation": "GDPR, ePrivacy",
        "path": "docs/compliance/templates/privacy-notice-template.md",
        "purpose": "Notice for telemetry collection and research reuse.",
    },
    {
        "id": "data-act-notice-template",
        "regulation": "Data Act",
        "path": "docs/compliance/templates/data-act-notice-template.md",
        "purpose": "User information for generated connected-product data access.",
    },
    {
        "id": "data-sharing-agreement-checklist",
        "regulation": "DGA, Data Act, GDPR",
        "path": "docs/compliance/templates/data-sharing-agreement-checklist.md",
        "purpose": "Recipient, purpose, safeguards and onward-use contract checklist.",
    },
    {
        "id": "processor-dpa-checklist",
        "regulation": "GDPR",
        "path": "docs/compliance/templates/processor-dpa-checklist.md",
        "purpose": "Processor, joint-controller and sub-processor contract review.",
    },
    {
        "id": "data-subject-rights-procedure",
        "regulation": "GDPR",
        "path": "docs/compliance/templates/data-subject-rights-procedure.md",
        "purpose": "Request intake, triage, deadline and fulfilment workflow.",
    },
    {
        "id": "dga-role-notification-template",
        "regulation": "DGA",
        "path": "docs/compliance/templates/dga-role-notification-template.md",
        "purpose": "DGA intermediation, altruism or internal-platform role decision.",
    },
    {
        "id": "scope-decision-template",
        "regulation": "DGA, Data Act, NIS2, DORA, CRA, AI Act, ePrivacy",
        "path": "docs/compliance/templates/scope-decision-template.md",
        "purpose": "In-scope, out-of-scope or conditional legal scope record.",
    },
    {
        "id": "reporting-channel-template",
        "regulation": "GDPR, DGA, NIS2, DORA, CRA",
        "path": "docs/compliance/templates/reporting-channel-template.md",
        "purpose": "Authority, trigger, deadline, template and notification owner.",
    },
    {
        "id": "cra-conformity-file-template",
        "regulation": "CRA",
        "path": "docs/compliance/templates/cra-conformity-file-template.md",
        "purpose": "Product classification, support period and vulnerability channel.",
    },
    {
        "id": "ai-system-inventory-template",
        "regulation": "AI Act",
        "path": "docs/compliance/templates/ai-system-inventory-template.md",
        "purpose": "AI system purpose, risk class, data lineage and oversight.",
    },
    {
        "id": "eprivacy-assessment-template",
        "regulation": "ePrivacy",
        "path": "docs/compliance/templates/eprivacy-assessment-template.md",
        "purpose": "Terminal access, communications metadata and national rules.",
    },
    {
        "id": "retention-schedule-template",
        "regulation": "GDPR, DGA, Data Act",
        "path": "docs/compliance/templates/retention-schedule-template.md",
        "purpose": "Retention, deletion and archive rules per data store and dataset.",
    },
    {
        "id": "incident-notification-playbook",
        "regulation": "GDPR, NIS2, DORA, CRA",
        "path": "docs/compliance/templates/incident-notification-playbook.md",
        "purpose": "Incident classification, deadlines, owners and authority contacts.",
    },
    {
        "id": "zenodo-publication-approval",
        "regulation": "GDPR, DGA, Data Act, Open Data Directive",
        "path": "docs/compliance/templates/zenodo-publication-approval.md",
        "purpose": "Legal approval checklist before publishing a Zenodo record.",
    },
    {
        "id": "openaire-discovery-approval",
        "regulation": "GDPR, DGA, Data Act, Open Data Directive",
        "path": "docs/compliance/templates/openaire-discovery-approval.md",
        "purpose": "Legal approval checklist before exposing metadata to OpenAIRE.",
    },
]

LEGAL_FINALIZATION_ITEMS: list[dict[str, str]] = [
    {
        "id": "architecture-controls",
        "status": "finalized",
        "owner": "platform",
        "decision": (
            "Evidence topics, schemas, release gates, API surfaces and UI management views "
            "are implemented."
        ),
        "evidence": "catalog_payload, /api/legal-compliance, compliance.legal.dossier",
    },
    {
        "id": "dataset-dmp-repository",
        "status": "finalized",
        "owner": "research-governance",
        "decision": "Dataset catalogue, DMP controls and Zenodo draft export are integrated.",
        "evidence": (
            "governance.dataset.catalog, governance.data_management_plans, "
            "governance.repository.exports"
        ),
    },
    {
        "id": "legal-template-pack",
        "status": "finalized",
        "owner": "legal-compliance",
        "decision": "Templates exist for every dossier artefact required by the release gates.",
        "evidence": "docs/compliance/templates",
    },
    {
        "id": "production-approval",
        "status": "approval_required",
        "owner": "DPO/legal/security/product owners",
        "decision": "Real organisation details, signatures and authority contacts are required.",
        "evidence": "compliance.legal.dossier",
    },
    {
        "id": "national-scope-approval",
        "status": "approval_required",
        "owner": "legal-compliance",
        "decision": (
            "Member State scope decisions for NIS2, ePrivacy and authority reporting "
            "channels must be recorded."
        ),
        "evidence": "compliance.scope.decisions, compliance.reporting.channels",
    },
    {
        "id": "external-release-approval",
        "status": "approval_required",
        "owner": "data-governance/research-governance",
        "decision": (
            "Third-party sharing and Zenodo publication require signed terms and "
            "legal_review_approved=true."
        ),
        "evidence": "dataact.third_party.sharing, governance.repository.exports",
    },
]

ADDITIONAL_LEGISLATION: list[dict[str, str]] = [
    {
        "regulation": "GDPR / RGPD",
        "applicability": "applicable",
        "reason": (
            "Telemetry, GPS, identifiers, timestamps, media metadata and research datasets can "
            "be personal data."
        ),
        "architecture_action": (
            "Keep legal-basis checks, DPIA, minimisation, retention, rights handling and "
            "processor evidence linked to each dataset and release."
        ),
        "evidence_topic": "dataact.legal_basis.checks",
    },
    {
        "regulation": "ePrivacy Directive",
        "applicability": "conditional",
        "reason": (
            "Applies if DEALIoT accesses terminal equipment, communications metadata or "
            "tracking identifiers under Member State ePrivacy law."
        ),
        "architecture_action": (
            "Record country scope, device notices, consent/exception basis and communications "
            "metadata minimisation."
        ),
        "evidence_topic": "compliance.scope.decisions",
    },
    {
        "regulation": "AI Act",
        "applicability": "conditional",
        "reason": "Applies if models or AI systems are deployed for analysis or decision support.",
        "architecture_action": (
            "Create AI inventory, classify risk, keep training/evaluation data lineage and "
            "document human oversight before deployment."
        ),
        "evidence_topic": "compliance.control.assessments",
    },
    {
        "regulation": "Trade Secrets Directive",
        "applicability": "conditional",
        "reason": "Relevant when Data Act sharing exposes protected know-how or confidential data.",
        "architecture_action": (
            "Bind third-party releases to safeguards, confidentiality terms, purpose limits and "
            "audit logs."
        ),
        "evidence_topic": "dataact.safeguards",
    },
    {
        "regulation": "Radio Equipment Directive",
        "applicability": "conditional",
        "reason": "Applies if DEALIoT radio gateways or devices are placed on the EU market.",
        "architecture_action": (
            "Maintain product conformity, radio/cybersecurity/privacy assessment and support "
            "evidence."
        ),
        "evidence_topic": "cra.product.lifecycle",
    },
    {
        "regulation": "GPSR and Product Liability Directive",
        "applicability": "conditional",
        "reason": (
            "Relevant when connected devices, software or digital services are supplied as "
            "products."
        ),
        "architecture_action": (
            "Maintain product safety file, defect handling, security-update history and market "
            "surveillance evidence."
        ),
        "evidence_topic": "cra.product.lifecycle",
    },
    {
        "regulation": "Cybersecurity Act",
        "applicability": "conditional",
        "reason": (
            "Relevant if certification is required by customers, procurement or sector rules."
        ),
        "architecture_action": (
            "Record certification applicability and map security controls to the selected EU "
            "scheme when needed."
        ),
        "evidence_topic": "compliance.control.assessments",
    },
    {
        "regulation": "Open Data Directive",
        "applicability": "conditional",
        "reason": "Applies only to public-sector information or public/open research-data reuse.",
        "architecture_action": (
            "Mark public-funded datasets, open-access obligations, licence and embargo status "
            "in the catalogue and DMP."
        ),
        "evidence_topic": "governance.dataset.catalog",
    },
    {
        "regulation": "EHDS",
        "applicability": "conditional",
        "reason": "Applies only if datasets contain personal electronic health data.",
        "architecture_action": (
            "Classify health-data scope before reuse; route secondary-use requests through the "
            "dataset catalogue and DMP controls."
        ),
        "evidence_topic": "governance.dataset.catalog",
    },
]

CRA_PRODUCT_LIFECYCLE: list[dict[str, str]] = [
    {
        "product_id": "dealiot-platform",
        "support_status": "planned",
        "evidence_topic": "cra.product.lifecycle",
        "control": (
            "Define support period, security update channel and vulnerability disclosure URL."
        ),
    },
    {
        "product_id": "wildfi-decoder-wrapper",
        "support_status": "planned",
        "evidence_topic": "cra.product.lifecycle",
        "control": "Track third-party decoder provenance, support and security update policy.",
    },
]

RUNBOOKS: list[dict[str, str]] = [
    {
        "name": "Operations",
        "path": "docs/runbooks/operations.md",
        "scope": "startup validation, runtime checks and troubleshooting.",
    },
    {
        "name": "Backup and restore",
        "path": "docs/runbooks/backup-restore.md",
        "scope": "database, object storage and platform recovery.",
    },
    {
        "name": "Security hardening",
        "path": "docs/runbooks/security-hardening.md",
        "scope": "TLS, authentication, secret handling and rotation.",
    },
    {
        "name": "Security resilience compliance",
        "path": "docs/runbooks/security-resilience-compliance.md",
        "scope": "NIS2, DORA and CRA evidence, incident, vulnerability and recovery controls.",
    },
    {
        "name": "Legal applicability",
        "path": "docs/runbooks/legal-applicability.md",
        "scope": "GDPR, ePrivacy, AI Act, product, open-data and EHDS scope matrix.",
    },
    {
        "name": "Legal compliance dossier",
        "path": "docs/compliance/legal-compliance-dossier.md",
        "scope": "Legal artefacts, release gates and evidence topics before go-live.",
    },
    {
        "name": "Legal finalization report",
        "path": "docs/compliance/legal-finalization-report.md",
        "scope": "Repository-side completion status and human approval requirements.",
    },
    {
        "name": "Data Governance Act",
        "path": "docs/runbooks/data-governance-act.md",
        "scope": "DGA role decision, intermediation evidence and data-sharing controls.",
    },
    {
        "name": "Data Act",
        "path": "docs/runbooks/data-act.md",
        "scope": "User access, third-party sharing and generated connected-product data.",
    },
    {
        "name": "Dataset catalogue and DMP",
        "path": "docs/runbooks/data-management-plan.md",
        "scope": "Dataset catalogue, FAIR metadata and Data Management Plan release gates.",
    },
    {
        "name": "Zenodo dataset export",
        "path": "docs/runbooks/zenodo-export.md",
        "scope": "Zenodo draft, manifest upload, staging directory and publication gates.",
    },
    {
        "name": "WildFi ingestion",
        "path": "docs/runbooks/wildfi-ingestion.md",
        "scope": "WildFi topic mapping, decoder use and data contracts.",
    },
]

OPERATIONS: list[dict[str, Any]] = [
    {
        "id": "refresh-health",
        "name": "Refresh service health",
        "method": "GET",
        "endpoint": "/api/health",
        "scope": "safe",
        "description": "Re-runs HTTP and TCP probes from inside the platform networks.",
    },
    {
        "id": "trigger-media-backfill",
        "name": "Trigger media backfill DAG",
        "method": "POST",
        "endpoint": "/api/operations/trigger-media-backfill",
        "scope": "controlled",
        "description": (
            "Triggers the Airflow media_backfill DAG when Airflow API credentials are set."
        ),
        "requires": ["AIRFLOW_API_USERNAME", "AIRFLOW_API_PASSWORD"],
    },
    {
        "id": "open-runbooks",
        "name": "Open runbooks",
        "method": "GET",
        "endpoint": "/api/runbooks",
        "scope": "safe",
        "description": "Lists operational runbooks included in the repository.",
    },
    {
        "id": "review-dga-readiness",
        "name": "Review DGA readiness",
        "method": "GET",
        "endpoint": "/api/dga",
        "scope": "safe",
        "description": "Lists DGA data products, obligations, evidence topics and open gaps.",
    },
    {
        "id": "review-data-act-readiness",
        "name": "Review Data Act readiness",
        "method": "GET",
        "endpoint": "/api/data-act",
        "scope": "safe",
        "description": (
            "Lists connected products, user access channels, sharing evidence and open gaps."
        ),
    },
    {
        "id": "review-dataset-dmp-readiness",
        "name": "Review dataset and DMP readiness",
        "method": "GET",
        "endpoint": "/api/datasets",
        "scope": "safe",
        "description": "Lists datasets, Data Management Plans and FAIR/release controls.",
    },
    {
        "id": "export-dataset-zenodo",
        "name": "Create Zenodo dataset draft",
        "method": "POST",
        "endpoint": "/api/datasets/zenodo/export",
        "scope": "controlled",
        "description": "Creates a Zenodo draft and uploads the dataset/DMP manifest.",
        "requires": ["ZENODO_ACCESS_TOKEN"],
    },
    {
        "id": "export-dataset-openaire",
        "name": "Create OpenAIRE metadata package",
        "method": "POST",
        "endpoint": "/api/datasets/openaire/export",
        "scope": "controlled",
        "description": (
            "Creates OpenAIRE/DataCite metadata package for PROVIDE or OAI-PMH exposure."
        ),
    },
    {
        "id": "review-intermediation-flow",
        "name": "Review intermediation flow",
        "method": "GET",
        "endpoint": "/api/intermediation",
        "scope": "safe",
        "description": "Lists consumer profiles, mediated delivery steps and required evidence.",
    },
    {
        "id": "review-research-readiness",
        "name": "Review research readiness",
        "method": "GET",
        "endpoint": "/api/research",
        "scope": "safe",
        "description": "Lists research purpose, project templates, gates and publication controls.",
    },
    {
        "id": "review-security-resilience-readiness",
        "name": "Review security resilience readiness",
        "method": "GET",
        "endpoint": "/api/security-resilience",
        "scope": "safe",
        "description": "Lists NIS2, DORA and CRA evidence topics, gates and open gaps.",
    },
    {
        "id": "review-nis2-readiness",
        "name": "Review NIS2 readiness",
        "method": "GET",
        "endpoint": "/api/nis2",
        "scope": "safe",
        "description": "Lists NIS2 risk management, incident and continuity controls.",
    },
    {
        "id": "review-dora-readiness",
        "name": "Review DORA readiness",
        "method": "GET",
        "endpoint": "/api/dora",
        "scope": "safe",
        "description": "Lists DORA ICT-risk controls when financial-sector scope applies.",
    },
    {
        "id": "review-cra-readiness",
        "name": "Review CRA readiness",
        "method": "GET",
        "endpoint": "/api/cra",
        "scope": "safe",
        "description": "Lists CRA secure-by-design, vulnerability and update controls.",
    },
    {
        "id": "review-legal-compliance",
        "name": "Review legal compliance dossier",
        "method": "GET",
        "endpoint": "/api/legal-compliance",
        "scope": "safe",
        "description": "Lists mandatory legal artefacts, templates, gates and evidence topics.",
    },
]

COMPLIANCE_CONTROLS: list[dict[str, str]] = [
    {
        "id": "data-map",
        "status": "partial",
        "regulation": "GDPR, Data Act, DGA",
        "control": (
            "Maintain topic-level and data-product inventory, purpose, owner and recipients."
        ),
    },
    {
        "id": "dga-neutrality",
        "status": "partial",
        "regulation": "DGA",
        "control": "Operate data intermediation as a separated governance plane with no own reuse.",
    },
    {
        "id": "mediated-access",
        "status": "implemented",
        "regulation": "DGA",
        "control": "Route applications and researchers through mediated data products.",
    },
    {
        "id": "dga-permissions",
        "status": "partial",
        "regulation": "DGA",
        "control": "Track research permissions, consent and withdrawals.",
    },
    {
        "id": "research-governance",
        "status": "partial",
        "regulation": "DGA, GDPR",
        "control": "Require research protocol, ethics status and disclosure review.",
    },
    {
        "id": "dataset-catalog-dmp",
        "status": "partial",
        "regulation": "DGA, Data Act, GDPR",
        "control": "Maintain dataset catalogue and DMP before research or third-party release.",
    },
    {
        "id": "zenodo-repository-export",
        "status": "partial",
        "regulation": "DGA, Data Act, GDPR, Open Data Directive",
        "control": "Export datasets to Zenodo as draft records with DMP and legal release gates.",
    },
    {
        "id": "openaire-discovery-export",
        "status": "partial",
        "regulation": "DGA, Data Act, GDPR, Open Data Directive",
        "control": (
            "Export OpenAIRE-compatible metadata packages for discovery without raw upload."
        ),
    },
    {
        "id": "dga-activity-log",
        "status": "implemented",
        "regulation": "DGA",
        "control": "Maintain a log record of data intermediation activity.",
    },
    {
        "id": "data-act-user-access",
        "status": "partial",
        "regulation": "Data Act",
        "control": (
            "Provide user access to generated connected-product data through logged channels."
        ),
    },
    {
        "id": "data-act-third-party-sharing",
        "status": "partial",
        "regulation": "Data Act",
        "control": "Share data with third parties only on user authorization and scoped evidence.",
    },
    {
        "id": "data-act-portability",
        "status": "implemented",
        "regulation": "Data Act",
        "control": "Publish portable JSON contracts and export logs for released datasets.",
    },
    {
        "id": "data-act-legal-basis",
        "status": "partial",
        "regulation": "Data Act, GDPR",
        "control": "Check personal-data legal basis before user or third-party release.",
    },
    {
        "id": "gdpr-dpia-rights",
        "status": "partial",
        "regulation": "GDPR",
        "control": "Maintain DPIA, rights handling, processor terms and breach evidence.",
    },
    {
        "id": "legal-dossier",
        "status": "partial",
        "regulation": "GDPR, DGA, Data Act, NIS2, DORA, CRA",
        "control": (
            "Maintain legal dossier artefacts and block releases until required approvals exist."
        ),
    },
    {
        "id": "eprivacy-terminal-access",
        "status": "conditional",
        "regulation": "ePrivacy",
        "control": "Assess terminal access, telemetry metadata and national consent rules.",
    },
    {
        "id": "retention",
        "status": "todo",
        "regulation": "GDPR, Data Act",
        "control": "Apply retention policies to raw Kafka topics, S3 buckets, DLQ and backups.",
    },
    {
        "id": "pseudonymisation",
        "status": "todo",
        "regulation": "GDPR",
        "control": "Pseudonymise device identifiers and restrict raw GPS/media access.",
    },
    {
        "id": "transport-security",
        "status": "partial",
        "regulation": "GDPR, CRA, NIS2",
        "control": "Replace local plaintext protocols with TLS/SASL/mTLS in production.",
    },
    {
        "id": "supply-chain",
        "status": "partial",
        "regulation": "CRA, NIS2",
        "control": "Publish SBOM/provenance and add image signature admission policy.",
    },
    {
        "id": "security-incident-reporting",
        "status": "partial",
        "regulation": "NIS2, DORA, CRA",
        "control": "Classify incidents, track deadlines and retain reporting evidence.",
    },
    {
        "id": "vulnerability-management",
        "status": "partial",
        "regulation": "CRA, NIS2",
        "control": "Track vulnerabilities, due dates, patches and accepted residual risk.",
    },
    {
        "id": "operational-resilience",
        "status": "partial",
        "regulation": "NIS2, DORA",
        "control": "Maintain ICT risk, continuity tests, RPO/RTO evidence and recovery proof.",
    },
    {
        "id": "third-party-risk",
        "status": "partial",
        "regulation": "NIS2, DORA, CRA",
        "control": "Assess providers, subcontracting, criticality and exit plans.",
    },
    {
        "id": "trade-secret-safeguards",
        "status": "partial",
        "regulation": "Data Act, Trade Secrets Directive",
        "control": "Preserve confidentiality and purpose limits for sensitive shared data.",
    },
    {
        "id": "product-market-scope",
        "status": "conditional",
        "regulation": "CRA, RED, GPSR, Product Liability Directive",
        "control": "Record product-market role, conformity file, support and defect handling.",
    },
    {
        "id": "dora-scope",
        "status": "conditional",
        "regulation": "DORA",
        "control": "Apply DORA fully only for financial entities or ICT providers in scope.",
    },
    {
        "id": "scope-and-reporting",
        "status": "partial",
        "regulation": "DGA, Data Act, NIS2, DORA, CRA",
        "control": "Record scope decisions, control assessments and authority reporting channels.",
    },
    {
        "id": "cra-product-lifecycle",
        "status": "todo",
        "regulation": "CRA",
        "control": (
            "Define product support period, update channel and vulnerability disclosure URL."
        ),
    },
    {
        "id": "ai-governance",
        "status": "conditional",
        "regulation": "AI Act",
        "control": "Inventory, classify and document AI systems before model deployment.",
    },
    {
        "id": "open-health-data-scope",
        "status": "conditional",
        "regulation": "Open Data Directive, EHDS",
        "control": "Classify public-sector, public-funded research and health-data datasets.",
    },
]


def catalog_payload() -> dict[str, Any]:
    return {
        "components": COMPONENTS,
        "topics": TOPICS,
        "data_products": DATA_PRODUCTS,
        "datasets": DATASETS,
        "data_management_plans": DATA_MANAGEMENT_PLANS,
        "dmp_controls": DMP_CONTROLS,
        "zenodo_export_policy": ZENODO_EXPORT_POLICY,
        "openaire_export_policy": OPENAIRE_EXPORT_POLICY,
        "data_act_connected_products": DATA_ACT_CONNECTED_PRODUCTS,
        "data_act_access_channels": DATA_ACT_ACCESS_CHANNELS,
        "data_act_obligations": DATA_ACT_OBLIGATIONS,
        "data_act_user_journey": DATA_ACT_USER_JOURNEY,
        "intermediation_flow": INTERMEDIATION_FLOW,
        "consumer_profiles": CONSUMER_PROFILES,
        "dga_obligations": DGA_OBLIGATIONS,
        "security_resilience_controls": SECURITY_RESILIENCE_CONTROLS,
        "security_resilience_gates": SECURITY_RESILIENCE_GATES,
        "compliance_scope_decisions": COMPLIANCE_SCOPE_DECISIONS,
        "compliance_reporting_channels": COMPLIANCE_REPORTING_CHANNELS,
        "compliance_readiness": COMPLIANCE_READINESS,
        "legal_compliance_dossier": LEGAL_COMPLIANCE_DOSSIER,
        "legal_release_gates": LEGAL_RELEASE_GATES,
        "legal_templates": LEGAL_TEMPLATES,
        "legal_finalization_items": LEGAL_FINALIZATION_ITEMS,
        "additional_legislation": ADDITIONAL_LEGISLATION,
        "cra_product_lifecycle": CRA_PRODUCT_LIFECYCLE,
        "nis2_obligations": NIS2_OBLIGATIONS,
        "dora_obligations": DORA_OBLIGATIONS,
        "cra_obligations": CRA_OBLIGATIONS,
        "research_context": RESEARCH_CONTEXT,
        "research_projects": RESEARCH_PROJECTS,
        "research_controls": RESEARCH_CONTROLS,
        "runbooks": RUNBOOKS,
        "operations": OPERATIONS,
        "compliance_controls": COMPLIANCE_CONTROLS,
    }


def security_resilience_payload() -> dict[str, Any]:
    return {
        "controls": SECURITY_RESILIENCE_CONTROLS,
        "release_gates": SECURITY_RESILIENCE_GATES,
        "nis2_obligations": NIS2_OBLIGATIONS,
        "dora_obligations": DORA_OBLIGATIONS,
        "cra_obligations": CRA_OBLIGATIONS,
        "evidence_topics": [
            topic
            for topic in TOPICS
            if topic["name"].startswith("security.")
            or topic["name"].startswith("resilience.")
            or topic["name"].startswith("compliance.")
            or topic["name"].startswith("cra.")
        ],
        "scope_decisions": COMPLIANCE_SCOPE_DECISIONS,
        "reporting_channels": COMPLIANCE_REPORTING_CHANNELS,
        "readiness": COMPLIANCE_READINESS,
        "additional_legislation": ADDITIONAL_LEGISLATION,
        "cra_product_lifecycle": CRA_PRODUCT_LIFECYCLE,
        "scope_notes": [
            "NIS2 depends on sector, entity size and national transposition.",
            "DORA applies when financial entity or ICT third-party provider scope is confirmed.",
            "CRA applies to products with digital elements made available on the EU market.",
            "GDPR is in scope when telemetry or datasets identify people or operators.",
            "AI Act, ePrivacy, RED, product safety, EHDS and open-data rules are conditional.",
        ],
        "default_policy": {
            "plaintext_production_protocols": "not allowed",
            "critical_vulnerabilities": "block release unless mitigated or accepted by owner",
            "incident_evidence": "record severity, affected assets, deadlines and channels",
            "supply_chain": "SBOM, provenance and signature evidence required for releases",
            "resilience": "restore tests and supplier exit plans required before go-live",
        },
    }


def compliance_payload() -> dict[str, Any]:
    return {
        "readiness": COMPLIANCE_READINESS,
        "controls": COMPLIANCE_CONTROLS,
        "scope_decisions": COMPLIANCE_SCOPE_DECISIONS,
        "reporting_channels": COMPLIANCE_REPORTING_CHANNELS,
        "legal_dossier": LEGAL_COMPLIANCE_DOSSIER,
        "release_gates": LEGAL_RELEASE_GATES,
        "templates": LEGAL_TEMPLATES,
        "finalization_items": LEGAL_FINALIZATION_ITEMS,
        "additional_legislation": ADDITIONAL_LEGISLATION,
        "legal_dossier_topic": "compliance.legal.dossier",
        "control_assessment_topic": "compliance.control.assessments",
        "evidence_topics": [
            topic
            for topic in TOPICS
            if topic["name"].startswith("compliance.")
            or topic["name"] in {"dataact.legal_basis.checks", "cra.product.lifecycle"}
        ],
        "verdict": (
            "technical evidence baseline only; legal compliance remains partial until "
            "scope, procedures, contracts, approvals and operating evidence are recorded"
        ),
    }


def legal_compliance_payload() -> dict[str, Any]:
    return {
        "legal_dossier": LEGAL_COMPLIANCE_DOSSIER,
        "release_gates": LEGAL_RELEASE_GATES,
        "templates": LEGAL_TEMPLATES,
        "finalization_items": LEGAL_FINALIZATION_ITEMS,
        "scope_decisions": COMPLIANCE_SCOPE_DECISIONS,
        "reporting_channels": COMPLIANCE_REPORTING_CHANNELS,
        "evidence_topics": [
            topic
            for topic in TOPICS
            if topic["name"].startswith("compliance.")
            or topic["name"]
            in {
                "dataact.legal_basis.checks",
                "governance.dataset.catalog",
                "governance.data_management_plans",
                "governance.repository.exports",
            }
        ],
        "default_policy": {
            "production_go_live": "blocked until mandatory legal dossier is approved",
            "dataset_sharing": "blocked until catalogue, DMP and legal review are complete",
            "zenodo_publication": "draft only until legal_review_approved is true",
            "legal_verdict": "reviewable baseline, not legal certification",
        },
    }


def dataset_payload() -> dict[str, Any]:
    return {
        "datasets": DATASETS,
        "data_management_plans": DATA_MANAGEMENT_PLANS,
        "controls": DMP_CONTROLS,
        "zenodo_export_policy": ZENODO_EXPORT_POLICY,
        "openaire_export_policy": OPENAIRE_EXPORT_POLICY,
        "evidence_topics": [
            topic
            for topic in TOPICS
            if topic["name"]
            in {
                "governance.dataset.catalog",
                "governance.data_management_plans",
                "governance.repository.exports",
            }
        ],
        "default_policy": {
            "dataset_release": "requires catalogue entry, DMP, access policy and review",
            "raw_dataset_access": "restricted by default",
            "preferred_publication": "derived, minimised or aggregated datasets",
            "fair_metadata": "schema, provenance, steward, access and preservation fields required",
            "zenodo_publish": "draft first; legal_review_approved required for publication",
            "openaire_export": "metadata package; OpenAIRE PROVIDE registration required",
        },
    }


def nis2_payload() -> dict[str, Any]:
    payload = security_resilience_payload()
    return {
        "obligations": NIS2_OBLIGATIONS,
        "controls": [
            control for control in SECURITY_RESILIENCE_CONTROLS if "NIS2" in control["regulation"]
        ],
        "evidence_topics": payload["evidence_topics"],
        "scope_note": payload["scope_notes"][0],
    }


def dora_payload() -> dict[str, Any]:
    payload = security_resilience_payload()
    return {
        "obligations": DORA_OBLIGATIONS,
        "controls": [
            control for control in SECURITY_RESILIENCE_CONTROLS if "DORA" in control["regulation"]
        ],
        "evidence_topics": payload["evidence_topics"],
        "scope_note": payload["scope_notes"][1],
    }


def cra_payload() -> dict[str, Any]:
    payload = security_resilience_payload()
    return {
        "obligations": CRA_OBLIGATIONS,
        "product_lifecycle": CRA_PRODUCT_LIFECYCLE,
        "controls": [
            control for control in SECURITY_RESILIENCE_CONTROLS if "CRA" in control["regulation"]
        ],
        "evidence_topics": payload["evidence_topics"],
        "scope_note": payload["scope_notes"][2],
    }


def data_act_payload() -> dict[str, Any]:
    return {
        "connected_products": DATA_ACT_CONNECTED_PRODUCTS,
        "access_channels": DATA_ACT_ACCESS_CHANNELS,
        "obligations": DATA_ACT_OBLIGATIONS,
        "user_journey": DATA_ACT_USER_JOURNEY,
        "datasets": DATASETS,
        "data_management_plans": DATA_MANAGEMENT_PLANS,
        "evidence_topics": [
            topic
            for topic in TOPICS
            if topic["name"].startswith("dataact.")
            or topic["name"]
            in {
                "governance.dataset.catalog",
                "governance.data_management_plans",
                "governance.intermediation.log",
                "governance.repository.exports",
                "governance.transfer.notices",
            }
        ],
        "legal_basis_topic": "dataact.legal_basis.checks",
        "default_policy": {
            "raw_topics": "denied by default unless scope, entitlement and safeguards are approved",
            "preferred_delivery": [
                "direct secure API",
                "minimised export",
                "controlled object access",
                "DGA-mediated research data product",
            ],
            "third_party_sharing": (
                "requires user authorization, recipient identity and purpose scope"
            ),
            "research_access": "combine Data Act user entitlement with DGA research governance",
        },
    }


def dga_payload() -> dict[str, Any]:
    return {
        "data_products": DATA_PRODUCTS,
        "datasets": DATASETS,
        "data_management_plans": DATA_MANAGEMENT_PLANS,
        "intermediation_flow": INTERMEDIATION_FLOW,
        "consumer_profiles": CONSUMER_PROFILES,
        "obligations": DGA_OBLIGATIONS,
        "research_context": RESEARCH_CONTEXT,
        "research_projects": RESEARCH_PROJECTS,
        "research_controls": RESEARCH_CONTROLS,
        "evidence_topics": [
            topic
            for topic in TOPICS
            if topic["name"].startswith("governance.")
            or topic["name"] in {"dlq.events", "compliance.reporting.channels"}
        ],
        "architectural_principles": [
            "separate governance plane for intermediation metadata",
            "no own reuse of mediated data by the intermediation layer",
            "purpose-bound access requests and decisions",
            "consumer profiles for applications and scientists",
            "mediated delivery before raw access",
            "consent and permission withdrawal evidence",
            "activity logging for every data-sharing action",
            "research protocol and ethics status before project access",
            "publication disclosure review before external release",
            "schema-based interoperability and transparent formats",
            "dataset catalogue and DMP before mediated research release",
            "unauthorised access, transfer and use notice trail",
        ],
    }


def research_payload() -> dict[str, Any]:
    return {
        "research_context": RESEARCH_CONTEXT,
        "projects": RESEARCH_PROJECTS,
        "controls": RESEARCH_CONTROLS,
        "datasets": DATASETS,
        "data_management_plans": DATA_MANAGEMENT_PLANS,
        "dmp_controls": DMP_CONTROLS,
        "zenodo_export_policy": ZENODO_EXPORT_POLICY,
        "openaire_export_policy": OPENAIRE_EXPORT_POLICY,
        "research_topics": [
            topic
            for topic in TOPICS
            if topic["name"].startswith("governance.research.")
            or topic["name"]
            in {
                "governance.dataset.catalog",
                "governance.data_management_plans",
                "governance.repository.exports",
            }
        ],
        "recommended_default": (
            "share derived or pseudonymised research datasets before raw GPS, raw payloads or media"
        ),
    }


def intermediation_payload() -> dict[str, Any]:
    return {
        "flow": INTERMEDIATION_FLOW,
        "consumer_profiles": CONSUMER_PROFILES,
        "default_policy": {
            "raw_topics": "restricted",
            "derived_topics": "preferred",
            "applications": "purpose-bound service accounts",
            "scientists": "project-bound access packages",
            "evidence": [
                "governance.access.requests",
                "governance.permission.events",
                "governance.intermediation.log",
                "governance.research.projects",
                "governance.research.outputs",
            ],
        },
    }
