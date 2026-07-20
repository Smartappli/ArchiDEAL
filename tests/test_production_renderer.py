from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "deploy/kubernetes/render.py"
EXAMPLE_VALUES = ROOT / "deploy/kubernetes/values.example.yaml"


def bash_executable() -> str | None:
    """Prefer Git Bash on Windows, where System32/bash.exe may be a WSL shim."""

    if os.name == "nt":
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parents[1] / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash")


class ProductionRendererTests(unittest.TestCase):
    def render(
        self,
        output: Path,
        *arguments: str,
        values: Path = EXAMPLE_VALUES,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--values",
                str(values),
                "--output",
                str(output),
                *arguments,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_value_rejected(self, key: str, value: str, expected: str) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            values = yaml.safe_load(EXAMPLE_VALUES.read_text(encoding="utf-8"))
            values[key] = value
            values_path = temporary / "values.yaml"
            values_path.write_text(yaml.safe_dump(values), encoding="utf-8")
            result = self.render(
                temporary / "rendered",
                "--allow-example",
                values=values_path,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn(expected, result.stderr)

    def render_with_runtime_config(
        self,
        temporary: Path,
        updates: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        kubernetes = temporary / "kubernetes"
        shutil.copytree(ROOT / "deploy/kubernetes", kubernetes)
        configuration = kubernetes / "base/configuration.yaml"
        documents = list(
            yaml.safe_load_all(configuration.read_text(encoding="utf-8")),
        )
        runtime_config = next(
            document
            for document in documents
            if isinstance(document, dict)
            and document.get("kind") == "ConfigMap"
            and document.get("metadata", {}).get("name") == "archideal-runtime"
        )
        runtime_config["data"].update(updates)
        configuration.write_text(
            yaml.safe_dump_all(documents, sort_keys=False),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                sys.executable,
                str(kubernetes / "render.py"),
                "--values",
                str(kubernetes / "values.example.yaml"),
                "--output",
                str(temporary / "rendered"),
                "--allow-example",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def render_with_kubernetes_mutation(
        self,
        temporary: Path,
        relative_path: str,
        mutate,
    ) -> subprocess.CompletedProcess[str]:
        kubernetes = temporary / "kubernetes"
        shutil.copytree(ROOT / "deploy/kubernetes", kubernetes)
        manifest_path = kubernetes / relative_path
        documents = list(
            yaml.safe_load_all(manifest_path.read_text(encoding="utf-8")),
        )
        mutate(documents)
        manifest_path.write_text(
            yaml.safe_dump_all(documents, sort_keys=False),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                sys.executable,
                str(kubernetes / "render.py"),
                "--values",
                str(kubernetes / "values.example.yaml"),
                "--output",
                str(temporary / "rendered"),
                "--allow-example",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_example_overlay_renders_with_fail_closed_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "rendered"
            result = self.render(output, "--allow-example")
            self.assertEqual(result.returncode, 0, result.stderr)

            release_id = yaml.safe_load(EXAMPLE_VALUES.read_text(encoding="utf-8"))[
                "RELEASE_ID"
            ]

            documents = []
            for path in output.rglob("*.yaml"):
                documents.extend(
                    document
                    for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
                    if isinstance(document, dict)
                )

            by_kind_name = {
                (
                    document.get("kind"),
                    document.get("metadata", {}).get("name"),
                ): document
                for document in documents
            }
            self.assertIn(("Job", f"kafka-preflight-{release_id}"), by_kind_name)
            private_preflight = by_kind_name[("Job", f"network-preflight-{release_id}")]
            private_container = private_preflight["spec"]["template"]["spec"][
                "containers"
            ][0]
            self.assertEqual(
                private_container["command"],
                ["python", "/bootstrap/private_network_preflight.py"],
            )
            self.assertEqual(private_preflight["spec"]["backoffLimit"], 0)
            self.assertEqual(
                private_preflight["spec"]["template"]["spec"]["serviceAccountName"],
                "archideal-preflight",
            )
            self.assertTrue(private_container["env"])
            self.assertTrue(
                all(
                    "value" in item and "valueFrom" not in item
                    for item in private_container["env"]
                )
            )
            self.assertNotIn("envFrom", private_container)
            self.assertNotIn(
                "volumes",
                private_preflight["spec"]["template"]["spec"],
            )
            synthetic = by_kind_name[("Job", f"production-smoke-{release_id}")]
            synthetic_container = synthetic["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(
                synthetic_container["command"],
                ["python", "-m", "management_console.synthetic_publish"],
            )
            synthetic_env = {item["name"]: item for item in synthetic_container["env"]}
            self.assertEqual(
                synthetic_env["MQTT_USERNAME"]["valueFrom"]["secretKeyRef"]["key"],
                "mqtt-smoke-username",
            )
            self.assertEqual(
                synthetic_env["MQTT_PASSWORD"]["valueFrom"]["secretKeyRef"]["key"],
                "mqtt-smoke-password",
            )
            self.assertEqual(
                synthetic_env["SMOKE_DEVICE_ID"]["value"],
                f"archideal-smoke-{release_id}",
            )
            smoke_policy = by_kind_name[("NetworkPolicy", "production-smoke-egress")]
            self.assertEqual(
                {
                    port["port"]
                    for rule in smoke_policy["spec"]["egress"]
                    for port in rule["ports"]
                },
                {8883},
            )

            oauth = by_kind_name[("Deployment", "oauth2-proxy")]
            oauth_pod = oauth["spec"]["template"]["spec"]
            oauth_arguments = set(oauth_pod["containers"][0]["args"])
            self.assertTrue(
                {
                    "--skip-jwt-bearer-tokens=true",
                    "--bearer-token-login-fallback=false",
                    "--pass-authorization-header=false",
                    "--set-authorization-header=false",
                    "--pass-access-token=true",
                }.issubset(oauth_arguments)
            )
            self.assertEqual(
                {
                    argument
                    for argument in oauth_arguments
                    if argument.startswith("--skip-auth-route=")
                },
                {
                    "--skip-auth-route=POST=^/dealhost/api/gateway/github/webhook/$",
                },
            )
            valkey_validator = next(
                container
                for container in oauth_pod["initContainers"]
                if container["name"] == "validate-valkey-tls"
            )
            self.assertEqual(valkey_validator["command"], ["python", "-c"])
            self.assertIn(
                "cache_config(require_tls=True)",
                " ".join(valkey_validator["args"]),
            )
            self.assertEqual(
                valkey_validator["env"][0]["valueFrom"]["secretKeyRef"]["key"],
                "valkey-url",
            )
            runtime_secret_name = f"archideal-runtime-secrets-{release_id}"
            runtime_controller_tls_secret_name = (
                f"dealhost-runtime-controller-tls-{release_id}"
            )
            self.assertEqual(
                valkey_validator["env"][0]["valueFrom"]["secretKeyRef"]["name"],
                runtime_secret_name,
            )

            dealhost_container = by_kind_name[("Deployment", "dealhost")]["spec"][
                "template"
            ]["spec"]["containers"][0]
            dealhost_env = {item["name"]: item for item in dealhost_container["env"]}
            self.assertEqual(
                dealhost_env["VALKEY_URL"]["valueFrom"]["secretKeyRef"]["key"],
                "valkey-url",
            )
            self.assertEqual(
                dealhost_env["VALKEY_URL"]["valueFrom"]["secretKeyRef"]["name"],
                runtime_secret_name,
            )

            runtime_external_secret = by_kind_name[
                ("ExternalSecret", runtime_secret_name)
            ]
            self.assertEqual(
                runtime_external_secret["spec"]["refreshPolicy"],
                "CreatedOnce",
            )
            self.assertNotIn("refreshInterval", runtime_external_secret["spec"])
            self.assertEqual(
                runtime_external_secret["spec"]["target"]["name"],
                runtime_secret_name,
            )
            self.assertEqual(
                runtime_external_secret["spec"]["target"]["template"]["metadata"][
                    "labels"
                ]["archideal.io/release"],
                release_id,
            )
            runtime_controller_tls_external_secret = by_kind_name[
                ("ExternalSecret", runtime_controller_tls_secret_name)
            ]
            self.assertEqual(
                runtime_controller_tls_external_secret["metadata"]["labels"][
                    "archideal.io/release"
                ],
                release_id,
            )
            self.assertEqual(
                runtime_controller_tls_external_secret["spec"]["target"]["name"],
                runtime_controller_tls_secret_name,
            )
            self.assertEqual(
                runtime_controller_tls_external_secret["spec"]["target"]["template"][
                    "type"
                ],
                "kubernetes.io/tls",
            )
            registry_external_secret = by_kind_name[
                ("ExternalSecret", "archideal-registry-credentials")
            ]
            self.assertEqual(
                registry_external_secret["spec"]["refreshPolicy"],
                "Periodic",
            )
            self.assertEqual(
                registry_external_secret["spec"]["refreshInterval"],
                "1h",
            )

            ingress = by_kind_name[("Ingress", "archideal")]
            public_backends = {
                path["backend"]["service"]["name"]
                for rule in ingress["spec"]["rules"]
                for path in rule["http"]["paths"]
            }
            self.assertEqual(public_backends, {"oauth2-proxy"})

            apisix_routes = yaml.safe_load(
                by_kind_name[("ConfigMap", "apisix-bootstrap")]["data"]["routes.json"]
            )["routes"]
            for route in apisix_routes:
                self.assertEqual(
                    route["plugins"]["proxy-rewrite"]["headers"]["set"][
                        "X-Forwarded-Proto"
                    ],
                    "$http_x_forwarded_proto",
                    route["id"],
                )
            routes_by_id = {route["id"]: route for route in apisix_routes}
            for route_id in (
                "archideal-dealhost",
                "archideal-dealiot",
                "archideal-dealdata-core",
                "archideal-dealdata-gps",
                "archideal-dealdata-sensor",
            ):
                self.assertEqual(
                    routes_by_id[route_id]["plugins"]["proxy-rewrite"]["headers"][
                        "set"
                    ]["Authorization"],
                    "Bearer $http_x_forwarded_access_token",
                )

            apisix = by_kind_name[("Deployment", "apisix")]
            apisix_containers = {
                container["name"]: container
                for container in apisix["spec"]["template"]["spec"]["containers"]
            }
            self.assertEqual(
                apisix_containers["apisix"]["readinessProbe"]["httpGet"],
                {"path": "/readyz", "port": 9191},
            )
            self.assertEqual(
                apisix_containers["apisix-health"]["command"],
                ["python", "/bootstrap/health.py"],
            )
            self.assertEqual(
                apisix_containers["apisix-health"]["readinessProbe"]["httpGet"],
                {"path": "/readyz", "port": "health"},
            )

            console = by_kind_name[("Deployment", "dealiot-console")]
            console_container = console["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(
                console_container["readinessProbe"]["httpGet"],
                {"path": "/readyz", "port": "http"},
            )
            console_env = {item["name"]: item for item in console_container["env"]}
            self.assertEqual(
                console_env["DEALIOT_REGISTRY_DATABASE_PASSWORD"]["valueFrom"][
                    "secretKeyRef"
                ]["key"],
                "dealiot-registry-database-password",
            )
            console_ca_items = {
                item["key"]
                for volume in console["spec"]["template"]["spec"]["volumes"]
                if volume["name"] == "ca"
                for item in volume["secret"]["items"]
            }
            self.assertIn("postgres-ca.crt", console_ca_items)

            dealiot_registry_migration = by_kind_name[
                ("Job", f"dealiot-registry-mig-{release_id}")
            ]
            registry_migration_container = dealiot_registry_migration["spec"][
                "template"
            ]["spec"]["containers"][0]
            self.assertEqual(
                registry_migration_container["command"],
                ["python", "-m", "management_console.migrate"],
            )
            self.assertEqual(
                registry_migration_container["image"],
                console_container["image"],
            )
            registry_migration_env = {
                item["name"]: item for item in registry_migration_container["env"]
            }
            self.assertEqual(
                set(registry_migration_env),
                {
                    "DEALIOT_REGISTRY_DATABASE_PASSWORD",
                    "DEALIOT_REGISTRY_DATABASE_USER",
                    "DEALIOT_REGISTRY_RUNTIME_DATABASE_USER",
                },
            )
            self.assertEqual(
                registry_migration_env["DEALIOT_REGISTRY_DATABASE_USER"]["value"],
                "dealiot_registry_migrator",
            )
            self.assertEqual(
                registry_migration_env["DEALIOT_REGISTRY_RUNTIME_DATABASE_USER"][
                    "value"
                ],
                "dealiot_registry_app",
            )
            self.assertEqual(
                registry_migration_env["DEALIOT_REGISTRY_DATABASE_PASSWORD"][
                    "valueFrom"
                ]["secretKeyRef"]["key"],
                "dealiot-registry-migration-database-password",
            )

            dealhost_migration = by_kind_name[
                (
                    "Job",
                    f"dealhost-migrate-{release_id}",
                )
            ]
            migration_env = {
                item["name"]: item
                for item in dealhost_migration["spec"]["template"]["spec"][
                    "containers"
                ][0]["env"]
            }
            self.assertEqual(
                set(migration_env),
                {"DJANGO_SETTINGS_MODULE", "DEALHOST_DATABASE_PASSWORD"},
            )
            self.assertEqual(
                migration_env["DJANGO_SETTINGS_MODULE"]["value"],
                "dealhost.settings.migration",
            )

            runtime_config = by_kind_name[("ConfigMap", "archideal-runtime")]["data"]
            self.assertEqual(
                runtime_config["DEALIOT_REGISTRY_DATABASE_HOST"],
                "dealiot-registry-postgres.example.invalid",
            )
            self.assertEqual(
                runtime_config["DEALIOT_REGISTRY_DATABASE_SSLMODE"],
                "verify-full",
            )
            self.assertEqual(
                runtime_config["DEALIOT_REGISTRY_DATABASE_USER"],
                "dealiot_registry_app",
            )
            self.assertEqual(
                runtime_config["DEALIOT_REGISTRY_DATABASE_SSLROOTCERT"],
                "/var/run/archideal-ca/postgres-ca.crt",
            )
            self.assertEqual(
                runtime_config["MANAGEMENT_CONSOLE_OIDC_READ_ROLES"],
                "archideal-production-readers",
            )
            self.assertEqual(
                runtime_config["MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES"],
                "archideal-production-admins",
            )
            self.assertEqual(
                runtime_config["MANAGEMENT_CONSOLE_OIDC_GROUPS_CLAIM"],
                "groups",
            )
            self.assertEqual(
                runtime_config["DEALHOST_OIDC_READ_GROUPS"],
                "archideal-production-readers",
            )
            self.assertEqual(
                runtime_config["DEALHOST_OIDC_ADMIN_GROUPS"],
                "archideal-production-admins",
            )
            self.assertEqual(
                runtime_config["DEALHOST_OIDC_GROUPS_CLAIM"],
                "groups",
            )
            self.assertEqual(
                runtime_config["APISIX_ROUTE_ALLOWED_UPSTREAM_HOSTS"],
                "dealhost,dealiot,dealdata-core,dealdata-gps,dealdata-sensor",
            )
            self.assertEqual(
                runtime_config["APISIX_ROUTE_ALLOWED_UPSTREAM_PORTS"],
                "7000,7001,7002,8000,8080",
            )
            self.assertEqual(
                runtime_config["APISIX_ROUTE_ALLOWED_UPSTREAMS"],
                "dealhost:8000,dealiot:8080,dealdata-core:7000,"
                "dealdata-gps:7001,dealdata-sensor:7002",
            )

            runtime_secret_keys = {
                item["secretKey"]: item["remoteRef"]["key"]
                for item in runtime_external_secret["spec"]["data"]
            }
            self.assertEqual(
                runtime_secret_keys["dealiot-registry-database-password"],
                "replace/archideal/production/postgres/dealiot-registry-password",
            )
            self.assertEqual(
                runtime_secret_keys["dealiot-registry-migration-database-password"],
                "replace/archideal/production/postgres/"
                "dealiot-registry-migration-password",
            )

            service_accounts = [
                document
                for document in documents
                if document.get("kind") == "ServiceAccount"
            ]
            self.assertTrue(service_accounts)
            for account in service_accounts:
                self.assertIn(
                    {"name": "archideal-registry-credentials"},
                    account.get("imagePullSecrets", []),
                )

            pod_owners = [
                document
                for document in documents
                if document.get("kind") in {"Deployment", "StatefulSet", "Job"}
            ]
            self.assertTrue(pod_owners)
            for workload in pod_owners:
                self.assertEqual(
                    workload["spec"]["template"]["spec"]["nodeSelector"],
                    {
                        "kubernetes.io/os": "linux",
                        "kubernetes.io/arch": "amd64",
                    },
                    workload["metadata"]["name"],
                )
                pod_spec = workload["spec"]["template"]["spec"]
                for container in [
                    *pod_spec.get("initContainers", []),
                    *pod_spec.get("containers", []),
                ]:
                    for environment in container.get("env", []):
                        secret_ref = environment.get("valueFrom", {}).get(
                            "secretKeyRef"
                        )
                        if secret_ref:
                            self.assertEqual(
                                secret_ref["name"],
                                runtime_secret_name,
                                f"{workload['metadata']['name']}/{container['name']}",
                            )
                for volume in pod_spec.get("volumes", []):
                    secret_name = volume.get("secret", {}).get("secretName")
                    if not secret_name or secret_name == runtime_secret_name:
                        continue
                    owner_name = workload["metadata"]["name"]
                    self.assertEqual(
                        secret_name,
                        runtime_controller_tls_secret_name,
                        f"{owner_name}/{volume['name']}",
                    )
                    self.assertIn(
                        owner_name,
                        {"dealhost-runtime-controller", "dealhost-runtime-worker"},
                    )
                    item_keys = {
                        item["key"] for item in volume["secret"].get("items", [])
                    }
                    expected_keys = (
                        {"tls.crt", "tls.key", "ca.crt"}
                        if owner_name == "dealhost-runtime-controller"
                        else {"ca.crt"}
                    )
                    self.assertEqual(item_keys, expected_keys)

            hpa_targets = {
                document["spec"]["scaleTargetRef"]["name"]: document
                for document in documents
                if document.get("kind") == "HorizontalPodAutoscaler"
            }
            long_running = {
                document["metadata"]["name"]: document
                for document in documents
                if document.get("kind") in {"Deployment", "StatefulSet"}
            }
            self.assertEqual(set(hpa_targets), set(long_running))
            for name, workload in long_running.items():
                self.assertNotIn(
                    "replicas",
                    workload["spec"],
                    f"{name}: HPA must remain the sole SSA owner of scale",
                )

            for monitor_kind, monitor_name in (
                ("ServiceMonitor", "archideal-oauth2-proxy"),
                ("ServiceMonitor", "archideal-apisix"),
                ("ServiceMonitor", "archideal-dealdata-api"),
                ("PodMonitor", "archideal-mqtt-kafka-bridge"),
                ("PodMonitor", "archideal-dealdata-consumers"),
                ("ServiceMonitor", "archideal-runtime-controller"),
                ("ServiceMonitor", "archideal-runtime-worker"),
                ("PrometheusRule", "archideal-production-slo"),
            ):
                monitor = by_kind_name[(monitor_kind, monitor_name)]
                self.assertEqual(
                    monitor["metadata"]["labels"]["monitoring.archideal.io/enabled"],
                    "true",
                )

            for consumer_name in (
                "dealdata-gps-consumer",
                "dealdata-sensor-consumer",
            ):
                consumer_hpa = by_kind_name[("HorizontalPodAutoscaler", consumer_name)]
                self.assertEqual(consumer_hpa["spec"]["maxReplicas"], 3)
                self.assertEqual(
                    consumer_hpa["spec"]["scaleTargetRef"],
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "name": consumer_name,
                    },
                )
                container = by_kind_name[("Deployment", consumer_name)]["spec"][
                    "template"
                ]["spec"]["containers"][0]
                self.assertIn(
                    {"name": "metrics", "containerPort": 9100},
                    container["ports"],
                )
                self.assertEqual(
                    container["readinessProbe"]["httpGet"],
                    {"path": "/readyz", "port": "metrics"},
                )
                self.assertEqual(
                    container["livenessProbe"]["httpGet"],
                    {"path": "/healthz", "port": "metrics"},
                )

            runtime_worker = by_kind_name[("Deployment", "dealhost-runtime-worker")][
                "spec"
            ]["template"]["spec"]["containers"][0]
            self.assertIn(
                {"name": "metrics", "containerPort": 9102},
                runtime_worker["ports"],
            )
            self.assertEqual(
                runtime_worker["readinessProbe"]["httpGet"],
                {"path": "/health/ready", "port": "metrics"},
            )
            self.assertEqual(
                runtime_worker["livenessProbe"]["httpGet"],
                {"path": "/health/live", "port": "metrics"},
            )
            controller_monitor = by_kind_name[
                ("ServiceMonitor", "archideal-runtime-controller")
            ]["spec"]["endpoints"][0]
            self.assertEqual(controller_monitor["scheme"], "https")
            self.assertEqual(
                controller_monitor["tlsConfig"]["serverName"],
                "dealhost-runtime-controller.archideal.svc.cluster.local",
            )
            self.assertEqual(
                controller_monitor["tlsConfig"]["ca"]["secret"],
                {
                    "name": runtime_controller_tls_secret_name,
                    "key": "ca.crt",
                },
            )

            expected_monitoring_ports = {
                "monitoring-identity-ingress": {44180},
                "monitoring-dealdata-ingress": {9101},
                "monitoring-ingestion-ingress": {8080, 9100},
                "dealhost-runtime-worker-ingress": {9102},
            }
            for policy_name, expected_ports in expected_monitoring_ports.items():
                policy = by_kind_name[("NetworkPolicy", policy_name)]
                monitoring_ports = {
                    port["port"]
                    for ingress_rule in policy["spec"]["ingress"]
                    for port in ingress_rule["ports"]
                }
                self.assertEqual(monitoring_ports, expected_ports)
                for ingress_rule in policy["spec"]["ingress"]:
                    for source in ingress_rule["from"]:
                        self.assertEqual(
                            source["podSelector"]["matchLabels"],
                            {"monitoring.archideal.io/scraper": "true"},
                        )

            ingress_policy = by_kind_name[("NetworkPolicy", "oauth2-proxy-ingress")]
            ingress_peer = ingress_policy["spec"]["ingress"][0]["from"][0]
            self.assertEqual(
                ingress_peer["namespaceSelector"]["matchLabels"],
                {"kubernetes.io/metadata.name": "ingress-nginx"},
            )
            self.assertEqual(
                ingress_peer["podSelector"]["matchLabels"],
                {
                    "app.kubernetes.io/name": "ingress-nginx",
                    "app.kubernetes.io/component": "controller",
                },
            )

            for service_name in (
                "dealdata-core",
                "dealdata-gps",
                "dealdata-sensor",
            ):
                service_port = {
                    "dealdata-core": 7000,
                    "dealdata-gps": 7001,
                    "dealdata-sensor": 7002,
                }[service_name]
                workload = by_kind_name[("Deployment", service_name)]
                application = workload["spec"]["template"]["spec"]["containers"][0]
                application_env = {
                    item["name"]: item for item in application.get("env", [])
                }
                self.assertEqual(
                    application_env["DEALDATA_OIDC_CLIENT_ID"]["valueFrom"][
                        "secretKeyRef"
                    ]["key"],
                    "dealdata-oidc-client-id",
                )
                self.assertEqual(
                    application_env["DEALDATA_OIDC_CLIENT_SECRET"]["valueFrom"][
                        "secretKeyRef"
                    ]["key"],
                    "dealdata-oidc-client-secret",
                )
                metrics_proxy = next(
                    container
                    for container in workload["spec"]["template"]["spec"]["containers"]
                    if container["name"] == "metrics-proxy"
                )
                self.assertEqual(
                    metrics_proxy["command"],
                    ["python", "-m", "dealdata_common.metrics_proxy"],
                )
                self.assertEqual(
                    metrics_proxy["args"][:6],
                    [
                        "--upstream",
                        f"http://127.0.0.1:{service_port}/metrics/",
                        "--upstream-ready",
                        f"http://127.0.0.1:{service_port}/health/ready/",
                        "--upstream-host",
                        service_name,
                    ],
                )
                service = by_kind_name[("Service", service_name)]
                self.assertIn(
                    {"name": "metrics", "port": 9101, "targetPort": "metrics"},
                    service["spec"]["ports"],
                )

            prometheus_rule = by_kind_name[
                ("PrometheusRule", "archideal-production-slo")
            ]
            alerts = [
                rule
                for group in prometheus_rule["spec"]["groups"]
                for rule in group["rules"]
                if "alert" in rule
            ]
            self.assertTrue(alerts)
            self.assertIn(
                "ArchiDEALConsumerNoAssignedCapacity",
                {alert["alert"] for alert in alerts},
            )
            self.assertTrue(
                {
                    "ArchiDEALRuntimeControllerUnavailable",
                    "ArchiDEALRuntimeKubernetesBackendUnavailable",
                    "ArchiDEALRuntimeWorkerUnavailable",
                    "ArchiDEALRuntimeOperationBacklogOld",
                    "ArchiDEALRuntimeOperationBacklogHigh",
                    "ArchiDEALRuntimeOperationStuck",
                }.issubset({alert["alert"] for alert in alerts})
            )
            for alert in alerts:
                self.assertIn("severity", alert["labels"])
                self.assertIn("owner", alert["labels"])
                self.assertIn("slo", alert["labels"])
                self.assertIn("runbook_url", alert["annotations"])
                self.assertTrue(
                    "service" in alert["labels"] or "by (service)" in alert["expr"],
                    alert["alert"],
                )

    def test_strict_mode_rejects_example_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.render(Path(temporary_directory) / "rendered")
        self.assertEqual(result.returncode, 2)
        self.assertIn("example", result.stderr.lower())

    def test_apisix_dynamic_route_policy_is_fail_closed_and_parseable(self) -> None:
        invalid_policies = (
            (
                {
                    "APISIX_ROUTE_ALLOWED_UPSTREAM_HOSTS": "",
                    "APISIX_ROUTE_ALLOWED_UPSTREAM_SUFFIXES": "",
                },
                "non-empty upstream host or suffix allowlist",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAM_HOSTS": "127.0.0.1"},
                "strict DNS hostnames",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAM_PORTS": ""},
                "non-empty port allowlist",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAM_PORTS": "7000,not-a-port"},
                "only numeric ports",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAM_PORTS": "07000"},
                "canonical ports",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAMS": ""},
                "non-empty exact host:port allowlist",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAMS": "dealhost:08000"},
                "canonical DNS host:port pairs",
            ),
            (
                {"APISIX_ROUTE_ALLOWED_UPSTREAMS": "dealhost:8000"},
                "exactly match the deployed non-interface bootstrap upstreams",
            ),
        )
        for index, (updates, expected) in enumerate(invalid_policies):
            with (
                self.subTest(updates=updates),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = self.render_with_runtime_config(
                    Path(directory) / f"case-{index}",
                    updates,
                )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(expected, result.stderr)

        with tempfile.TemporaryDirectory() as directory:
            result = self.render_with_runtime_config(
                Path(directory) / "suffix-only",
                {
                    "APISIX_ROUTE_ALLOWED_UPSTREAM_HOSTS": "",
                    "APISIX_ROUTE_ALLOWED_UPSTREAM_SUFFIXES": (
                        ".archideal.svc.cluster.local"
                    ),
                },
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Every APISIX exact upstream", result.stderr)

    def test_apisix_oidc_header_boundary_and_network_policy_are_render_gates(
        self,
    ) -> None:
        def stop_forwarding_dealdata_token(documents) -> None:
            config = next(
                document
                for document in documents
                if document.get("metadata", {}).get("name") == "apisix-bootstrap"
            )
            routes = json.loads(config["data"]["routes.json"])
            core_route = next(
                route
                for route in routes["routes"]
                if route["id"] == "archideal-dealdata-core"
            )
            headers = core_route["plugins"]["proxy-rewrite"]["headers"]
            headers["set"].pop("Authorization")
            headers["remove"] = ["Authorization", "X-Forwarded-Access-Token"]
            config["data"]["routes.json"] = json.dumps(routes)

        with tempfile.TemporaryDirectory() as directory:
            result = self.render_with_kubernetes_mutation(
                Path(directory) / "token-leak",
                "base/configuration.yaml",
                stop_forwarding_dealdata_token,
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("must exchange the forwarded", result.stderr)

        def remove_dealdata_oidc_egress(documents) -> None:
            policy = next(
                document
                for document in documents
                if document.get("metadata", {}).get("name") == "dealdata-api-egress"
            )
            policy["spec"]["egress"] = [
                rule
                for rule in policy["spec"]["egress"]
                if all(port["port"] != 443 for port in rule.get("ports", []))
            ]

        with tempfile.TemporaryDirectory() as directory:
            result = self.render_with_kubernetes_mutation(
                Path(directory) / "dealdata-oidc-egress",
                "base/network-policies.yaml",
                remove_dealdata_oidc_egress,
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("dealdata-api-egress", result.stderr)

        def remove_dealhost_egress(documents) -> None:
            policy = next(
                document
                for document in documents
                if document.get("metadata", {}).get("name") == "apisix-egress"
            )
            dealhost_rule = next(
                rule
                for rule in policy["spec"]["egress"]
                if rule.get("to", [{}])[0]
                .get("podSelector", {})
                .get("matchLabels", {})
                .get("app.kubernetes.io/name")
                == "dealhost"
            )
            dealhost_rule["ports"][0]["port"] = 8001

        with tempfile.TemporaryDirectory() as directory:
            result = self.render_with_kubernetes_mutation(
                Path(directory) / "network-drift",
                "base/network-policies.yaml",
                remove_dealhost_egress,
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("apisix-egress NetworkPolicy", result.stderr)

    def test_dependency_ports_must_match_network_policies(self) -> None:
        invalid_values = {
            "KAFKA_BOOTSTRAP_SERVERS": (
                "kafka-0.example.invalid:9092,kafka-1.example.invalid:9093,"
                "kafka-2.example.invalid:9093",
                "TCP port 9093",
            ),
            "ETCD_ENDPOINT_1": (
                "https://etcd-0.example.invalid:2380",
                "TCP port 2379",
            ),
            "OIDC_INTROSPECTION_URL": (
                "https://identity.example.invalid:8443/oauth2/introspect",
                "TCP port 443",
            ),
            "OTEL_COLLECTOR_HTTP_ENDPOINT": (
                "https://otel.example.invalid:4318/v1/traces",
                "TCP port 443",
            ),
        }
        for key, (value, expected) in invalid_values.items():
            with self.subTest(key=key):
                self.assert_value_rejected(key, value, expected)

    def test_endpoint_values_reject_yaml_escape_characters(self) -> None:
        invalid_values = {
            "double quote": (
                "OIDC_ISSUER_URL",
                'https://identity.example.invalid/realms/archideal"',
            ),
            "single quote": (
                "OIDC_INTROSPECTION_URL",
                "https://identity.example.invalid/oauth2/introspect'",
            ),
            "backslash": (
                "OTEL_COLLECTOR_HTTP_ENDPOINT",
                "https://otel.example.invalid/v1\\traces",
            ),
            "newline": (
                "ETCD_ENDPOINT_1",
                "https://etcd-0.example.invalid:2379\nignored",
            ),
            "space": (
                "OIDC_ISSUER_URL",
                "https://identity.example.invalid/realms/archi deal",
            ),
            "non-ASCII": (
                "OIDC_ISSUER_URL",
                "https://identity.example.invalid/realms/archidéal",
            ),
        }
        for case, (key, value) in invalid_values.items():
            with self.subTest(case=case):
                self.assert_value_rejected(
                    key,
                    value,
                    "visible ASCII without whitespace, control characters, "
                    "quotes or backslashes",
                )

    def test_endpoint_values_reject_multi_document_yaml_injection(self) -> None:
        self.assert_value_rejected(
            "OIDC_ISSUER_URL",
            (
                'https://identity.example.invalid/realms/archideal"\n'
                "---\napiVersion: v1\nkind: Secret\nmetadata:\n"
                "  name: injected\n#"
            ),
            "quotes or backslashes",
        )

    def test_https_endpoints_require_canonical_dns_host_path_and_port(self) -> None:
        invalid_values = {
            "OIDC_ISSUER_URL": (
                "https://127.0.0.1/realms/archideal",
                "DNS hostname",
            ),
            "OIDC_INTROSPECTION_URL": (
                "https://identity.example.invalid:0443/oauth2/introspect",
                "canonical DNS hostname and numeric port",
            ),
            "OTEL_COLLECTOR_HTTP_ENDPOINT": (
                "https://otel.example.invalid/v1/%traces",
                "invalid URL path",
            ),
            "ETCD_ENDPOINT_1": (
                "https://etcd-0.example.invalid:2379/v3",
                "must not contain a path",
            ),
        }
        for key, (value, expected) in invalid_values.items():
            with self.subTest(key=key):
                self.assert_value_rejected(key, value, expected)

    def test_network_trust_boundaries_are_disjoint_and_private(self) -> None:
        invalid_values = {
            "KAFKA_EGRESS_CIDR": (
                "198.51.100.0/24",
                "IPv4 RFC1918",
            ),
            "POD_CIDR": (
                "198.51.100.0/24",
                "IPv4 RFC1918",
            ),
            "INGRESS_PROXY_CIDR": (
                "198.51.100.0/24",
                "IPv4 RFC1918",
            ),
            "INGRESS_NAMESPACE": (
                "archideal",
                "distinct trust boundaries",
            ),
            "MONITORING_NAMESPACE": (
                "ingress-nginx",
                "distinct trust boundaries",
            ),
            "MQTT_EGRESS_CIDR": (
                "10.100.0.0/24",
                "KAFKA_EGRESS_CIDR must not overlap MQTT_EGRESS_CIDR",
            ),
            "OIDC_EGRESS_CIDR": (
                "128.0.0.0/1",
                "no broader than /20",
            ),
            "GITHUB_EGRESS_CIDR": (
                "8000::/1",
                "no broader than /48",
            ),
        }
        for key, (value, expected) in invalid_values.items():
            with self.subTest(key=key):
                self.assert_value_rejected(key, value, expected)

    def test_admin_group_must_be_distinct_from_edge_admission(self) -> None:
        self.assert_value_rejected(
            "OIDC_ADMIN_GROUP",
            "archideal-production-readers",
            "must be distinct from OIDC_ALLOWED_GROUP",
        )

    def test_release_id_keeps_every_job_name_within_kubernetes_limits(self) -> None:
        self.assert_value_rejected(
            "RELEASE_ID",
            "a" * 40,
            "at most 39 characters",
        )
        self.assert_value_rejected(
            "RELEASE_ID",
            "none",
            "reserved promotion-state sentinel",
        )

    def test_force_refuses_to_replace_an_unmarked_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "owned-by-someone-else"
            output.mkdir()
            (output / "important.txt").write_text("preserve me\n", encoding="utf-8")
            result = self.render(output, "--allow-example", "--force")
            self.assertEqual(result.returncode, 2)
            self.assertIn("unmarked output", result.stderr)
            self.assertEqual(
                (output / "important.txt").read_text(encoding="utf-8"),
                "preserve me\n",
            )

    def test_ordered_deployer_is_executable_and_sequences_promotion(self) -> None:
        deployer = ROOT / "deploy/kubernetes/deploy-production.sh"
        self.assertTrue(os.access(deployer, os.X_OK))
        bash = bash_executable()
        self.assertIsNotNone(
            bash, "A Bash interpreter is required for shell syntax checks."
        )
        result = subprocess.run(
            [bash, "-n", str(deployer)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        script = deployer.read_text(encoding="utf-8")
        phases = [
            'apply_file "$rendered/overlays/production/external-secrets.yaml"',
            'apply_file "$rendered/base/private-network-preflight.yaml"',
            'apply_file "$rendered/base/network-policies.yaml"',
            'apply_file "$rendered/base/preflight.yaml"',
            'apply_file "$rendered/base/jobs.yaml"',
            'apply_file "$rendered/base/observability.yaml"',
            'for controller_name in "${controller_order[@]}"; do',
            'apply_file "$rendered/base/bootstrap.yaml"',
            'apply_file "$rendered/overlays/production/ingress.yaml"',
        ]
        offsets = [script.index(phase) for phase in phases]
        self.assertEqual(offsets, sorted(offsets))
        verification = script.index('python "$script_dir/verify-release.py"')
        rendering = script.index('python "$script_dir/render.py"')
        invocation_preparation = script.index(
            'python "$script_dir/prepare-invocation-jobs.py"'
        )
        bundle_rendering = script.index(
            'kubectl kustomize "$rendered/overlays/production"'
        )
        first_kubectl = script.index('known_context="$(kubectl config get-contexts')
        self.assertLess(verification, rendering)
        self.assertLess(rendering, invocation_preparation)
        self.assertLess(invocation_preparation, bundle_rendering)
        self.assertLess(verification, first_kubectl)
        crd_preflight = script.index("required_crds=(")
        reference_preflight = script.index("require_cluster_condition()")
        ingress_preflight = script.index(
            'python "$script_dir/validate-ingress-controller.py"'
        )
        first_mutation = script.index(
            'apply_cluster_file "$rendered/base/namespace.yaml"'
        )
        self.assertLess(crd_preflight, first_mutation)
        self.assertLess(reference_preflight, first_mutation)
        self.assertLess(ingress_preflight, first_mutation)
        self.assertIn(
            "--field-manager=archideal-production --dry-run=server",
            " ".join(script.replace("\\\n", " ").split()),
        )
        for crd in (
            "externalsecrets.external-secrets.io",
            "clustersecretstores.external-secrets.io",
            "certificates.cert-manager.io",
            "clusterissuers.cert-manager.io",
            "servicemonitors.monitoring.coreos.com",
            "podmonitors.monitoring.coreos.com",
            "prometheusrules.monitoring.coreos.com",
        ):
            self.assertIn(crd, script)
        for value_key in (
            "INGRESS_CLASS",
            "INGRESS_NAMESPACE",
            "INGRESS_PROXY_CIDR",
            "CLUSTER_ISSUER",
            "SECRET_STORE_NAME",
            "MONITORING_NAMESPACE",
            "VALKEY_HOST",
        ):
            self.assertIn(f"read_value {value_key}", script)
        for cluster_reference in (
            '"namespace/$ingress_namespace"',
            '"namespace/$monitoring_namespace"',
            '"ingressclass.networking.k8s.io/$ingress_class"',
            '"clusterissuer.cert-manager.io/$cluster_issuer" Ready',
            '"clustersecretstore.external-secrets.io/$secret_store_name" Ready',
            '"apiservice.apiregistration.k8s.io/v1beta1.metrics.k8s.io" Available',
        ):
            self.assertIn(cluster_reference, script.replace("\\\n", " "))
        self.assertIn('"k8s.io/ingress-nginx"', script)
        self.assertIn(
            "app.kubernetes.io/name=ingress-nginx,"
            "app.kubernetes.io/component=controller",
            script,
        )
        self.assertIn("socket.getaddrinfo", script)
        for argument in (
            "--release-manifest",
            "--release-bundle",
            "--release-evidence-dir",
        ):
            self.assertIn(argument, script)
        self.assertIn(
            'runtime_secret_name="archideal-runtime-secrets-$release_id"',
            script,
        )
        runtime_secret_ready = script.index(
            'wait_created_once_external_secret "$runtime_secret_name"'
        )
        self.assertNotIn(
            'force_and_wait_periodic_external_secret "$runtime_secret_name"',
            script,
        )
        self.assertIn(
            'patch "secret/$name" --type=merge --patch \'{"immutable":true}\'',
            " ".join(script.replace("\\\n", " ").split()),
        )
        self.assertIn("jsonpath='{.immutable}'", script)
        valkey_tls_gate = script.index("validate-valkey-url.py", runtime_secret_ready)
        private_dns_gate = script.index(
            'apply_file "$rendered/base/private-network-preflight.yaml"',
            valkey_tls_gate,
        )
        network_policy_mutation = script.index(
            'apply_file "$rendered/base/network-policies.yaml"'
        )
        migration_phase = script.index('apply_file "$rendered/base/jobs.yaml"')
        self.assertLess(runtime_secret_ready, valkey_tls_gate)
        self.assertLess(valkey_tls_gate, private_dns_gate)
        self.assertLess(private_dns_gate, network_policy_mutation)
        self.assertLess(valkey_tls_gate, migration_phase)
        self.assertIn("go-template='{{ index .data \"valkey-url\" }}'", script)
        ingest_token_extract = script.index(
            "dealdata-ingest-token",
            runtime_secret_ready,
        )
        production_smoke = script.index("--exercise-api-ingest")
        self.assertLess(runtime_secret_ready, ingest_token_extract)
        self.assertLess(ingest_token_extract, production_smoke)
        self.assertIn('(umask 077; : > "$ingest_token_file")', script)
        self.assertIn(
            'ARCHIDEAL_INGEST_TOKEN_FILE="$ingest_token_file"',
            script,
        )
        self.assertNotIn("--health-only", script)
        self.assertNotIn('ARCHIDEAL_INGEST_TOKEN_FILE="$(', script)
        self.assertIn(
            'apply_file "$rendered/overlays/production/synthetic-smoke.yaml"',
            script,
        )
        self.assertIn('"job/$apisix_bootstrap_job"', script)
        self.assertIn('"job/$private_network_preflight_job"', script)
        self.assertIn('"job/$kafka_preflight_job"', script)
        self.assertIn('"job/$production_smoke_job"', script)
        self.assertNotIn('"job/kafka-preflight-$release_id"', script)
        self.assertNotIn('"job/production-smoke-$release_id"', script)
        self.assertIn('--kafka "$rendered/base/preflight.yaml"', script)
        self.assertIn(
            '--private-network "$rendered/base/private-network-preflight.yaml"',
            script,
        )
        self.assertNotIn('smoke_device_id="archideal-smoke-$release_id"', script)
        self.assertIn('--device-id "$smoke_device_id"', script)
        self.assertIn(
            '--pods "$success_pods_json" --values "$values_file" '
            '--expected-release "$release_id"',
            " ".join(script.replace("\\\n", " ").split()),
        )
        self.assertNotIn('patch "$controller"', script)
        self.assertIn('apply_file "$controller_manifest"', script)
        self.assertLess(
            script.index('python "$script_dir/prepare-rollouts.py"'),
            script.index('for controller_name in "${controller_order[@]}"; do'),
        )

    def test_operator_production_smoke_runs_fresh_mqtt_and_database_gate(self) -> None:
        smoke = ROOT / "deploy/kubernetes/smoke-production.sh"
        self.assertTrue(os.access(smoke, os.X_OK))
        bash = bash_executable()
        self.assertIsNotNone(
            bash, "A Bash interpreter is required for shell syntax checks."
        )
        result = subprocess.run(
            [bash, "-n", str(smoke)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        script = smoke.read_text(encoding="utf-8")
        self.assertIn(
            'runtime_secret_name="archideal-runtime-secrets-$release_id"',
            script,
        )
        self.assertIn('"secret/$runtime_secret_name"', script)
        self.assertIn('python "$script_dir/prepare-invocation-jobs.py"', script)
        self.assertIn(
            '--synthetic "$rendered/overlays/production/synthetic-smoke.yaml"', script
        )
        self.assertIn('"job/$production_smoke_job"', script)
        self.assertIn('controllers_json="$work_dir/controllers.json"', script)
        self.assertIn('pods_json="$work_dir/pods.json"', script)
        self.assertIn('ingress_json="$work_dir/ingress.json"', script)
        self.assertIn('python "$script_dir/validate-release-coherence.py"', script)
        self.assertIn('--expected-release "$release_id"', script)
        self.assertIn('--values "$values_file"', script)
        self.assertIn('--ingress "$ingress_json"', script)
        self.assertIn("Refusing to reuse an existing production smoke Job", script)
        self.assertIn('python "$script_dir/validate-production-smoke-job.py"', script)
        self.assertIn("--exercise-api-ingest", script)
        self.assertIn('--device-id "$smoke_device_id"', script)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        production_smoke = makefile.split("production-smoke:", 1)[1]
        self.assertIn("deploy/kubernetes/smoke-production.sh", production_smoke)
        self.assertNotIn("python scripts/check-architecture.py", production_smoke)


if __name__ == "__main__":
    unittest.main()
