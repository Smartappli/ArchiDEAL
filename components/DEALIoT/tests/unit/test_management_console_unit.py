from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console.app import configured_probe, first_host_port  # noqa: E402
from management_console.catalog import (  # noqa: E402
    catalog_payload,
    compliance_payload,
    cra_payload,
    data_act_payload,
    dataset_payload,
    dga_payload,
    dora_payload,
    intermediation_payload,
    legal_compliance_payload,
    nis2_payload,
    research_payload,
    security_resilience_payload,
)


class ManagementConsoleUnitTests(unittest.TestCase):
    def test_catalog_payload_contains_core_management_surfaces(self) -> None:
        payload = catalog_payload()
        component_ids = {component["id"] for component in payload["components"]}
        topic_names = {topic["name"] for topic in payload["topics"]}
        operation_ids = {operation["id"] for operation in payload["operations"]}
        data_product_ids = {product["product_id"] for product in payload["data_products"]}
        dataset_ids = {dataset["dataset_id"] for dataset in payload["datasets"]}
        dmp_ids = {dmp["dmp_id"] for dmp in payload["data_management_plans"]}
        data_act_products = {
            product["product_id"] for product in payload["data_act_connected_products"]
        }
        research_control_ids = {control["id"] for control in payload["research_controls"]}
        profile_ids = {profile["profile_id"] for profile in payload["consumer_profiles"]}
        additional_regs = {item["regulation"] for item in payload["additional_legislation"]}

        self.assertIn("kafka", component_ids)
        self.assertIn("airflow", component_ids)
        self.assertIn("flink", component_ids)
        self.assertIn("data-governance", component_ids)
        self.assertIn("security-resilience", component_ids)
        self.assertIn("raw.gps", topic_names)
        self.assertIn("dlq.events", topic_names)
        self.assertIn("governance.intermediation.log", topic_names)
        self.assertIn("governance.research.projects", topic_names)
        self.assertIn("governance.research.outputs", topic_names)
        self.assertIn("governance.dataset.catalog", topic_names)
        self.assertIn("governance.data_management_plans", topic_names)
        self.assertIn("governance.repository.exports", topic_names)
        self.assertIn("dataact.product.catalog", topic_names)
        self.assertIn("dataact.user.access.requests", topic_names)
        self.assertIn("dataact.third_party.sharing", topic_names)
        self.assertIn("telemetry.raw.gps", data_product_ids)
        self.assertIn("dataset.telemetry.raw-gps-restricted", dataset_ids)
        self.assertIn("dmp.livestock-behaviour.template", dmp_ids)
        self.assertIn("connected-device.telemetry", data_act_products)
        self.assertIn("research-protocol", research_control_ids)
        self.assertIn("data-management-plan", research_control_ids)
        self.assertIn("GDPR / RGPD", additional_regs)
        self.assertIn("AI Act", additional_regs)
        self.assertIn("ePrivacy Directive", additional_regs)
        self.assertIn("application.operational", profile_ids)
        self.assertIn("researcher.external", profile_ids)
        self.assertIn("refresh-health", operation_ids)
        self.assertIn("review-dga-readiness", operation_ids)
        self.assertIn("review-data-act-readiness", operation_ids)
        self.assertIn("review-dataset-dmp-readiness", operation_ids)
        self.assertIn("export-dataset-zenodo", operation_ids)
        self.assertIn("review-intermediation-flow", operation_ids)
        self.assertIn("review-research-readiness", operation_ids)
        self.assertIn("review-security-resilience-readiness", operation_ids)
        self.assertIn("review-nis2-readiness", operation_ids)
        self.assertIn("review-dora-readiness", operation_ids)
        self.assertIn("review-cra-readiness", operation_ids)
        self.assertIn("trigger-media-backfill", operation_ids)

    def test_catalog_payload_contains_security_and_compliance_surfaces(self) -> None:
        payload = catalog_payload()
        topic_names = {topic["name"] for topic in payload["topics"]}
        security_control_ids = {
            control["id"] for control in payload["security_resilience_controls"]
        }
        readiness_regs = {item["regulation"] for item in payload["compliance_readiness"]}

        self.assertIn("dataact.legal_basis.checks", topic_names)
        self.assertIn("security.incident.events", topic_names)
        self.assertIn("security.vulnerability.findings", topic_names)
        self.assertIn("security.sbom.attestations", topic_names)
        self.assertIn("resilience.backup.tests", topic_names)
        self.assertIn("compliance.scope.decisions", topic_names)
        self.assertIn("compliance.reporting.channels", topic_names)
        self.assertIn("compliance.legal.dossier", topic_names)
        self.assertIn("cra.product.lifecycle", topic_names)
        self.assertIn("incident-reporting", security_control_ids)
        self.assertIn("scope-decisions", security_control_ids)
        self.assertIn("third-party-ict-risk", security_control_ids)
        self.assertIn("DGA", readiness_regs)
        self.assertIn("CRA", readiness_regs)
        self.assertIn("GDPR", readiness_regs)
        self.assertIn("AI Act", readiness_regs)

    def test_dga_payload_exposes_evidence_topics_and_obligations(self) -> None:
        payload = dga_payload()
        evidence_topics = {topic["name"] for topic in payload["evidence_topics"]}
        obligation_ids = {obligation["id"] for obligation in payload["obligations"]}

        self.assertIn("governance.data.products", evidence_topics)
        self.assertIn("governance.permission.events", evidence_topics)
        self.assertIn("governance.intermediation.log", evidence_topics)
        self.assertIn("governance.research.projects", evidence_topics)
        self.assertIn("governance.dataset.catalog", evidence_topics)
        self.assertIn("governance.data_management_plans", evidence_topics)
        self.assertIn("neutrality", obligation_ids)
        self.assertIn("dataset-catalog-dmp", obligation_ids)
        self.assertIn("intermediation-log", obligation_ids)

    def test_dataset_payload_exposes_catalog_and_dmp_controls(self) -> None:
        payload = dataset_payload()
        dataset_ids = {dataset["dataset_id"] for dataset in payload["datasets"]}
        dmp_ids = {dmp["dmp_id"] for dmp in payload["data_management_plans"]}
        control_ids = {control["id"] for control in payload["controls"]}
        evidence_topics = {topic["name"] for topic in payload["evidence_topics"]}
        operation_ids = {operation["id"] for operation in catalog_payload()["operations"]}

        self.assertIn("dataset.telemetry.sensor-minimised", dataset_ids)
        self.assertIn("dmp.precision-agriculture.template", dmp_ids)
        self.assertIn("dataset-catalog", control_ids)
        self.assertIn("dmp-required", control_ids)
        self.assertIn("governance.dataset.catalog", evidence_topics)
        self.assertIn("governance.data_management_plans", evidence_topics)
        self.assertIn("governance.repository.exports", evidence_topics)
        self.assertEqual(
            payload["default_policy"]["raw_dataset_access"],
            "restricted by default",
        )
        self.assertEqual(
            payload["default_policy"]["zenodo_publish"],
            "draft first; legal_review_approved required for publication",
        )
        self.assertIn(
            "draft-first",
            {control["id"] for control in payload["zenodo_export_policy"]},
        )
        self.assertIn(
            "metadata-first",
            {control["id"] for control in payload["openaire_export_policy"]},
        )
        self.assertIn("export-dataset-openaire", operation_ids)
        self.assertEqual(
            payload["default_policy"]["openaire_export"],
            "metadata package; OpenAIRE PROVIDE registration required",
        )

    def test_data_act_payload_exposes_user_access_and_third_party_sharing(self) -> None:
        payload = data_act_payload()
        evidence_topics = {topic["name"] for topic in payload["evidence_topics"]}
        channel_ids = {channel["channel_id"] for channel in payload["access_channels"]}
        obligation_ids = {obligation["id"] for obligation in payload["obligations"]}

        self.assertIn("dataact.product.catalog", evidence_topics)
        self.assertIn("dataact.user.access.requests", evidence_topics)
        self.assertIn("dataact.third_party.sharing", evidence_topics)
        self.assertIn("dataact.user.exports", evidence_topics)
        self.assertIn("dataact.legal_basis.checks", evidence_topics)
        self.assertIn("governance.dataset.catalog", evidence_topics)
        self.assertIn("governance.repository.exports", evidence_topics)
        self.assertIn("dataact.direct-access", channel_ids)
        self.assertIn("dataact.third-party-transfer", channel_ids)
        self.assertIn("user-access", obligation_ids)
        self.assertIn("third-party-sharing", obligation_ids)
        self.assertEqual(
            payload["default_policy"]["third_party_sharing"],
            "requires user authorization, recipient identity and purpose scope",
        )

    def test_security_resilience_payload_exposes_nis2_dora_and_cra_controls(self) -> None:
        payload = security_resilience_payload()
        evidence_topics = {topic["name"] for topic in payload["evidence_topics"]}
        control_ids = {control["id"] for control in payload["controls"]}
        gate_ids = {gate["gate"] for gate in payload["release_gates"]}

        self.assertIn("security.asset.inventory", evidence_topics)
        self.assertIn("security.incident.events", evidence_topics)
        self.assertIn("security.vulnerability.findings", evidence_topics)
        self.assertIn("security.sbom.attestations", evidence_topics)
        self.assertIn("resilience.operational.risk", evidence_topics)
        self.assertIn("compliance.scope.decisions", evidence_topics)
        self.assertIn("cra.product.lifecycle", evidence_topics)
        self.assertIn("incident-reporting", control_ids)
        self.assertIn("dora-scope", control_ids)
        self.assertIn("reporting-channels", control_ids)
        self.assertIn("release-supply-chain", gate_ids)
        self.assertEqual(
            payload["default_policy"]["plaintext_production_protocols"],
            "not allowed",
        )

    def test_regulation_specific_payloads_are_filtered(self) -> None:
        nis2_controls = {control["id"] for control in nis2_payload()["controls"]}
        dora_controls = {control["id"] for control in dora_payload()["controls"]}
        cra_controls = {control["id"] for control in cra_payload()["controls"]}

        self.assertIn("continuity-testing", nis2_controls)
        self.assertIn("dora-scope", dora_controls)
        self.assertIn("vulnerability-handling", cra_controls)

    def test_compliance_payload_states_partial_legal_readiness(self) -> None:
        payload = compliance_payload()
        topic_names = {topic["name"] for topic in payload["evidence_topics"]}
        readiness = {item["regulation"]: item["readiness"] for item in payload["readiness"]}
        channels = {item["regulation"] for item in payload["reporting_channels"]}
        scope_regs = {item["regulation"] for item in payload["scope_decisions"]}
        additional = {
            item["regulation"]: item["applicability"] for item in payload["additional_legislation"]
        }
        control_ids = {item["id"] for item in payload["controls"]}

        self.assertEqual(readiness["DORA"], "conditional")
        self.assertEqual(readiness["Data Act"], "partial")
        self.assertEqual(readiness["GDPR"], "partial")
        self.assertEqual(readiness["AI Act"], "conditional")
        self.assertIn("compliance.scope.decisions", topic_names)
        self.assertIn("compliance.control.assessments", topic_names)
        self.assertIn("compliance.reporting.channels", topic_names)
        self.assertIn("compliance.legal.dossier", topic_names)
        self.assertIn("dataact.legal_basis.checks", topic_names)
        self.assertIn("CRA", channels)
        self.assertIn("GDPR", channels)
        self.assertIn("ePrivacy", scope_regs)
        self.assertEqual(additional["GDPR / RGPD"], "applicable")
        self.assertEqual(additional["AI Act"], "conditional")
        self.assertEqual(additional["EHDS"], "conditional")
        self.assertIn("gdpr-dpia-rights", control_ids)
        self.assertIn("legal-dossier", control_ids)
        self.assertIn("eprivacy-terminal-access", control_ids)
        self.assertIn("product-market-scope", control_ids)
        self.assertIn("zenodo-repository-export", control_ids)
        self.assertIn("openaire-discovery-export", control_ids)
        self.assertEqual(payload["legal_dossier_topic"], "compliance.legal.dossier")
        self.assertIn("technical evidence baseline only", payload["verdict"])

    def test_legal_compliance_payload_exposes_dossier_gates_and_templates(self) -> None:
        payload = legal_compliance_payload()
        dossier_ids = {item["id"] for item in payload["legal_dossier"]}
        gate_ids = {gate["id"] for gate in payload["release_gates"]}
        template_ids = {template["id"] for template in payload["templates"]}
        finalization = {item["id"]: item["status"] for item in payload["finalization_items"]}
        evidence_topics = {topic["name"] for topic in payload["evidence_topics"]}
        operation_ids = {operation["id"] for operation in catalog_payload()["operations"]}

        self.assertIn("ropa-register", dossier_ids)
        self.assertIn("dpia-aipd", dossier_ids)
        self.assertIn("data-sharing-agreement", dossier_ids)
        self.assertIn("zenodo-publication-approval", dossier_ids)
        self.assertIn("openaire-discovery-approval", dossier_ids)
        self.assertIn("production-go-live", gate_ids)
        self.assertIn("dataset-sharing", gate_ids)
        self.assertIn("zenodo-publication", gate_ids)
        self.assertIn("external-catalog-discovery", gate_ids)
        self.assertIn("ropa-template", template_ids)
        self.assertIn("data-act-notice-template", template_ids)
        self.assertIn("processor-dpa-checklist", template_ids)
        self.assertIn("dga-role-notification-template", template_ids)
        self.assertIn("cra-conformity-file-template", template_ids)
        self.assertIn("openaire-discovery-approval", template_ids)
        self.assertEqual(finalization["architecture-controls"], "finalized")
        self.assertEqual(finalization["production-approval"], "approval_required")
        self.assertIn("compliance.legal.dossier", evidence_topics)
        self.assertIn("review-legal-compliance", operation_ids)
        self.assertEqual(
            payload["default_policy"]["legal_verdict"],
            "reviewable baseline, not legal certification",
        )

    def test_compliance_ui_exposes_additional_legislation_matrix(self) -> None:
        html = (REPO_ROOT / "management-console" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        javascript = (REPO_ROOT / "management-console" / "static" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="additional-legislation-table"', html)
        self.assertIn("additional_legislation", javascript)
        self.assertIn("#additional-legislation-table", javascript)
        self.assertIn('id="legal-dossier-table"', html)
        self.assertIn('id="legal-release-gate-list"', html)
        self.assertIn('id="legal-template-table"', html)
        self.assertIn('id="legal-finalization-table"', html)
        self.assertIn("legal_compliance_dossier", javascript)
        self.assertIn("legal_release_gates", javascript)
        self.assertIn("legal_templates", javascript)
        self.assertIn("legal_finalization_items", javascript)
        self.assertIn('id="zenodo-export-policy"', html)
        self.assertIn('id="openaire-export-policy"', html)
        self.assertIn("zenodo_export_policy", javascript)
        self.assertIn("openaire_export_policy", javascript)
        self.assertIn("zenodo-export", javascript)
        self.assertIn("openaire-export", javascript)

    def test_research_payload_exposes_research_collection_context(self) -> None:
        payload = research_payload()
        topic_names = {topic["name"] for topic in payload["research_topics"]}
        control_ids = {control["id"] for control in payload["controls"]}

        self.assertEqual(payload["research_context"]["primary_purpose"], "scientific research")
        self.assertIn("governance.research.projects", topic_names)
        self.assertIn("governance.research.outputs", topic_names)
        self.assertIn("governance.dataset.catalog", topic_names)
        self.assertIn("governance.data_management_plans", topic_names)
        self.assertIn("governance.repository.exports", topic_names)
        self.assertIn("ethics-review", control_ids)
        self.assertIn("publication-review", control_ids)
        self.assertIn("data-management-plan", control_ids)

    def test_intermediation_payload_routes_consumers_through_mediated_access(self) -> None:
        payload = intermediation_payload()
        profile_ids = {profile["profile_id"] for profile in payload["consumer_profiles"]}
        evidence = set(payload["default_policy"]["evidence"])

        self.assertEqual(payload["default_policy"]["raw_topics"], "restricted")
        self.assertIn("application.operational", profile_ids)
        self.assertIn("researcher.internal", profile_ids)
        self.assertIn("governance.access.requests", evidence)
        self.assertIn("governance.intermediation.log", evidence)

    def test_first_host_port_accepts_common_kafka_listener_prefixes(self) -> None:
        self.assertEqual(
            first_host_port("SASL_SSL://kafka1.example.net:9093,kafka2.example.net:9093"),
            "kafka1.example.net:9093",
        )
        self.assertEqual(first_host_port("kafka1:9092,kafka2:9092"), "kafka1:9092")
        self.assertIsNone(first_host_port(""))

    def test_configured_probe_uses_runtime_environment(self) -> None:
        kafka_component = {"id": "kafka", "probe": "tcp://kafka1:9092"}
        mqtt_component = {"id": "vernemq", "probe": "tcp://vernemq1:1883"}
        airflow_component = {"id": "airflow", "probe": "http://airflow-apiserver:8080/api/v2"}

        with patch.dict(
            "os.environ",
            {
                "KAFKA_BOOTSTRAP_SERVERS": "SASL_SSL://kafka.example.net:9093",
                "MQTT_HOST": "mqtt.example.net",
                "MQTT_PORT": "8883",
                "AIRFLOW_API_URL": "https://airflow.example.net/api/v2",
            },
            clear=False,
        ):
            self.assertEqual(configured_probe(kafka_component), "tcp://kafka.example.net:9093")
            self.assertEqual(configured_probe(mqtt_component), "tcp://mqtt.example.net:8883")
            self.assertEqual(
                configured_probe(airflow_component),
                "https://airflow.example.net/api/v2/version",
            )


if __name__ == "__main__":
    unittest.main()
