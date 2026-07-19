from __future__ import annotations

import ast
import json
import subprocess
import unicodedata
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class RepositoryUnitTests(unittest.TestCase):
    def test_critical_repository_files_exist(self) -> None:
        required_files = [
            REPO_ROOT / "docker-compose.yml",
            REPO_ROOT / "docker-compose.dev.yml",
            REPO_ROOT / "docker-compose.staging.yml",
            REPO_ROOT / "docker-compose.prod.yml",
            REPO_ROOT / ".dockerignore",
            REPO_ROOT / "README.md",
            REPO_ROOT / "CONTRIBUTING.md",
            REPO_ROOT / "CODE_OF_CONDUCT.md",
            REPO_ROOT / "SECURITY.md",
            REPO_ROOT / "SUPPORT.md",
            REPO_ROOT / "ROADMAP.md",
            REPO_ROOT / "ADOPTERS.md",
            REPO_ROOT / "CITATION.cff",
            REPO_ROOT / "scripts" / "smoke-e2e.sh",
            REPO_ROOT / "docs" / "community" / "README.md",
            REPO_ROOT / "docs" / "community" / "adoption-playbook.md",
            REPO_ROOT / "docs" / "community" / "demo-pilot-playbook.md",
            REPO_ROOT / "docs" / "community" / "integration-partner-guide.md",
            REPO_ROOT / "docs" / "community" / "validation-scorecard.md",
            REPO_ROOT / "docs" / "community" / "adopter-story-template.md",
            REPO_ROOT / "docs" / "runbooks" / "operations.md",
            REPO_ROOT / "docs" / "runbooks" / "backup-restore.md",
            REPO_ROOT / "docs" / "runbooks" / "security-hardening.md",
            REPO_ROOT / "docs" / "runbooks" / "security-resilience-compliance.md",
            REPO_ROOT / "docs" / "runbooks" / "legal-applicability.md",
            REPO_ROOT / "docs" / "runbooks" / "data-governance-act.md",
            REPO_ROOT / "docs" / "runbooks" / "data-act.md",
            REPO_ROOT / "docs" / "runbooks" / "data-management-plan.md",
            REPO_ROOT / "docs" / "runbooks" / "zenodo-export.md",
            REPO_ROOT / "docs" / "runbooks" / "openaire-export.md",
            REPO_ROOT / "docs" / "runbooks" / "wildfi-ingestion.md",
            REPO_ROOT / "docs" / "architecture" / "scalable-production-audit.md",
            REPO_ROOT / "docs" / "wiki" / "Home.md",
            REPO_ROOT / "docs" / "wiki" / "Architecture.md",
            REPO_ROOT / "docs" / "wiki" / "Production-Deployment.md",
            REPO_ROOT / "docs" / "wiki" / "Configuration-Reference.md",
            REPO_ROOT / "docs" / "wiki" / "Security-and-Compliance.md",
            REPO_ROOT / "docs" / "wiki" / "Operations-and-Scaling.md",
            REPO_ROOT / "docs" / "wiki" / "CI-CD-and-Release.md",
            REPO_ROOT / "docs" / "wiki" / "Runbook-Index.md",
            REPO_ROOT / "docs" / "compliance" / "legal-compliance-dossier.md",
            REPO_ROOT / "docs" / "compliance" / "legal-finalization-report.md",
            REPO_ROOT / "docs" / "compliance" / "legal-readiness-review.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "ropa-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "dpia-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "privacy-notice-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "data-act-notice-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "data-sharing-agreement-checklist.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "processor-dpa-checklist.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "data-subject-rights-procedure.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "dga-role-notification-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "scope-decision-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "reporting-channel-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "cra-conformity-file-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "ai-system-inventory-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "eprivacy-assessment-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "retention-schedule-template.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "incident-notification-playbook.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "zenodo-publication-approval.md",
            REPO_ROOT / "docs" / "compliance" / "templates" / "openaire-discovery-approval.md",
            REPO_ROOT / ".github" / "workflows" / "ci.yml",
            REPO_ROOT / ".github" / "dependabot.yml",
            REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "demo_request.yml",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "adopter_story.yml",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "documentation.yml",
            REPO_ROOT / ".github" / "workflows" / "e2e-smoke.yml",
            REPO_ROOT / "bandit.yaml",
            REPO_ROOT / "wildfi-decoder" / "Dockerfile",
            REPO_ROOT / "wildfi-decoder-runner" / "src" / "lib.rs",
            REPO_ROOT / "wildfi-decoder-runner" / "src" / "main.rs",
            REPO_ROOT / "management-console" / "Dockerfile",
            REPO_ROOT / "management-console" / "management_console" / "app.py",
            REPO_ROOT / "management-console" / "management_console" / "openaire.py",
        ]

        for file_path in required_files:
            self.assertTrue(file_path.is_file(), f"Missing file: {file_path}")

    def test_readme_is_professional_project_entrypoint(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        for required_heading in (
            "# DEALIoT",
            "## Platform Scope",
            "## Architecture",
            "## Local Development",
            "## Production Deployment",
            "## Runtime Security",
            "## Testing And Quality Gates",
            "## Operations And Runbooks",
            "## Website And Adoption",
        ):
            self.assertIn(required_heading, readme)

        for forbidden_fragment in (
            "Recent reliability hardening:",
            "MQTTâ",
            "Recommended next steps",
            "Included artifacts in this finalized package",
        ):
            self.assertNotIn(forbidden_fragment, readme)

        self.assertIn("Kubernetes is the primary production target", readme)
        self.assertIn("The GitHub Wiki contains the production architecture handbook", readme)
        self.assertIn("docs/community/adoption-playbook.md", readme)
        self.assertIn("CONTRIBUTING.md", readme)

    def test_versioned_wiki_source_covers_production_operations(self) -> None:
        wiki_dir = REPO_ROOT / "docs" / "wiki"
        wiki_text = "\n".join(path.read_text(encoding="utf-8") for path in wiki_dir.glob("*.md"))

        for required_fragment in (
            "Production Deployment",
            "Configuration Reference",
            "Security And Compliance",
            "Operations And Scaling",
            "CI/CD And Release",
            "Pod Security `restricted`",
            "Kafka `SASL_SSL`",
            "MQTT TLS",
            "NetworkPolicies",
            "HPA",
            "PDB",
        ):
            self.assertIn(required_fragment, wiki_text)

    def test_apicurio_bootstrap_json_payloads_are_strings(self) -> None:
        bootstrap_files = [
            REPO_ROOT / "apicurio" / "bootstrap" / "dlq.events.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "raw.sensor.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "media.object.events.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.data.products.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.permission.events.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.intermediation.log.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.research.projects.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.research.outputs.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.dataset.catalog.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.data_management_plans.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "governance.repository.exports.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "dataact.product.catalog.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "dataact.user.access.requests.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "dataact.third_party.sharing.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "dataact.user.exports.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "dataact.safeguards.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "dataact.legal_basis.checks.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "security.asset.inventory.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "security.incident.events.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "security.vulnerability.findings.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "security.sbom.attestations.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "security.patch.events.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "resilience.backup.tests.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "resilience.operational.risk.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "resilience.third_party.risk.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "compliance.scope.decisions.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "compliance.control.assessments.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "compliance.reporting.channels.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "compliance.legal.dossier.json",
            REPO_ROOT / "apicurio" / "bootstrap" / "cra.product.lifecycle.json",
        ]

        for file_path in bootstrap_files:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            content = payload["firstVersion"]["content"]["content"]
            self.assertIsInstance(content, str, f"Invalid embedded schema content in {file_path}")
            self.assertGreater(
                len(content), 20, f"Embedded schema content too short in {file_path}"
            )

    def test_compose_uses_canonical_state_latest_topic(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        flink_text = (REPO_ROOT / "flink" / "jobs" / "streaming_minimal.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("--topic state.latest", compose_text)
        self.assertIn('STATE_TOPIC: "state.latest"', compose_text)
        self.assertIn('FEATURES_TOPIC: "features.events"', compose_text)
        self.assertIn('profiles: ["rust-normalizer"]', compose_text)
        self.assertIn(
            'env_or_default("STATE_TOPIC", "state.latest")',
            flink_text,
        )
        self.assertNotIn("state-latest", compose_text)

    def test_apicurio_init_posts_bootstrap_payloads_directly(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn('--data @"$$file"', compose_text)
        self.assertNotIn("content_escaped", compose_text)
        self.assertIn('"$$base/groups/$$group/artifacts/$$artifact"', compose_text)
        self.assertIn('ready_url="http://apicurio-registry:9000/health/ready"', compose_text)
        self.assertIn("ready_attempts=120", compose_text)
        self.assertIn("curl --connect-timeout 5 --max-time 10 -fsS", compose_text)
        self.assertIn("curl --connect-timeout 5 --max-time 30 -fsS -X POST", compose_text)
        self.assertNotIn("apicurio-registry:8080/health/ready", compose_text)
        self.assertIn("post_artifact platform dlq.events /bootstrap/dlq.events.json", compose_text)
        self.assertIn(
            "post_artifact governance governance.data.products "
            "/bootstrap/governance.data.products.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact governance governance.intermediation.log "
            "/bootstrap/governance.intermediation.log.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact governance governance.research.projects "
            "/bootstrap/governance.research.projects.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact governance governance.dataset.catalog "
            "/bootstrap/governance.dataset.catalog.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact governance governance.data_management_plans "
            "/bootstrap/governance.data_management_plans.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact governance governance.repository.exports "
            "/bootstrap/governance.repository.exports.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact dataact dataact.product.catalog /bootstrap/dataact.product.catalog.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact dataact dataact.third_party.sharing "
            "/bootstrap/dataact.third_party.sharing.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact dataact dataact.legal_basis.checks "
            "/bootstrap/dataact.legal_basis.checks.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact security security.incident.events "
            "/bootstrap/security.incident.events.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact security security.sbom.attestations "
            "/bootstrap/security.sbom.attestations.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact resilience resilience.operational.risk "
            "/bootstrap/resilience.operational.risk.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact compliance compliance.scope.decisions "
            "/bootstrap/compliance.scope.decisions.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact compliance compliance.reporting.channels "
            "/bootstrap/compliance.reporting.channels.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact compliance compliance.legal.dossier "
            "/bootstrap/compliance.legal.dossier.json",
            compose_text,
        )
        self.assertIn(
            "post_artifact cra cra.product.lifecycle /bootstrap/cra.product.lifecycle.json",
            compose_text,
        )

    def test_local_secrets_are_excluded_from_git_and_docker_contexts(self) -> None:
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")

        for ignored_path in [".env", ".env.*", ".idea/", ".mypy_cache/", "secrets/*"]:
            self.assertIn(ignored_path, gitignore)

        self.assertIn("!secrets/.gitkeep", gitignore)

        for ignored_path in [".env", ".env.*", ".idea", ".mypy_cache", "secrets/"]:
            self.assertIn(ignored_path, dockerignore)

        tracked_sensitive_paths = subprocess.run(
            ["git", "ls-files", ".env", ".env.*", ".idea", "secrets"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        allowed_sensitive_paths = {".env.example", "secrets/.gitkeep"}

        for path in tracked_sensitive_paths:
            self.assertIn(path, allowed_sensitive_paths)

    def test_compose_does_not_define_sensitive_password_fallbacks(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        forbidden_fragments = [
            "change-this-password",
            "change-this-cookie",
            "AIRFLOW_ADMIN_PASSWORD:-",
            "AIRFLOW_DB_PASSWORD:-",
            "GRAFANA_ADMIN_PASSWORD:-",
            "VERNEMQ_ADMIN_PASSWORD:-",
        ]

        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, compose_text)

    def test_base_compose_does_not_publish_host_ports(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertNotIn("\n    ports:\n", compose_text)

    def test_compose_and_patroni_avoid_broad_privilege_hotspots(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        patroni_templates = sorted((REPO_ROOT / "patroni").glob("pg*.yml.tmpl"))

        self.assertNotIn("privileged: true", compose_text)
        self.assertIn("no-new-privileges:true", compose_text)
        for template_path in patroni_templates:
            template_text = template_path.read_text(encoding="utf-8")
            self.assertNotIn("0.0.0.0/0", template_text)
            self.assertIn("samenet scram-sha-256", template_text)

    def test_dev_overlay_contains_local_ports_and_prod_exposes_only_edge(self) -> None:
        dev_text = (REPO_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
        prod_text = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

        for port in [
            '"8088:8080"',
            '"19092:19092"',
            '"3000:3000"',
            '"1883:1883"',
            '"8090:8080"',
        ]:
            self.assertIn(port, dev_text)

        self.assertIn('"80:80"', prod_text)
        self.assertIn('"443:443"', prod_text)
        self.assertNotIn('"8088:8080"', prod_text)
        self.assertNotIn('"8090:8080"', prod_text)
        self.assertNotIn('"19092:19092"', prod_text)

    def test_e2e_smoke_script_checks_runtime_contracts(self) -> None:
        script_text = (REPO_ROOT / "scripts" / "smoke-e2e.sh").read_text(encoding="utf-8")
        flink_job_text = (REPO_ROOT / "flink" / "jobs" / "streaming_minimal.py").read_text(
            encoding="utf-8"
        )

        for expected in [
            "raw.sensor",
            "dlq.events",
            "features.events",
            "state.latest",
            "smoke_run_id=",
            "FLINK_CONSUMER_GROUP",
            "Core event-flow services failed to become ready.",
            "SMOKE_COMPOSE_OUTPUT_TAIL",
            "wait_for_core_event_flow_services",
            "compose_service_running",
            'compose ps -a -q "$service"',
            "wait_for_compose_service kafka-init completed",
            "wait_for_compose_service seaweedfs-init completed",
            "wait_for_compose_service flink-jobmanager healthy",
            "SMOKE_COMPOSE_READY_POLL_SECONDS",
            "SMOKE_COMPOSE_READY_ATTEMPTS",
            "wait_for_flink_job_running",
            "wait_for_flink_taskmanagers",
            "dump_smoke_diagnostics",
            "flink-cli sh /opt/flink/usrlib/run-streaming-minimal.sh",
            "SMOKE_FLINK_EXPECTED_TASKMANAGERS",
            "SMOKE_FLINK_TASKMANAGER_WAIT_ATTEMPTS",
            "SMOKE_FLINK_REST_HOST",
            "SMOKE_FLINK_SUBMIT_OUTPUT_TAIL",
            "SMOKE_DIAGNOSTIC_LOG_TAIL",
            "SMOKE_KAFKA_DIAGNOSTIC_TOPICS",
            "emit_smoke_error",
            "::error title=E2E smoke",
            "GITHUB_STEP_SUMMARY",
            "http.client.HTTPConnection",
            "apicurio-registry:8080",
            "check_apicurio_artifact",
            "apicurio-registry apicurio-init kafka1 kafka2 kafka3",
            "dump_kafka_topic_state",
            "dump_flink_job_diagnostics",
            "dump_flink_rest_path",
            "/jobs/${flink_job_id}/exceptions",
            "/jobs/${flink_job_id}/checkpoints",
            "kafka-get-offsets.sh",
            "groups/${group}/artifacts/${artifact}",
            "require_command timeout",
            "compose_with_timeout",
            "SMOKE_FLINK_SUBMIT_TIMEOUT_SECONDS",
            "Flink job submission failed or timed out with status ${submit_status}",
            "Flink submit output (last ${SMOKE_FLINK_SUBMIT_OUTPUT_TAIL} lines)",
            "SMOKE_MQTT_PUBLISH_TIMEOUT_SECONDS",
            "wait_for_publish(timeout=publish_timeout)",
            "grep -F -m 1",
            "cancel --jobmanager flink-jobmanager:8081",
            '--tail="$SMOKE_DIAGNOSTIC_LOG_TAIL"',
            "mktemp",
            "Docker compose up output (last ${SMOKE_COMPOSE_OUTPUT_TAIL} lines)",
            "Flink JobManager is not running; skipping Flink job list",
            "Kafka service kafka1 is not running; skipping topic state",
            "run --no-deps --rm --entrypoint",
        ]:
            self.assertIn(expected, script_text)
        self.assertIn(" up -d --build \\", script_text)
        self.assertNotIn("--quiet-pull", script_text)
        self.assertNotIn("--quiet-build", script_text)
        self.assertNotIn(" --wait \\", script_text)
        self.assertNotIn("e2e-sensor-001", script_text)
        self.assertNotIn("e2e-camera-001", script_text)
        self.assertNotIn("http://flink-jobmanager", script_text)
        self.assertIn(
            "from pyflink.datastream.connectors.base import DeliveryGuarantee",
            flink_job_text,
        )

    def test_wildfi_ingestion_is_configured(self) -> None:
        bridge_source = (REPO_ROOT / "mqtt-kafka-bridge" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        runbook_text = (REPO_ROOT / "docs" / "runbooks" / "wildfi-ingestion.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("$share/ingestors/wildfi/#", compose_text)
        self.assertIn("WILDFI_TOPIC_PREFIXES", bridge_source)
        self.assertIn("WildFiDecoder", runbook_text)
        self.assertIn("WildFiOpenSource", runbook_text)
        self.assertIn("raw.gps", runbook_text)
        self.assertIn("raw.sensor", runbook_text)

    def test_wildfi_decoder_image_is_pinned_and_wrapped_for_batch_decoding(self) -> None:
        dockerfile = (REPO_ROOT / "wildfi-decoder" / "Dockerfile").read_text(encoding="utf-8")
        runner = (REPO_ROOT / "wildfi-decoder-runner" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        runner_main = (REPO_ROOT / "wildfi-decoder-runner" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )

        self.assertIn("FROM rust:", dockerfile)
        self.assertIn("https://github.com/wildlab/WildFiDecoder.git", dockerfile)
        self.assertIn("b4002eb9a6111de140b95e5a35c3f3bd552d51be", dockerfile)
        self.assertIn('test "$(git rev-parse HEAD)" = "${WILDFI_DECODER_GIT_REF}"', dockerfile)
        self.assertIn("WildFiDecoderStandalone.jar", dockerfile)
        self.assertIn("cargo build --release --locked -p dealiot-wildfi-decoder-runner", dockerfile)
        self.assertIn("COPY --from=runner-builder", dockerfile)
        self.assertIn("WILDFI_DECODER_RAW_INPUT", runner)
        self.assertIn("WILDFI_DECODER_MODE", runner)
        self.assertIn('Command::new("java")', runner_main)
        self.assertIn('env_remove("JAVA_TOOL_OPTIONS")', runner_main)

    def test_ci_assets_do_not_contain_static_placeholder_secrets(self) -> None:
        scanned_paths = [
            *sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")),
            REPO_ROOT / ".env.example",
            REPO_ROOT / "deploy" / "kubernetes" / "overlays" / "ci-smoke" / "kustomization.yaml",
        ]
        forbidden_fragments = [
            "change-me",
            "replace-with",
            "replace-me",
            "ci-api-secret",
            "ci-jwt-secret",
            "ci-access-key",
            "ci-fernet-key",
            "ci-mqtt-password",
            "ci-secret-key",
            "ci-airflow-admin-password",
            "ci-airflow-db-password",
            "ci-vernemq-admin-password",
            "ci-grafana-admin-password",
        ]

        for path in scanned_paths:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, text, f"{path} contains {fragment}")

    def test_coverage_threshold_is_at_least_90_percent(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "sonarqube.yml").read_text(
            encoding="utf-8"
        )
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("--cov-fail-under=90", workflow)
        self.assertIn("fail_under = 90", pyproject)

    def test_codacy_excludes_known_scanner_false_positives(self) -> None:
        codacy_config = (REPO_ROOT / ".codacy.yaml").read_text(encoding="utf-8")

        self.assertTrue(codacy_config.startswith("---\n"))
        self.assertIn("opengrep:", codacy_config)
        self.assertIn("bandit:", codacy_config)
        self.assertIn("pylintpython3:", codacy_config)
        self.assertIn("management-console/static/app.js", codacy_config)
        self.assertIn("management-console/management_console/app.py", codacy_config)
        self.assertIn(".github/ISSUE_TEMPLATE/*.yml", codacy_config)
        self.assertIn(".github/workflows/sonarqube.yml", codacy_config)

    def test_management_console_frontend_avoids_unsafe_dom_sinks(self) -> None:
        app_js = (REPO_ROOT / "management-console" / "static" / "app.js").read_text(
            encoding="utf-8"
        )

        for forbidden in ["innerHTML", "outerHTML", "document.write", "dataset["]:
            self.assertNotIn(forbidden, app_js)
        self.assertIn("dataAttributeName", app_js)
        self.assertIn('publicBasePath = "/dealiot"', app_js)
        self.assertIn("fetch(`${publicBasePath}/api/architecture`", app_js)
        self.assertIn("fetch(`${publicBasePath}/api/health`", app_js)
        self.assertNotIn("fetch(endpoint", app_js)

    def test_public_website_is_externalized_to_dealwebsite(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        dependabot = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        codeowners = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertFalse((REPO_ROOT / "website").exists())
        self.assertFalse((REPO_ROOT / ".github" / "workflows" / "website-pages.yml").exists())
        self.assertFalse((REPO_ROOT / "scripts" / "localize_website.py").exists())
        self.assertIn("https://smartappli.io/", readme)
        self.assertIn("https://github.com/Smartappli/DEALWebsite", readme)
        self.assertIn("Website source repository", readme)
        self.assertNotIn('directory: "/website"', dependabot)
        self.assertNotIn("/website/", codeowners)
        self.assertNotIn("website/node_modules/", gitignore)

    def test_repository_has_adoption_assets(self) -> None:
        adoption_playbook = (REPO_ROOT / "docs" / "community" / "adoption-playbook.md").read_text(
            encoding="utf-8"
        )
        popularity_playbook = (
            REPO_ROOT / "docs" / "community" / "architecture-popularity-playbook.md"
        ).read_text(encoding="utf-8")
        star_growth_plan = (
            REPO_ROOT / "docs" / "community" / "github-star-growth-plan.md"
        ).read_text(encoding="utf-8")
        use_case_catalog = (REPO_ROOT / "docs" / "community" / "use-case-catalog.md").read_text(
            encoding="utf-8"
        )
        quick_evaluation_path = (
            REPO_ROOT / "docs" / "community" / "quick-evaluation-path.md"
        ).read_text(encoding="utf-8")
        comparison_guide = (
            REPO_ROOT / "docs" / "community" / "architecture-comparison-guide.md"
        ).read_text(encoding="utf-8")
        champion_kit = (REPO_ROOT / "docs" / "community" / "internal-champion-kit.md").read_text(
            encoding="utf-8"
        )
        public_launch_kit = (REPO_ROOT / "docs" / "community" / "public-launch-kit.md").read_text(
            encoding="utf-8"
        )
        first_github_discussion = (
            REPO_ROOT / "docs" / "community" / "first-github-discussion.md"
        ).read_text(encoding="utf-8")
        adoption_funnel = (REPO_ROOT / "docs" / "community" / "adoption-funnel.md").read_text(
            encoding="utf-8"
        )
        demo_playbook = (REPO_ROOT / "docs" / "community" / "demo-pilot-playbook.md").read_text(
            encoding="utf-8"
        )
        community_launch_plan = (
            REPO_ROOT / "docs" / "community" / "user-community-launch-plan.md"
        ).read_text(encoding="utf-8")
        user_onboarding_guide = (
            REPO_ROOT / "docs" / "community" / "user-onboarding-guide.md"
        ).read_text(encoding="utf-8")
        developer_community_playbook = (
            REPO_ROOT / "docs" / "community" / "developer-community-playbook.md"
        ).read_text(encoding="utf-8")
        contributor_onboarding = (
            REPO_ROOT / "docs" / "community" / "contributor-onboarding.md"
        ).read_text(encoding="utf-8")
        community_governance = (
            REPO_ROOT / "docs" / "community" / "community-governance.md"
        ).read_text(encoding="utf-8")
        community_rituals = (REPO_ROOT / "docs" / "community" / "community-rituals.md").read_text(
            encoding="utf-8"
        )
        user_feedback_loop = (REPO_ROOT / "docs" / "community" / "user-feedback-loop.md").read_text(
            encoding="utf-8"
        )
        seed_discussions = (REPO_ROOT / "docs" / "community" / "seed-discussions.md").read_text(
            encoding="utf-8"
        )
        partner_guide = (
            REPO_ROOT / "docs" / "community" / "integration-partner-guide.md"
        ).read_text(encoding="utf-8")
        validation_scorecard = (
            REPO_ROOT / "docs" / "community" / "validation-scorecard.md"
        ).read_text(encoding="utf-8")
        adopter_story_template = (
            REPO_ROOT / "docs" / "community" / "adopter-story-template.md"
        ).read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        issue_templates = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")
        )
        discussion_templates = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / ".github" / "DISCUSSION_TEMPLATE").glob("*.yml")
        )
        labels = (REPO_ROOT / ".github" / "labels.yml").read_text(encoding="utf-8")
        codeowners = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
        contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        pull_request_template = (REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(
            encoding="utf-8"
        )

        for fragment in (
            "Primary Audiences",
            "Adoption Ladder",
            "30-Day Pilot Motion",
            "Success Metrics",
        ):
            self.assertIn(fragment, adoption_playbook)

        for fragment in (
            "Adoption Thesis",
            "Adoption Flywheel",
            "Distribution Plan",
            "Launch Metrics",
        ):
            self.assertIn(fragment, popularity_playbook)

        for fragment in (
            "Star Conversion Assets",
            "7-Day Launch Motion",
            "Distribution Channels",
            "Do Not Do",
        ):
            self.assertIn(fragment, star_growth_plan)

        for fragment in ("Use Cases", "Priority Matrix", "Public Proof Assets"):
            self.assertIn(fragment, use_case_catalog)

        for fragment in ("10-Minute Fit Check", "60-Minute Technical Check", "30-Day Decision"):
            self.assertIn(fragment, quick_evaluation_path)

        for fragment in ("Comparison Matrix", "Anti-Fit Signals", "Adoption Recommendation"):
            self.assertIn(fragment, comparison_guide)

        for fragment in ("5-Minute Sponsor Brief", "Stakeholder Map", "Objection Handling"):
            self.assertIn(fragment, champion_kit)

        for fragment in ("Launch Post", "Partner Outreach Email", "Conference Or Meetup Abstract"):
            self.assertIn(fragment, public_launch_kit)

        self.assertIn("First GitHub Discussion", public_launch_kit)
        self.assertIn("Show DEALIoT", public_launch_kit)

        for fragment in (
            "Title",
            "Body",
            "Show DEALIoT",
            "If this looks useful, star the repository",
        ):
            self.assertIn(fragment, first_github_discussion)

        for fragment in ("Funnel Stages", "Conversion Assets", "Minimum Viable Popularity"):
            self.assertIn(fragment, adoption_funnel)

        for fragment in ("Pilot Scorecard", "Local Demo Script", "Post-Pilot Decision"):
            self.assertIn(fragment, demo_playbook)

        for fragment in (
            "Community Promise",
            "30-Day Launch Motion",
            "Launch Checklist",
            "GitHub Discussions",
        ):
            self.assertIn(fragment, community_launch_plan)

        for fragment in ("First 60 Minutes", "Community Entry Points", "Good Question Template"):
            self.assertIn(fragment, user_onboarding_guide)

        for fragment in ("Contributor Tracks", "Contribution Ladder", "Good First Issue Criteria"):
            self.assertIn(fragment, developer_community_playbook)

        for fragment in ("First Contribution Paths", "Validation Shortcuts", "Asking For Help"):
            self.assertIn(fragment, contributor_onboarding)

        for fragment in ("Principles", "Roles", "Decision Process", "Recognition"):
            self.assertIn(fragment, community_governance)

        for fragment in ("Weekly Triage", "Office Hours Agenda", "Discussion Moderation Rules"):
            self.assertIn(fragment, community_rituals)

        for fragment in ("Triage Flow", "Prioritization Score", "Feedback Closure"):
            self.assertIn(fragment, user_feedback_loop)

        for fragment in (
            "Launch Discussion",
            "Q&A Seed",
            "Ideas Seed",
            "Show And Tell Seed",
            "Pilot Report Seed",
        ):
            self.assertIn(fragment, seed_discussions)

        for fragment in ("Partner Tracks", "Integration Contract", "Partner Readiness Checklist"):
            self.assertIn(fragment, partner_guide)

        for fragment in (
            "Decision Rule",
            "First event reaches Kafka",
            "Production deployment gaps",
        ):
            self.assertIn(fragment, validation_scorecard)

        for fragment in ("Publication limits", "Outcome", "Remaining gaps"):
            self.assertIn(fragment, adopter_story_template)

        for fragment in (
            "Demo or pilot request",
            "Adopter story",
            "Documentation gap",
            "User feedback",
            "Use case proposal",
        ):
            self.assertIn(fragment, issue_templates)

        for fragment in (
            "Use this for usage questions",
            "Use this for early feature",
            "Use this for approved demos",
            "Use this to share a sanitized 30-day pilot result",
            "Use this when you want to contribute",
            "Use this for launch announcements",
        ):
            self.assertIn(fragment, discussion_templates)

        for fragment in (
            "user-feedback",
            "show-and-tell",
            "pilot",
            "integration",
            "use-case",
            "contributor",
            "good first issue",
            "help wanted",
            "mentored",
            "community",
        ):
            self.assertIn(fragment, labels)

        for fragment in ("@Smartappli", "/docs/community/"):
            self.assertIn(fragment, codeowners)

        for fragment in (
            "Contributor onboarding",
            "Developer community playbook",
            "Community governance",
            "good first issue",
        ):
            self.assertIn(fragment, contributing)

        self.assertIn("Operational Impact", pull_request_template)
        self.assertIn("Why Teams Adopt DEALIoT", readme)
        self.assertIn("Fast Adoption Path", readme)
        self.assertIn("Architecture popularity playbook", readme)
        self.assertIn("GitHub star growth plan", readme)
        self.assertIn("Use case catalog", readme)
        self.assertIn("Quick evaluation path", readme)
        self.assertIn("Architecture comparison guide", readme)
        self.assertIn("Internal champion kit", readme)
        self.assertIn("Public launch kit", readme)
        self.assertIn("First GitHub discussion", readme)
        self.assertIn("Adoption funnel", readme)
        self.assertIn("User community launch plan", readme)
        self.assertIn("Developer community playbook", readme)
        self.assertIn("Contributor onboarding", readme)
        self.assertIn("Community governance", readme)
        self.assertIn("Community discussions", readme)
        self.assertIn("Public website", readme)
        self.assertIn("Website source repository", readme)
        self.assertIn("https://github.com/Smartappli/DEALWebsite", readme)

    def test_management_console_backend_avoids_scanner_hotspots(self) -> None:
        app_py = (REPO_ROOT / "management-console" / "management_console" / "app.py").read_text(
            encoding="utf-8"
        )
        openaire_py = (
            REPO_ROOT / "management-console" / "management_console" / "openaire.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("urlopen", app_py)
        self.assertNotIn('os.getenv("MANAGEMENT_CONSOLE_BIND", "0.0.0.0")', app_py)
        self.assertIn('os.getenv("MANAGEMENT_CONSOLE_BIND", "127.0.0.1")', app_py)
        self.assertNotIn("xml.etree", openaire_py)
        self.assertNotIn("from xml", openaire_py)
        self.assertIn("xml_escape_text", openaire_py)

        self.assertIn("pylint: disable=arguments-differ", app_py)
        bridge_rs = (REPO_ROOT / "mqtt-kafka-bridge" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("start_health_server", bridge_rs)

    def test_github_metadata_has_no_hidden_unicode_controls(self) -> None:
        scanned_paths = [
            *sorted((REPO_ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")),
            *sorted((REPO_ROOT / ".github" / "DISCUSSION_TEMPLATE").glob("*.yml")),
            REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
        ]
        allowed_controls = {"\n", "\r", "\t"}

        for path in scanned_paths:
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
                for column, char in enumerate(line, start=1):
                    if char in allowed_controls:
                        continue
                    if unicodedata.category(char).startswith("C"):
                        codepoint = f"U+{ord(char):04X}"
                        self.fail(f"{path}:{line_number}:{column} contains {codepoint}")

    def test_critical_shell_scripts_are_present(self) -> None:
        script_files = [
            REPO_ROOT / "scripts" / "post-bootstrap.sh",
            REPO_ROOT / "scripts" / "start-patroni.sh",
            REPO_ROOT / "scripts" / "start-pgbouncer-rw.sh",
            REPO_ROOT / "scripts" / "start-pgbouncer-ro.sh",
            REPO_ROOT / "scripts" / "smoke-e2e.sh",
        ]

        for script in script_files:
            self.assertTrue(script.is_file(), f"Missing shell script: {script}")

    def test_runtime_python_sources_parse_with_ci_minimum_python(self) -> None:
        runtime_sources = [
            REPO_ROOT / "airflow" / "dags" / "media_backfill.py",
            REPO_ROOT / "dealiot_contracts" / "events.py",
            REPO_ROOT / "flink" / "jobs" / "streaming_minimal.py",
            REPO_ROOT / "management-console" / "management_console" / "app.py",
            REPO_ROOT / "management-console" / "management_console" / "catalog.py",
            REPO_ROOT / "management-console" / "management_console" / "device_registry.py",
            REPO_ROOT / "management-console" / "management_console" / "migrate.py",
            REPO_ROOT / "management-console" / "management_console" / "openaire.py",
            REPO_ROOT / "management-console" / "management_console" / "zenodo.py",
            REPO_ROOT / "mqtt-kafka-bridge" / "bridge.py",
            REPO_ROOT / "pipelines" / "media_backfill.py",
        ]

        for source in runtime_sources:
            ast.parse(
                source.read_text(encoding="utf-8"),
                filename=str(source),
                feature_version=(3, 12),
            )


if __name__ == "__main__":
    unittest.main()
