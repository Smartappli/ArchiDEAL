from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class PlatformIntegrationTests(unittest.TestCase):
    def test_seaweed_cluster_services_are_defined(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        services = [
            "seaweedfs-master1",
            "seaweedfs-master2",
            "seaweedfs-master3",
            "seaweedfs-volume1",
            "seaweedfs-volume2",
            "seaweedfs-volume3",
            "seaweedfs-filer",
            "seaweedfs-s3",
        ]

        for service in services:
            self.assertIn(f"  {service}:", compose_text, f"Missing SeaweedFS service: {service}")

    def test_seaweed_s3_depends_on_filer(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("  seaweedfs-s3:", compose_text)
        self.assertIn("      seaweedfs-filer:", compose_text)

    def test_airflow_and_streaming_components_coexist(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        expected_services = [
            "airflow-scheduler",
            "airflow-worker",
            "kafka1",
            "kafka2",
            "kafka3",
            "flink-jobmanager",
            "flink-taskmanager-1",
            "beam-jobserver",
            "mqtt-kafka-bridge",
            "stream-normalizer",
        ]
        for service in expected_services:
            self.assertIn(f"  {service}:", compose_text, f"Missing integration service: {service}")

    def test_core_event_topics_are_bootstrapped(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        expected_topics = [
            "raw.sensor",
            "raw.gps",
            "raw.image2d.meta",
            "raw.image3d.meta",
            "raw.video2d.meta",
            "raw.video3d.meta",
            "features.events",
            "state.latest",
            "dlq.events",
            "governance.data.products",
            "governance.access.requests",
            "governance.permission.events",
            "governance.intermediation.log",
            "governance.transfer.notices",
            "governance.research.projects",
            "governance.research.outputs",
            "governance.dataset.catalog",
            "governance.data_management_plans",
            "governance.repository.exports",
            "dataact.product.catalog",
            "dataact.user.access.requests",
            "dataact.third_party.sharing",
            "dataact.user.exports",
            "dataact.safeguards",
            "dataact.legal_basis.checks",
            "security.asset.inventory",
            "security.incident.events",
            "security.vulnerability.findings",
            "security.sbom.attestations",
            "security.patch.events",
            "resilience.backup.tests",
            "resilience.operational.risk",
            "resilience.third_party.risk",
            "compliance.scope.decisions",
            "compliance.control.assessments",
            "compliance.reporting.channels",
            "compliance.legal.dossier",
            "cra.product.lifecycle",
        ]

        for topic in expected_topics:
            self.assertIn(f"--topic {topic}", compose_text, f"Missing topic: {topic}")

    def test_images_that_import_contracts_build_from_repo_root(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("dockerfile: orchestration/Dockerfile", compose_text)
        self.assertIn("dockerfile: mqtt-kafka-bridge/Dockerfile", compose_text)
        self.assertIn("dockerfile: stream-normalizer/Dockerfile", compose_text)
        self.assertIn("http://127.0.0.1:8080/healthz", compose_text)
        self.assertIn("./dealiot_contracts:/opt/airflow/dealiot_contracts:ro", compose_text)


if __name__ == "__main__":
    unittest.main()
