from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FULL_LENGTH_SHA = re.compile(r"^[0-9a-f]{40}$")
WORKLOAD_MANIFEST_PATHS = [
    REPO_ROOT / "deploy" / "kubernetes" / "base" / "mqtt-kafka-bridge.yaml",
    REPO_ROOT
    / "deploy"
    / "kubernetes"
    / "processing"
    / "rust-normalizer"
    / "stream-normalizer.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "base" / "apicurio-registry.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "processing" / "flink" / "flink-session.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "base" / "airflow.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "base" / "management-console.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "mqtt-broker.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "kafka.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "mqtt-kafka-bridge.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "verifier.yaml",
    REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "production" / "wildfi-decoder-job.yaml",
]


class DeploymentReadinessTests(unittest.TestCase):
    def test_compose_smoke_workflow_targets_valid_seaweed_services(self) -> None:
        workflow_text = (
            REPO_ROOT / ".github" / "workflows" / "compose-deployment-test.yml"
        ).read_text(encoding="utf-8")
        expected_targets = [
            "seaweedfs-master1",
            "seaweedfs-master2",
            "seaweedfs-master3",
            "seaweedfs-volume1",
            "seaweedfs-volume2",
            "seaweedfs-volume3",
            "seaweedfs-filer",
            "seaweedfs-s3",
        ]
        for target in expected_targets:
            self.assertIn(
                target,
                workflow_text,
                f"Missing deployment target in workflow: {target}",
            )

    def test_compose_smoke_workflow_has_cleanup_and_failure_logs(self) -> None:
        workflow_text = (
            REPO_ROOT / ".github" / "workflows" / "compose-deployment-test.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Prepare local secret files", workflow_text)
        self.assertIn("secrets/postgres_superuser_password.txt", workflow_text)
        self.assertIn("secrets/seaweedfs_s3_secret_key.txt", workflow_text)
        self.assertIn("Dump compose logs on failure", workflow_text)
        self.assertIn("if: failure()", workflow_text)
        self.assertIn("if: always()", workflow_text)
        self.assertIn(
            "docker compose -f docker-compose.yml down -v --remove-orphans",
            workflow_text,
        )

    def test_ci_workflow_executes_test_layers(self) -> None:
        workflow_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("Unit test suite", workflow_text)
        self.assertIn("Integration test suite", workflow_text)
        self.assertIn("Deployment test suite", workflow_text)

    def test_codacy_workflow_normalizes_sarif_for_github(self) -> None:
        workflow_text = (REPO_ROOT / ".github" / "workflows" / "codacy.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Normalize SARIF for GitHub code scanning", workflow_text)
        self.assertIn("automationDetails", workflow_text)
        self.assertIn("del(.partialFingerprints, .ruleIndex)", workflow_text)
        self.assertIn("GitHub rejects a single SARIF upload", workflow_text)
        self.assertIn(".runs = [", workflow_text)
        self.assertIn('id: "codacy-security-scan"', workflow_text)
        self.assertIn("results.normalized.sarif", workflow_text)

    def test_e2e_workflow_runs_smoke_script_and_cleans_up(self) -> None:
        workflow_text = (REPO_ROOT / ".github" / "workflows" / "e2e-smoke.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("bash scripts/smoke-e2e.sh", workflow_text)
        self.assertIn("Dump compose logs on failure", workflow_text)
        self.assertIn('--tail="${SMOKE_DIAGNOSTIC_LOG_TAIL:-60}"', workflow_text)
        self.assertIn("flink-jobmanager flink-taskmanager-1 flink-taskmanager-2", workflow_text)
        self.assertIn(
            "mqtt-kafka-bridge apicurio-registry apicurio-init kafka1 kafka2 kafka3", workflow_text
        )
        self.assertIn(
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml down",
            workflow_text,
        )

    def test_production_deployment_workflow_tests_swarm_and_kubernetes(self) -> None:
        workflow_text = (
            REPO_ROOT / ".github" / "workflows" / "production-deployment-test.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("docker stack config -c deploy/swarm/dealiot-stack.yml", workflow_text)
        self.assertIn("docker stack deploy -c deploy/swarm/dealiot-smoke-stack.yml", workflow_text)
        self.assertIn("DEALIOT_SMOKE_BRIDGE_IMAGE: dealiot-mqtt-kafka-bridge:ci", workflow_text)
        bridge_image_env = (
            "DEALIOT_MQTT_KAFKA_BRIDGE_IMAGE: "
            "ghcr.io/smartappli/dealiot-mqtt-kafka-bridge:sha-${{ github.sha }}"
        )
        self.assertIn(
            bridge_image_env,
            workflow_text,
        )
        self.assertIn(
            "Production Swarm stack must render immutable release images only", workflow_text
        )
        self.assertIn("kubectl kustomize deploy/kubernetes/base", workflow_text)
        self.assertIn("kubectl kustomize deploy/kubernetes/overlays/production", workflow_text)
        self.assertIn("kubectl create namespace dealiot", workflow_text)
        self.assertIn("kubectl create namespace dealiot-smoke", workflow_text)
        placeholder_message = (
            "Production overlay must not render mutable tags, placeholder tags, "
            "example endpoints, or example secrets"
        )
        self.assertIn(
            placeholder_message,
            workflow_text,
        )
        self.assertIn("sha-${GITHUB_SHA}", workflow_text)
        self.assertIn("REPLACE_WITH_RELEASE_SHA", workflow_text)
        self.assertIn("example\\\\.net", workflow_text)
        self.assertIn("SET_FROM_SECRET_MANAGER", workflow_text)
        self.assertIn("kind create cluster --name dealiot-ci", workflow_text)
        self.assertIn("kubectl apply -k deploy/kubernetes/overlays/ci-smoke", workflow_text)

    def test_production_deployment_manifests_are_present_and_parseable(self) -> None:
        manifest_paths = [
            REPO_ROOT / "deploy" / "swarm" / "dealiot-stack.yml",
            REPO_ROOT / "deploy" / "swarm" / "dealiot-smoke-stack.yml",
            REPO_ROOT / "deploy" / "kubernetes" / "base" / "kustomization.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "base" / "mqtt-kafka-bridge.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "base" / "airflow.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "base" / "management-console.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "kustomization.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "serviceaccount.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "configmap.yaml",
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "ci-smoke"
            / "mqtt-kafka-bridge.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "production" / "kustomization.yaml",
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "production"
            / "network-policies.yaml",
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "production"
            / "external-dependency-contract.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "production" / "autoscaling.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "production" / "availability.yaml",
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "production"
            / "wildfi-decoder-config.yaml",
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "production"
            / "wildfi-decoder-job.yaml",
        ]

        for manifest_path in manifest_paths:
            self.assertTrue(manifest_path.is_file(), f"Missing manifest: {manifest_path}")
            documents = list(yaml.safe_load_all(manifest_path.read_text(encoding="utf-8")))
            self.assertTrue(
                any(document is not None for document in documents),
                f"Empty manifest: {manifest_path}",
            )

    def test_kubernetes_ci_smoke_overlay_is_self_contained(self) -> None:
        overlay = yaml.safe_load(
            (
                REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "kustomization.yaml"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(overlay["namespace"], "dealiot-smoke")
        self.assertEqual(
            overlay["resources"],
            [
                "namespace.yaml",
                "serviceaccount.yaml",
                "configmap.yaml",
                "mqtt-broker.yaml",
                "kafka.yaml",
                "mqtt-kafka-bridge.yaml",
                "verifier.yaml",
            ],
        )
        self.assertFalse(
            any(resource.startswith("../../base/") for resource in overlay["resources"]),
            "kubectl apply -k rejects individual files loaded from outside the overlay root",
        )
        verifier = yaml.safe_load(
            (
                REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "verifier.yaml"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(verifier["kind"], "Job")
        self.assertTrue(verifier["spec"]["template"]["spec"]["initContainers"])

    def test_kubernetes_production_overlay_uses_immutable_images(self) -> None:
        overlay = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "production"
                / "kustomization.yaml"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(overlay["namespace"], "dealiot")
        self.assertIn("network-policies.yaml", overlay["resources"])
        self.assertIn("external-dependency-contract.yaml", overlay["resources"])
        self.assertIn("autoscaling.yaml", overlay["resources"])
        self.assertIn("availability.yaml", overlay["resources"])
        self.assertIn("wildfi-decoder-config.yaml", overlay["resources"])
        self.assertIn("wildfi-decoder-job.yaml", overlay["resources"])
        self.assertIn("../../processing/flink-operator", overlay["resources"])
        self.assertEqual(
            overlay["configMapGenerator"],
            [
                {
                    "name": "dealiot-runtime-config",
                    "behavior": "replace",
                    "envs": ["runtime-config.production.example.env"],
                }
            ],
        )

        image_tags = {image["name"]: image["newTag"] for image in overlay["images"]}
        self.assertEqual(
            image_tags,
            {
                "ghcr.io/smartappli/dealiot-mqtt-kafka-bridge": "sha-REPLACE_WITH_RELEASE_SHA",
                "ghcr.io/smartappli/dealiot-stream-normalizer": "sha-REPLACE_WITH_RELEASE_SHA",
                "ghcr.io/smartappli/dealiot-management-console": "sha-REPLACE_WITH_RELEASE_SHA",
                "ghcr.io/smartappli/dealiot-flink-pyflink": "sha-REPLACE_WITH_RELEASE_SHA",
                "ghcr.io/smartappli/dealiot-orchestration": "sha-REPLACE_WITH_RELEASE_SHA",
                "ghcr.io/smartappli/dealiot-wildfi-decoder": "sha-REPLACE_WITH_RELEASE_SHA",
            },
        )
        self.assertNotIn("latest", set(image_tags.values()))

    def test_kubernetes_production_runtime_config_uses_secure_external_defaults(self) -> None:
        config_text = (
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "production"
            / "runtime-config.production.example.env"
        ).read_text(encoding="utf-8")
        runtime_config = dict(
            line.split("=", maxsplit=1)
            for line in config_text.splitlines()
            if line and not line.startswith("#")
        )

        self.assertEqual(runtime_config["MQTT_PORT"], "8883")
        self.assertIn("$share/ingestors/wildfi/#", runtime_config["MQTT_TOPICS"])
        self.assertEqual(
            runtime_config["WILDFI_DECODER_REPOSITORY"],
            "https://github.com/wildlab/WildFiDecoder",
        )
        self.assertEqual(
            runtime_config["WILDFI_FIRMWARE_REPOSITORY"],
            "https://github.com/trichl/WildFiOpenSource",
        )
        self.assertEqual(runtime_config["WILDFI_TOPIC_PREFIXES"], "wildfi,wild-fi")
        self.assertEqual(runtime_config["MQTT_USERNAME"], "dealiot_ingestor")
        self.assertEqual(runtime_config["MQTT_TLS_ENABLED"], "true")
        self.assertEqual(runtime_config["FEATURES_TOPIC"], "features.events")
        self.assertEqual(runtime_config["STATE_TOPIC"], "state.latest")
        self.assertIn("raw.sensor", runtime_config["STREAM_NORMALIZER_SOURCE_TOPICS"])
        self.assertIn("raw.gps", runtime_config["STREAM_NORMALIZER_SOURCE_TOPICS"])
        self.assertEqual(runtime_config["KAFKA_SECURITY_PROTOCOL"], "SASL_SSL")
        self.assertEqual(runtime_config["KAFKA_SASL_MECHANISM"], "SCRAM-SHA-512")
        self.assertEqual(runtime_config["KAFKA_SASL_USERNAME"], "dealiot_runtime")
        self.assertGreaterEqual(len(runtime_config["KAFKA_BOOTSTRAP_SERVERS"].split(",")), 3)
        self.assertNotIn("mqtt-broker.ingest.svc.cluster.local", config_text)
        self.assertNotIn("MQTT_PORT=1883", config_text)

    def test_kubernetes_production_overlay_sets_replica_floor(self) -> None:
        overlay = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "production"
                / "kustomization.yaml"
            ).read_text(encoding="utf-8")
        )

        replicas = {replica["name"]: replica["count"] for replica in overlay["replicas"]}
        for workload_name in (
            "mqtt-kafka-bridge",
            "apicurio-registry",
            "airflow-worker",
        ):
            self.assertGreaterEqual(replicas[workload_name], 3)
        self.assertGreaterEqual(replicas["airflow-apiserver"], 2)
        self.assertGreaterEqual(replicas["management-console"], 2)

    def test_kubernetes_production_overlay_defines_autoscaling_and_disruption_budgets(self) -> None:
        autoscaling_docs = [
            document
            for document in yaml.safe_load_all(
                (
                    REPO_ROOT
                    / "deploy"
                    / "kubernetes"
                    / "overlays"
                    / "production"
                    / "autoscaling.yaml"
                ).read_text(encoding="utf-8")
            )
            if document
        ]
        availability_docs = [
            document
            for document in yaml.safe_load_all(
                (
                    REPO_ROOT
                    / "deploy"
                    / "kubernetes"
                    / "overlays"
                    / "production"
                    / "availability.yaml"
                ).read_text(encoding="utf-8")
            )
            if document
        ]

        hpas = {document["metadata"]["name"]: document for document in autoscaling_docs}
        for workload in (
            "mqtt-kafka-bridge",
            "airflow-worker",
            "management-console",
        ):
            self.assertIn(workload, hpas)
            self.assertEqual(hpas[workload]["kind"], "HorizontalPodAutoscaler")
            hpa_spec = hpas[workload]["spec"]
            self.assertGreater(
                hpa_spec["maxReplicas"],
                hpa_spec["minReplicas"],
            )
        self.assertEqual(
            hpas["mqtt-kafka-bridge"]["spec"]["scaleTargetRef"]["kind"],
            "StatefulSet",
        )
        self.assertEqual(
            hpas["mqtt-kafka-bridge"]["spec"]["behavior"]["scaleDown"],
            {
                "stabilizationWindowSeconds": 600,
                "policies": [{"type": "Pods", "value": 1, "periodSeconds": 60}],
            },
        )
        self.assertNotIn("flink-taskmanager", hpas)

        pdbs = {document["metadata"]["name"]: document for document in availability_docs}
        self.assertEqual(pdbs["airflow-worker"]["spec"]["minAvailable"], 2)
        self.assertEqual(pdbs["airflow-apiserver"]["spec"]["minAvailable"], 1)
        self.assertEqual(pdbs["management-console"]["spec"]["minAvailable"], 1)

    def test_kubernetes_production_network_policies_default_deny_and_scope_egress(self) -> None:
        policy_path = (
            REPO_ROOT
            / "deploy"
            / "kubernetes"
            / "overlays"
            / "production"
            / "network-policies.yaml"
        )
        policy_text = policy_path.read_text(encoding="utf-8")
        policies = [policy for policy in yaml.safe_load_all(policy_text) if policy]
        policy_names = {policy["metadata"]["name"] for policy in policies}

        self.assertIn("default-deny-all", policy_names)
        self.assertIn("allow-dns-egress", policy_names)
        self.assertIn("allow-runtime-egress-to-external-dependencies", policy_names)
        self.assertIn("allow-management-console-ingress", policy_names)
        self.assertNotIn("0.0.0.0/0", policy_text)

        default_deny = next(
            policy for policy in policies if policy["metadata"]["name"] == "default-deny-all"
        )
        self.assertEqual(default_deny["spec"]["podSelector"], {})
        self.assertEqual(set(default_deny["spec"]["policyTypes"]), {"Ingress", "Egress"})

    def test_kubernetes_production_external_dependency_contract_is_explicit(self) -> None:
        contract = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "production"
                / "external-dependency-contract.yaml"
            ).read_text(encoding="utf-8")
        )
        contract_text = contract["data"]["contract.yaml"]

        for required_dependency in (
            "kafka",
            "mqtt",
            "object_storage",
            "airflow_metadata_db",
            "airflow_broker",
        ):
            self.assertIn(f"{required_dependency}:", contract_text)
        for required_secret in (
            "MQTT_PASSWORD",
            "KAFKA_SASL_PASSWORD",
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET",
            "AWS_SECRET_ACCESS_KEY",
            "AIRFLOW__CORE__FERNET_KEY",
            "AIRFLOW__API__SECRET_KEY",
        ):
            self.assertIn(required_secret, contract_text)
        self.assertIn("optional_keys:\n    - MANAGEMENT_CONSOLE_TOKEN", contract_text)
        for required_evidence_topic in (
            "governance.dataset.catalog",
            "governance.data_management_plans",
            "governance.repository.exports",
            "dataact.legal_basis.checks",
            "security.incident.events",
            "security.vulnerability.findings",
            "security.sbom.attestations",
            "resilience.backup.tests",
            "resilience.operational.risk",
            "resilience.third_party.risk",
            "compliance.scope.decisions",
            "compliance.control.assessments",
            "compliance.reporting.channels",
            "compliance.legal.dossier",
            "cra.product.lifecycle",
        ):
            self.assertIn(required_evidence_topic, contract_text)
        self.assertIn("required_security_resilience:", contract_text)
        self.assertIn("required_legal_compliance:", contract_text)
        self.assertIn("dataset_catalog: governance.dataset.catalog", contract_text)
        self.assertIn(
            "data_management_plan_register: governance.data_management_plans",
            contract_text,
        )
        self.assertIn("repository_export_log: governance.repository.exports", contract_text)
        self.assertIn("repository_publication: requires_dmp_and_legal_review", contract_text)
        self.assertIn("legal_dossier_register: compliance.legal.dossier", contract_text)
        self.assertIn("zenodo_publication: requires_legal_review_approved", contract_text)
        self.assertIn("scope_decision_register: compliance.scope.decisions", contract_text)
        self.assertIn("dora_scope: required_if_financial_entity_or_ict_provider", contract_text)
        self.assertIn("required_legal_applicability:", contract_text)
        self.assertIn("gdpr: required_for_personal_data", contract_text)
        self.assertIn("ai_act: required_before_ai_deployment", contract_text)
        self.assertIn(
            "radio_and_product_law: required_if_devices_are_placed_on_eu_market",
            contract_text,
        )

        external_contract = yaml.safe_load(contract_text)
        kafka_contract = yaml.safe_load(
            (REPO_ROOT / "deploy" / "kafka" / "topics.yaml").read_text(encoding="utf-8")
        )
        required_topics = set(external_contract["required_services"]["kafka"]["required_topics"])
        provisioned_topics = {topic["name"] for topic in kafka_contract["spec"]["topics"]}
        self.assertLessEqual(required_topics, provisioned_topics)
        principal_names = {principal["name"] for principal in kafka_contract["spec"]["principals"]}
        self.assertEqual(
            principal_names,
            {
                "dealiot-ingestion",
                "dealiot-flink",
                "dealiot-normalizer",
                "dealiot-apicurio",
                "dealiot-orchestration",
                "dealiot-operations",
            },
        )

    def test_kubernetes_runtime_manifests_wire_security_and_health_probes(self) -> None:
        bridge = next(
            document
            for document in yaml.safe_load_all(
                (REPO_ROOT / "deploy" / "kubernetes" / "base" / "mqtt-kafka-bridge.yaml").read_text(
                    encoding="utf-8"
                )
            )
            if document and document.get("kind") == "StatefulSet"
        )
        bridge_container = bridge["spec"]["template"]["spec"]["containers"][0]
        bridge_env_names = {item["name"] for item in bridge_container["env"]}
        self.assertIn("KAFKA_SASL_PASSWORD", bridge_env_names)
        self.assertIn("MQTT_CLIENT_ID", bridge_env_names)
        self.assertIn("MQTT_CLEAN_SESSION", bridge_env_names)
        self.assertEqual(bridge["spec"]["serviceName"], "mqtt-kafka-bridge")
        self.assertIn("readinessProbe", bridge_container)
        self.assertIn("livenessProbe", bridge_container)
        self.assertEqual(bridge_container["readinessProbe"]["httpGet"]["path"], "/readyz")
        self.assertEqual(bridge_container["livenessProbe"]["httpGet"]["path"], "/healthz")
        self.assertEqual(bridge_container["ports"][0]["name"], "health")

        normalizer = next(
            document
            for document in yaml.safe_load_all(
                (
                    REPO_ROOT
                    / "deploy"
                    / "kubernetes"
                    / "processing"
                    / "rust-normalizer"
                    / "stream-normalizer.yaml"
                ).read_text(encoding="utf-8")
            )
            if document and document.get("kind") == "Deployment"
        )
        normalizer_container = normalizer["spec"]["template"]["spec"]["containers"][0]
        normalizer_env_names = {item["name"] for item in normalizer_container["env"]}
        self.assertIn("KAFKA_SASL_PASSWORD", normalizer_env_names)
        self.assertIn("STREAM_NORMALIZER_HEALTH_BIND", normalizer_env_names)
        self.assertEqual(
            normalizer_container["image"],
            "ghcr.io/smartappli/dealiot-stream-normalizer:local-placeholder",
        )
        self.assertIn("readinessProbe", normalizer_container)
        self.assertIn("livenessProbe", normalizer_container)
        self.assertEqual(normalizer_container["readinessProbe"]["httpGet"]["path"], "/readyz")
        self.assertEqual(normalizer_container["livenessProbe"]["httpGet"]["path"], "/healthz")
        self.assertEqual(normalizer_container["ports"][0]["name"], "health")

        flink_deployment = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "processing"
                / "flink-operator"
                / "flink-deployment.yaml"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(flink_deployment["kind"], "FlinkDeployment")
        flink_spec = flink_deployment["spec"]
        self.assertEqual(flink_spec["job"]["upgradeMode"], "savepoint")
        self.assertEqual(flink_spec["flinkConfiguration"]["high-availability.type"], "kubernetes")
        self.assertEqual(flink_spec["flinkConfiguration"]["job.autoscaler.enabled"], "true")
        flink_container = flink_spec["podTemplate"]["spec"]["containers"][0]
        flink_env_names = {item["name"] for item in flink_container["env"]}
        self.assertIn("KAFKA_SASL_PASSWORD", flink_env_names)
        self.assertFalse(flink_container["securityContext"]["allowPrivilegeEscalation"])

        management_console = next(
            document
            for document in yaml.safe_load_all(
                (
                    REPO_ROOT / "deploy" / "kubernetes" / "base" / "management-console.yaml"
                ).read_text(encoding="utf-8")
            )
            if document and document.get("kind") == "Deployment"
        )
        console_env_names = {
            item["name"]
            for item in management_console["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        self.assertIn("MANAGEMENT_CONSOLE_TOKEN", console_env_names)
        console_container = management_console["spec"]["template"]["spec"]["containers"][0]
        self.assertIn("readinessProbe", console_container)
        self.assertIn("livenessProbe", console_container)

    def test_kubernetes_workloads_follow_restricted_pod_security(self) -> None:
        for namespace_path in (
            REPO_ROOT / "deploy" / "kubernetes" / "base" / "namespace.yaml",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "namespace.yaml",
        ):
            namespace = yaml.safe_load(namespace_path.read_text(encoding="utf-8"))
            labels = namespace["metadata"]["labels"]
            self.assertEqual(labels["pod-security.kubernetes.io/enforce"], "restricted")
            self.assertEqual(labels["pod-security.kubernetes.io/audit"], "restricted")
            self.assertEqual(labels["pod-security.kubernetes.io/warn"], "restricted")

        for manifest_path in WORKLOAD_MANIFEST_PATHS:
            documents = yaml.safe_load_all(manifest_path.read_text(encoding="utf-8"))
            for document in documents:
                if not document or document.get("kind") not in {
                    "Deployment",
                    "Job",
                    "StatefulSet",
                }:
                    continue

                pod_spec = document["spec"]["template"]["spec"]
                context = f"{manifest_path}:{document['kind']}/{document['metadata']['name']}"
                self.assertFalse(pod_spec.get("automountServiceAccountToken", True), context)
                self.assertEqual(
                    pod_spec["securityContext"]["seccompProfile"]["type"],
                    "RuntimeDefault",
                    context,
                )

                for container in pod_spec.get("initContainers", []) + pod_spec["containers"]:
                    container_context = f"{context}:{container['name']}"
                    security_context = container["securityContext"]
                    self.assertFalse(
                        security_context["allowPrivilegeEscalation"],
                        container_context,
                    )
                    self.assertIn("ALL", security_context["capabilities"]["drop"])
                    self.assertTrue(security_context["runAsNonRoot"], container_context)
                    self.assertIn("cpu", container["resources"]["requests"])
                    self.assertIn("memory", container["resources"]["requests"])
                    self.assertIn("cpu", container["resources"]["limits"])
                    self.assertIn("memory", container["resources"]["limits"])

    def test_processing_modes_are_exclusive_and_operator_managed(self) -> None:
        production = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "production"
                / "kustomization.yaml"
            ).read_text(encoding="utf-8")
        )
        rust = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "rust-normalizer"
                / "kustomization.yaml"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("../../processing/flink-operator", production["resources"])
        self.assertNotIn("../../processing/rust-normalizer", production["resources"])
        self.assertIn("../../processing/rust-normalizer", rust["resources"])
        self.assertNotIn("../../processing/flink-operator", rust["resources"])

        workflow = (
            REPO_ROOT / ".github" / "workflows" / "production-deployment-test.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("FLINK_KUBERNETES_OPERATOR_VERSION: 1.15.0", workflow)
        self.assertIn("flink-operator-repo/flink-kubernetes-operator", workflow)

        dockerfile = (REPO_ROOT / "flink" / "Dockerfile.pyflink").read_text(encoding="utf-8")
        requirements = (REPO_ROOT / "flink" / "requirements-pyflink.txt").read_text(
            encoding="utf-8"
        )
        flink_resource = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "processing"
                / "flink-operator"
                / "flink-deployment.yaml"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("apache/flink:2.2.1-scala_2.12-java17", dockerfile)
        self.assertIn("apache-flink==2.2.1", requirements)
        self.assertEqual(flink_resource["spec"]["flinkVersion"], "v2_2")
        self.assertIn("flink-python-2.2.1.jar", flink_resource["spec"]["job"]["jarURI"])

    def test_supply_chain_and_resilience_controls_are_executable(self) -> None:
        image_workflow = (
            REPO_ROOT / ".github" / "workflows" / "build-and-push-images.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("id-token: write", image_workflow)
        self.assertIn("cosign sign --yes", image_workflow)

        policy = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "components"
                / "security-platform"
                / "image-verification-policy.yaml"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(policy["kind"], "NamespacedImageValidatingPolicy")
        self.assertEqual(policy["spec"]["validationActions"], ["Deny"])

        backup_drill = (REPO_ROOT / "scripts" / "backup-restore-drill.sh").read_text(
            encoding="utf-8"
        )
        fault_drill = (REPO_ROOT / "scripts" / "fault-injection-smoke.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("pg_dump", backup_drill)
        self.assertIn("resilience.backup.tests", backup_drill)
        self.assertIn('docker kill "$bridge_container"', fault_drill)
        self.assertIn("compose stop kafka1 kafka2 kafka3", fault_drill)
        self.assertIn("compose stop kafka1", fault_drill)

    def test_ingestion_delivery_contract_is_at_least_once(self) -> None:
        bridge_source = (REPO_ROOT / "mqtt-kafka-bridge" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )
        normalizer_source = (REPO_ROOT / "stream-normalizer" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )
        swarm_stack = (REPO_ROOT / "deploy" / "swarm" / "dealiot-stack.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(".set_manual_acks(true)", bridge_source)
        self.assertIn("client.ack(&publish).await", bridge_source)
        self.assertIn('.set("enable.idempotence", "true")', bridge_source)
        self.assertIn('request.url() == "/readyz"', bridge_source)

        self.assertIn('.set("enable.auto.commit", "false")', normalizer_source)
        self.assertIn("consumer.commit_message(&message, CommitMode::Sync)", normalizer_source)
        self.assertIn('.set("enable.idempotence", "true")', normalizer_source)
        self.assertIn('request.url() == "/readyz"', normalizer_source)

        self.assertIn('MQTT_CLIENT_ID: "dealiot-bridge-{{.Task.Slot}}"', swarm_stack)
        self.assertIn('MQTT_CLEAN_SESSION: "false"', swarm_stack)

    def test_kubernetes_production_wildfi_contract_is_explicit(self) -> None:
        contract = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "production"
                / "wildfi-decoder-config.yaml"
            ).read_text(encoding="utf-8")
        )
        ingest_contract = contract["data"]["ingest-contract.yaml"]
        decoder_config = contract["data"]["WildFiDecoderConfig.txt"]

        self.assertIn("https://github.com/wildlab/WildFiDecoder", ingest_contract)
        self.assertIn("https://github.com/trichl/WildFiOpenSource", ingest_contract)
        self.assertIn("WildFiDecoderMultiThreaded", ingest_contract)
        self.assertIn("b4002eb9a6111de140b95e5a35c3f3bd552d51be", ingest_contract)
        self.assertIn("$share/ingestors/wildfi/#", ingest_contract)
        self.assertIn("raw.gps", ingest_contract)
        self.assertIn("raw.sensor", ingest_contract)
        self.assertIn("native_binary_policy", ingest_contract)
        self.assertIn("wildfi-decoder", ingest_contract)
        self.assertIn("0.00024414062", decoder_config)

    def test_kubernetes_production_wildfi_decoder_job_is_manual_and_bounded(self) -> None:
        job = yaml.safe_load(
            (
                REPO_ROOT
                / "deploy"
                / "kubernetes"
                / "overlays"
                / "production"
                / "wildfi-decoder-job.yaml"
            ).read_text(encoding="utf-8")
        )

        container = job["spec"]["template"]["spec"]["containers"][0]
        env_names = {item["name"] for item in container["env"]}
        volumes = {volume["name"]: volume for volume in job["spec"]["template"]["spec"]["volumes"]}

        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(
            container["image"],
            "ghcr.io/smartappli/dealiot-wildfi-decoder:local-placeholder",
        )
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertIn("WILDFI_DECODER_MODE", env_names)
        self.assertIn("WILDFI_IMU_FREQUENCY", env_names)
        self.assertNotIn("JAVA_TOOL_OPTIONS", env_names)
        self.assertEqual(
            volumes["workdir"]["persistentVolumeClaim"]["claimName"],
            "wildfi-decoder-workdir",
        )
        self.assertEqual(volumes["tmp"]["emptyDir"], {})

    def test_image_build_workflow_publishes_supply_chain_metadata(self) -> None:
        workflow_text = (
            REPO_ROOT / ".github" / "workflows" / "build-and-push-images.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("--sbom=true", workflow_text)
        self.assertIn("--provenance=true", workflow_text)
        self.assertIn("org.opencontainers.image.revision", workflow_text)
        self.assertIn("sha-${GITHUB_SHA}", workflow_text)
        self.assertNotIn(':latest"', workflow_text)
        self.assertIn("image_name: management-console", workflow_text)
        self.assertIn("image_name: wildfi-decoder", workflow_text)
        self.assertIn("WILDFI_DECODER_GIT_REF", workflow_text)

    def test_security_workflows_cover_static_and_dependency_scanning(self) -> None:
        bandit_text = (REPO_ROOT / ".github" / "workflows" / "bandit.yml").read_text(
            encoding="utf-8"
        )
        ossar_text = (REPO_ROOT / ".github" / "workflows" / "ossar.yml").read_text(encoding="utf-8")
        osv_text = (REPO_ROOT / ".github" / "workflows" / "osv-scanner.yml").read_text(
            encoding="utf-8"
        )
        codeql_text = (REPO_ROOT / ".github" / "workflows" / "codeql.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("shundor/python-bandit-scan", bandit_text)
        self.assertIn(
            'excluded_paths: ".git,.venv,build,dist,grafana,secrets,tests"',
            bandit_text,
        )
        self.assertIn("security-events: write", bandit_text)
        self.assertIn("github/ossar-action", ossar_text)
        self.assertIn("github/codeql-action/upload-sarif", ossar_text)
        self.assertIn("google/osv-scanner-action/.github/workflows", osv_text)
        self.assertIn("--skip-git", osv_text)
        self.assertIn("github/codeql-action/init", codeql_text)
        self.assertIn("github/codeql-action/analyze", codeql_text)

    def test_quality_workflows_run_expected_validation_tools(self) -> None:
        shellcheck_text = (REPO_ROOT / ".github" / "workflows" / "shellcheck.yml").read_text(
            encoding="utf-8"
        )
        sonarqube_text = (REPO_ROOT / ".github" / "workflows" / "sonarqube.yml").read_text(
            encoding="utf-8"
        )
        renovate_text = (REPO_ROOT / ".github" / "workflows" / "renovate.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("find ./scripts ./flink/jobs ./beam", shellcheck_text)
        self.assertIn("shellcheck -S warning", shellcheck_text)
        self.assertIn("pytest --cov=. --cov-report=xml --cov-report=term-missing", sonarqube_text)
        self.assertIn("--cov-fail-under=90", sonarqube_text)
        self.assertIn("SonarSource/sonarqube-scan-action", sonarqube_text)
        self.assertIn("python -m json.tool renovate.json", renovate_text)
        self.assertIn("renovatebot/github-action", renovate_text)

    def test_github_actions_are_pinned_to_full_length_commit_sha(self) -> None:
        workflow_paths = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

        for workflow_path in workflow_paths:
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
            for job in workflow.get("jobs", {}).values():
                job_uses = job.get("uses")
                if job_uses:
                    job_action_ref = job_uses.rsplit("@", maxsplit=1)[-1]
                    self.assertRegex(
                        job_action_ref,
                        FULL_LENGTH_SHA,
                        f"{workflow_path.name} uses an unpinned reusable workflow: {job_uses}",
                    )
                for step in job.get("steps", []):
                    uses = step.get("uses")
                    if not uses:
                        continue
                    action_ref = uses.rsplit("@", maxsplit=1)[-1]
                    self.assertRegex(
                        action_ref,
                        FULL_LENGTH_SHA,
                        f"{workflow_path.name} uses an unpinned action: {uses}",
                    )

    def test_production_images_package_runtime_code(self) -> None:
        beam_jobserver_dockerfile = (REPO_ROOT / "beam" / "Dockerfile.jobserver").read_text(
            encoding="utf-8"
        )
        beam_runtime_dockerfile = (REPO_ROOT / "beam" / "Dockerfile.python-runtime").read_text(
            encoding="utf-8"
        )
        orchestration_dockerfile = (REPO_ROOT / "orchestration" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        management_console_dockerfile = (REPO_ROOT / "management-console" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        flink_dockerfile = (REPO_ROOT / "flink" / "Dockerfile.pyflink").read_text(encoding="utf-8")
        bridge_dockerfile = (REPO_ROOT / "mqtt-kafka-bridge" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        normalizer_dockerfile = (REPO_ROOT / "stream-normalizer" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        bridge_source = (REPO_ROOT / "mqtt-kafka-bridge" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )

        self.assertIn("--chown=root:root --chmod=0444 /out/jars", beam_jobserver_dockerfile)
        self.assertIn(
            "--chown=root:root --chmod=0555 /out/flink-job-server.sh",
            beam_jobserver_dockerfile,
        )
        self.assertIn(
            "COPY --chown=root:root --chmod=0555 dealiot_contracts",
            beam_runtime_dockerfile,
        )
        self.assertIn("COPY --chown=root:root --chmod=0555 pipelines", beam_runtime_dockerfile)
        self.assertIn("FROM rust:", bridge_dockerfile)
        self.assertIn("cargo build --release", bridge_dockerfile)
        self.assertIn("ca-certificates libsasl2-2 wget", bridge_dockerfile)
        self.assertIn(
            "COPY --from=builder --chown=root:root --chmod=0555",
            bridge_dockerfile,
        )
        self.assertIn("FROM rust:", normalizer_dockerfile)
        self.assertIn(
            "cargo build --release --locked -p dealiot-stream-normalizer",
            normalizer_dockerfile,
        )
        self.assertIn("dealiot-stream-normalizer", normalizer_dockerfile)
        self.assertIn("ca-certificates libsasl2-2 wget", normalizer_dockerfile)
        self.assertIn(
            "COPY --chown=root:0 --chmod=0444 orchestration/requirements.txt",
            orchestration_dockerfile,
        )
        self.assertIn("COPY --chown=root:0 --chmod=0555 airflow/dags", orchestration_dockerfile)
        self.assertIn(
            "COPY --chown=root:0 --chmod=0555 pipelines /opt/pipelines",
            orchestration_dockerfile,
        )
        self.assertIn("COPY --chown=root:root --chmod=0555 ./flink/jobs", flink_dockerfile)
        self.assertIn("COPY --chown=root:root --chmod=0555 ./pipelines", flink_dockerfile)
        self.assertIn("flink/log4j-console.properties", flink_dockerfile)
        self.assertIn("flink-sql-connector-kafka", flink_dockerfile)
        self.assertIn("FLINK_KAFKA_CONNECTOR_VERSION=5.0.0-2.2", flink_dockerfile)
        self.assertNotIn("FLINK_CONNECTOR_BASE_VERSION", flink_dockerfile)
        self.assertIn("jdk_only_exports", flink_dockerfile)
        self.assertIn("env_or_secret_file", bridge_source)
        self.assertIn("apply_kafka_security_config", bridge_source)
        self.assertIn("configure_mqtt_tls", bridge_source)
        self.assertIn("start_health_server", bridge_source)
        self.assertIn(
            "COPY --chown=root:root --chmod=0555 management-console/management_console",
            management_console_dockerfile,
        )
        self.assertIn("USER appuser", management_console_dockerfile)

    def test_flink_runtime_logs_suppress_kafka_client_info_noise(self) -> None:
        log4j_config = (REPO_ROOT / "flink" / "log4j-console.properties").read_text(
            encoding="utf-8"
        )

        self.assertIn("logger.kafka.name = org.apache.kafka", log4j_config)
        self.assertIn("logger.kafka.level = WARN", log4j_config)
        self.assertIn(
            "logger.kafkaShaded.name = org.apache.flink.kafka.shaded.org.apache.kafka",
            log4j_config,
        )
        self.assertIn("logger.kafkaShaded.level = WARN", log4j_config)

    def test_local_flink_services_use_seaweed_s3_secret_files(self) -> None:
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        dockerfile = (REPO_ROOT / "flink" / "Dockerfile.pyflink").read_text(encoding="utf-8")
        entrypoint = (REPO_ROOT / "flink" / "docker-entrypoint.sh").read_text(encoding="utf-8")

        for service_name in (
            "flink-jobmanager",
            "flink-taskmanager-1",
            "flink-taskmanager-2",
            "flink-cli",
        ):
            secrets = {
                item["source"]: item["target"]
                for item in compose["services"][service_name]["secrets"]
            }
            self.assertEqual(secrets["seaweedfs_s3_access_key"], "seaweedfs_s3_access_key")
            self.assertEqual(secrets["seaweedfs_s3_secret_key"], "seaweedfs_s3_secret_key")

        self.assertIn(
            "COPY --chown=root:root --chmod=0555 ./flink/docker-entrypoint.sh",
            dockerfile,
        )
        self.assertIn('ENTRYPOINT ["/opt/flink/bin/dealiot-flink-entrypoint.sh"]', dockerfile)
        self.assertIn("/run/secrets/seaweedfs_s3_access_key", entrypoint)
        self.assertIn("/run/secrets/seaweedfs_s3_secret_key", entrypoint)
        self.assertIn("s3\\.access-key", entrypoint)
        self.assertIn("exec /docker-entrypoint.sh", entrypoint)

    def test_local_flink_services_have_explicit_network_addresses(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        dev_text = (REPO_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")

        self.assertIn("jobmanager.bind-host: 0.0.0.0", compose_text)
        self.assertIn("rest.bind-address: 0.0.0.0", compose_text)
        self.assertIn("taskmanager.host: flink-taskmanager-1", compose_text)
        self.assertIn("taskmanager.host: flink-taskmanager-2", compose_text)
        self.assertIn("taskmanager.bind-host: 0.0.0.0", compose_text)
        self.assertIn("jobmanager.bind-host: 0.0.0.0", dev_text)
        self.assertIn("rest.bind-address: 0.0.0.0", dev_text)

    def test_haproxy_uses_patroni_options_health_checks(self) -> None:
        haproxy_cfg = (REPO_ROOT / "haproxy" / "haproxy.cfg").read_text(encoding="utf-8")

        self.assertIn("option httpchk", haproxy_cfg)
        self.assertIn("http-check connect port 8008", haproxy_cfg)
        self.assertIn(
            "http-check send meth OPTIONS uri /primary ver HTTP/1.1 hdr Host patroni",
            haproxy_cfg,
        )
        self.assertIn(
            "http-check send meth OPTIONS uri /replica ver HTTP/1.1 hdr Host patroni",
            haproxy_cfg,
        )
        self.assertNotIn("meth GET uri /primary", haproxy_cfg)
        self.assertNotIn("meth GET uri /replica", haproxy_cfg)

    def test_seaweedfs_filer_healthcheck_uses_get_request(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("wget -q -O - http://127.0.0.1:8888/ >/dev/null 2>&1", compose_text)
        self.assertNotIn("--spider http://127.0.0.1:8888/", compose_text)

    def test_seaweedfs_postgres_bootstrap_quotes_secret_with_psql(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn('-v seaweedfs_pg_password="$$SEAWEEDFS_PG_PASSWORD"', compose_text)
        self.assertIn(":'seaweedfs_pg_password'", compose_text)
        self.assertIn("CREATE DATABASE seaweedfs OWNER seaweedfs_filer", compose_text)
        self.assertNotIn(
            "CREATE ROLE seaweedfs_filer LOGIN PASSWORD '$$SEAWEEDFS_PG_PASSWORD'",
            compose_text,
        )


if __name__ == "__main__":
    unittest.main()
