from __future__ import annotations

import io
import ipaddress
import json
import sys
import threading
import unittest
from contextlib import contextmanager
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Self, cast
from unittest.mock import Mock, patch
from urllib import error, request
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console import app  # noqa: E402


class FakeResponse:
    def __init__(self, status: int = HTTPStatus.OK, body: bytes = b"{}") -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self.body


class FakeBodyHandler:
    def __init__(self, body: bytes, length: int | None = None) -> None:
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length)}


def open_test_http_url(url_or_request: str | request.Request):
    url = url_or_request.full_url if isinstance(url_or_request, request.Request) else url_or_request
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("test URL must use http or https")
    # Test helper validates the scheme above before exercising the local HTTP server.
    return request.urlopen(url_or_request, timeout=5)  # noqa: S310  # nosec B310


@contextmanager
def running_console_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.ManagementConsoleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def read_json(url: str) -> dict[str, object]:
    with open_test_http_url(url) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("Expected JSON object response")
    return cast("dict[str, object]", parsed)


class ManagementConsoleAppUnitTests(unittest.TestCase):
    def test_timeout_seconds_clamps_and_handles_invalid_values(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(app.timeout_seconds(), app.DEFAULT_TIMEOUT_SECONDS)

        for value, expected in [("0.01", 0.2), ("30", 10.0), ("invalid", 2.0)]:
            with patch.dict("os.environ", {"MANAGEMENT_CONSOLE_PROBE_TIMEOUT_SECONDS": value}):
                self.assertEqual(app.timeout_seconds(), expected)

    def test_probe_tcp_reports_invalid_healthy_and_unreachable_states(self) -> None:
        self.assertEqual(app.probe_tcp("tcp://missing-port", 0.1)["status"], "unknown")

        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=None)
        with patch("management_console.app.socket.create_connection", return_value=connection):
            result = app.probe_tcp("tcp://example.net:9092", 0.1)
        self.assertEqual(result, {"status": "healthy", "detail": "tcp:example.net:9092"})

        with patch(
            "management_console.app.socket.create_connection",
            side_effect=OSError("offline"),
        ):
            result = app.probe_tcp("tcp://example.net:9092", 0.1)
        self.assertEqual(result["status"], "unreachable")
        self.assertIn("offline", result["detail"])

    def test_probe_http_reports_status_classes_and_errors(self) -> None:
        self.assertEqual(app.probe_http("ftp://example.net", 0.1)["status"], "unknown")
        self.assertEqual(app.probe_http("https://user@example.net", 0.1)["status"], "unknown")

        with patch("management_console.app.open_http_request", return_value=FakeResponse(204)):
            self.assertEqual(app.probe_http("https://example.net", 0.1)["status"], "healthy")
        with patch("management_console.app.open_http_request", return_value=FakeResponse(503)):
            self.assertEqual(app.probe_http("https://example.net", 0.1)["status"], "degraded")

        with patch("management_console.app.open_http_request", return_value=FakeResponse(404)):
            self.assertEqual(app.probe_http("https://example.net", 0.1)["status"], "healthy")
        with patch("management_console.app.open_http_request", return_value=FakeResponse(500)):
            self.assertEqual(app.probe_http("https://example.net", 0.1)["status"], "degraded")
        with patch("management_console.app.open_http_request", side_effect=OSError("offline")):
            self.assertEqual(app.probe_http("https://example.net", 0.1)["status"], "unreachable")

    def test_parse_http_url_rejects_non_http_credentials_and_fragments(self) -> None:
        self.assertEqual(app.parse_http_url("https://example.net/health").hostname, "example.net")

        for value in (
            "ftp://example.net/health",
            "file:///etc/passwd",
            "https://user:pass@example.net/health",
            "https://example.net/health#token",
            "/relative",
        ):
            with self.assertRaises(ValueError):
                app.parse_http_url(value)

    def test_runtime_probe_overrides_cover_registered_components(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(app.mqtt_probe())
            self.assertIsNone(app.kafka_probe())
            self.assertIsNone(app.apicurio_probe())
            self.assertIsNone(app.endpoint_probe("MISSING_URL"))
            self.assertEqual(
                app.configured_probe({"id": "unknown", "probe": "tcp://fallback:1"}),
                "tcp://fallback:1",
            )

        with patch.dict("os.environ", {"KAFKA_BOOTSTRAP_SERVERS": ", ,"}, clear=True):
            self.assertIsNone(app.kafka_probe())

        with patch.dict(
            "os.environ",
            {
                "APICURIO_REGISTRY_URL": "https://apicurio.example/api",
                "MQTT_KAFKA_BRIDGE_HEALTH_URL": "https://bridge.example/readyz",
                "S3_ENDPOINT_URL": "https://s3.example",
                "FLINK_REST_URL": "https://flink.example",
                "PROMETHEUS_URL": "https://prometheus.example",
                "GRAFANA_URL": "https://grafana.example",
            },
            clear=True,
        ):
            self.assertEqual(
                app.configured_probe({"id": "mqtt-kafka-bridge", "probe": None}),
                "https://bridge.example/readyz",
            )
            self.assertEqual(
                app.configured_probe({"id": "apicurio", "probe": None}),
                "https://apicurio.example/api/system/info",
            )
            self.assertEqual(
                app.configured_probe({"id": "seaweedfs", "probe": None}),
                "https://s3.example",
            )
            self.assertEqual(
                app.configured_probe({"id": "flink", "probe": None}),
                "https://flink.example/overview",
            )
            self.assertEqual(
                app.configured_probe({"id": "prometheus", "probe": None}),
                "https://prometheus.example/-/ready",
            )
            self.assertEqual(
                app.configured_probe({"id": "grafana", "probe": None}),
                "https://grafana.example/api/health",
            )

        with patch.dict(
            "os.environ",
            {"APICURIO_REGISTRY_HEALTH_URL": "https://apicurio.example/health"},
            clear=True,
        ):
            self.assertEqual(
                app.configured_probe({"id": "apicurio", "probe": None}),
                "https://apicurio.example/health",
            )

    def test_probe_component_and_health_payload_summarize_checks(self) -> None:
        no_probe = app.probe_component({"id": "manual", "probe": None})
        self.assertEqual(no_probe["status"], "unknown")

        with (
            patch("management_console.app.configured_probe", return_value="tcp://broker:9092"),
            patch(
                "management_console.app.probe_tcp",
                return_value={"status": "healthy", "detail": "tcp"},
            ),
        ):
            result = app.probe_component({"id": "kafka"})
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["detail"], "tcp")

        with (
            patch("management_console.app.configured_probe", return_value="https://service/health"),
            patch(
                "management_console.app.probe_http",
                return_value={"status": "degraded", "detail": "http 503"},
            ),
        ):
            result = app.probe_component({"id": "service"})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["detail"], "http 503")

        components = [{"id": "healthy"}, {"id": "offline"}, {"id": "offline-2"}]

        def fake_probe(component: dict[str, str]) -> dict[str, str]:
            status = "healthy" if component["id"] == "healthy" else "unreachable"
            return {"id": component["id"], "status": status, "detail": "test"}

        with (
            patch("management_console.app.COMPONENTS", components),
            patch("management_console.app.probe_component", side_effect=fake_probe),
            patch.dict("os.environ", {}, clear=True),
        ):
            payload = app.health_payload()
        self.assertEqual(payload["summary"], {"healthy": 1, "unreachable": 2})
        self.assertEqual(len(payload["checks"]), 3)

    def test_health_payload_separates_required_optional_and_excluded_components(self) -> None:
        components = [
            {"id": "required"},
            {"id": "optional"},
            {"id": "not-deployed"},
        ]

        def fake_probe(component: dict[str, str]) -> dict[str, str]:
            status = "unreachable" if component["id"] == "required" else "healthy"
            return {"id": component["id"], "status": status, "detail": "test"}

        with (
            patch("management_console.app.COMPONENTS", components),
            patch("management_console.app.probe_component", side_effect=fake_probe) as probe,
            patch.dict(
                "os.environ",
                {
                    "MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS": "required",
                    "MANAGEMENT_CONSOLE_OPTIONAL_COMPONENT_IDS": "optional,required",
                },
                clear=True,
            ),
        ):
            payload = app.health_payload()

        self.assertEqual(payload["summary"], {"unreachable": 1})
        self.assertEqual(payload["optional_summary"], {"healthy": 1})
        self.assertEqual([check["id"] for check in payload["checks"]], ["required"])
        self.assertEqual([check["id"] for check in payload["optional_checks"]], ["optional"])
        self.assertEqual(
            payload["scope"],
            {
                "required": ["required"],
                "optional": ["optional"],
                "excluded": ["not-deployed"],
            },
        )
        self.assertEqual(probe.call_count, 2)

    def test_unknown_required_component_fails_closed(self) -> None:
        with (
            patch("management_console.app.COMPONENTS", [{"id": "known"}]),
            patch.dict(
                "os.environ",
                {"MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS": "configuration-typo"},
                clear=True,
            ),
        ):
            payload = app.health_payload()

        self.assertEqual(payload["summary"], {"unknown": 1})
        self.assertEqual(payload["checks"][0]["id"], "configuration-typo")
        self.assertEqual(payload["checks"][0]["detail"], "no probe configured")

    def test_empty_required_component_scope_fails_closed(self) -> None:
        with (
            patch("management_console.app.COMPONENTS", [{"id": "known"}]),
            patch.dict(
                "os.environ",
                {"MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS": " , "},
                clear=True,
            ),
        ):
            payload = app.health_payload()

        self.assertEqual(payload["summary"], {"unknown": 1})
        self.assertEqual(payload["scope"]["required"], [])
        self.assertEqual(payload["checks"][0]["id"], "management-console-health-scope")
        self.assertIn("must not be empty", payload["checks"][0]["detail"])

    def test_readiness_requires_healthy_mqtt_and_kafka(self) -> None:
        components = [{"id": "vernemq"}, {"id": "kafka"}]

        def fake_probe(component: dict[str, str]) -> dict[str, str]:
            return {
                "id": component["id"],
                "status": "healthy" if component["id"] == "vernemq" else "unreachable",
                "detail": "test",
            }

        with (
            patch("management_console.app.COMPONENTS", components),
            patch("management_console.app.probe_component", side_effect=fake_probe),
            patch.dict("os.environ", {}, clear=True),
        ):
            status, payload = app.readiness_payload()
        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["status"], "not_ready")

        with (
            patch("management_console.app.COMPONENTS", components),
            patch(
                "management_console.app.probe_component",
                side_effect=lambda component: {
                    "id": component["id"],
                    "status": "healthy",
                    "detail": "test",
                },
            ),
            patch.dict("os.environ", {}, clear=True),
        ):
            status, payload = app.readiness_payload()
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["status"], "ready")

    def test_readiness_uses_explicit_required_scope_including_bridge(self) -> None:
        components = [
            {"id": "vernemq"},
            {"id": "mqtt-kafka-bridge"},
            {"id": "kafka"},
        ]

        def fake_probe(component: dict[str, str]) -> dict[str, str]:
            return {
                "id": component["id"],
                "status": (
                    "unreachable" if component["id"] == "mqtt-kafka-bridge" else "healthy"
                ),
                "detail": "test",
            }

        with (
            patch("management_console.app.COMPONENTS", components),
            patch("management_console.app.probe_component", side_effect=fake_probe),
            patch.dict(
                "os.environ",
                {
                    "MANAGEMENT_CONSOLE_REQUIRED_COMPONENT_IDS": (
                        "vernemq,mqtt-kafka-bridge,kafka"
                    )
                },
                clear=True,
            ),
        ):
            status, payload = app.readiness_payload()

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(
            payload["scope"]["required"],
            ["vernemq", "mqtt-kafka-bridge", "kafka"],
        )
        self.assertEqual(
            {check["id"] for check in payload["checks"]},
            {"vernemq", "mqtt-kafka-bridge", "kafka"},
        )

    def test_airflow_trigger_handles_credentials_url_success_and_failures(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            status, payload = app.trigger_media_backfill({})
        self.assertEqual(status, HTTPStatus.CONFLICT)
        self.assertEqual(payload["error"], "missing_airflow_credentials")

        with patch.dict(
            "os.environ",
            {
                "AIRFLOW_API_USERNAME": "u",
                "AIRFLOW_API_PASSWORD": "p",
                "AIRFLOW_API_URL": "ftp://airflow",
            },
            clear=True,
        ):
            status, payload = app.trigger_media_backfill({})
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"], "invalid_airflow_api_url")

        with patch.dict(
            "os.environ",
            {
                "AIRFLOW_API_USERNAME": "u",
                "AIRFLOW_API_PASSWORD": "p",
                "AIRFLOW_API_URL": "https://user:pass@airflow.example/api/v2",
            },
            clear=True,
        ):
            status, payload = app.trigger_media_backfill({})
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"], "invalid_airflow_api_url")

        response_body = b'{"dag_run_id":"manual"}'
        with (
            patch.dict(
                "os.environ",
                {
                    "AIRFLOW_API_USERNAME": "u",
                    "AIRFLOW_API_PASSWORD": "p",
                    "AIRFLOW_API_URL": "https://airflow.example/api/v2",
                },
                clear=True,
            ),
            patch(
                "management_console.app.open_http_request",
                return_value=FakeResponse(200, response_body),
            ),
        ):
            status, payload = app.trigger_media_backfill({"dag_run_id": "manual"})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["status"], "submitted")

        with (
            patch.dict(
                "os.environ",
                {"AIRFLOW_API_USERNAME": "u", "AIRFLOW_API_PASSWORD": "p"},
                clear=True,
            ),
            patch(
                "management_console.app.open_http_request",
                return_value=FakeResponse(409, b"already exists"),
            ),
        ):
            status, payload = app.trigger_media_backfill({})
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "airflow_rejected_request")

        with (
            patch.dict(
                "os.environ",
                {"AIRFLOW_API_USERNAME": "u", "AIRFLOW_API_PASSWORD": "p"},
                clear=True,
            ),
            patch("management_console.app.open_http_request", side_effect=OSError("offline")),
        ):
            status, payload = app.trigger_media_backfill({})
        self.assertEqual(status, HTTPStatus.BAD_GATEWAY)
        self.assertEqual(payload["error"], "airflow_unreachable")

    def test_read_json_body_validates_shape_and_size(self) -> None:
        self.assertEqual(app.read_json_body(FakeBodyHandler(b"")), {})
        self.assertEqual(app.read_json_body(FakeBodyHandler(b'{"a":1}')), {"a": 1})

        with self.assertRaises(TypeError):
            app.read_json_body(FakeBodyHandler(b'["not", "object"]'))
        with self.assertRaises(ValueError):
            app.read_json_body(FakeBodyHandler(b"{}", app.MAX_REQUEST_BYTES + 1))

    def test_configured_bind_host_rejects_wildcard_without_explicit_opt_in(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(app.configured_bind_host(), "127.0.0.1")

        wildcard_ipv4 = str(ipaddress.IPv4Address(0))
        with (
            patch.dict("os.environ", {"MANAGEMENT_CONSOLE_BIND": wildcard_ipv4}, clear=True),
            self.assertRaisesRegex(ValueError, "Wildcard bind requires"),
        ):
            app.configured_bind_host()

        with patch.dict(
            "os.environ",
            {
                "MANAGEMENT_CONSOLE_BIND": "::",
                "MANAGEMENT_CONSOLE_ALLOW_WILDCARD_BIND": "true",
            },
            clear=True,
        ):
            self.assertEqual(app.configured_bind_host(), "::")

    def test_http_handler_serves_api_static_post_and_errors(self) -> None:
        with patch.dict("os.environ", {}, clear=True), running_console_server() as base_url:
            health = read_json(f"{base_url}/healthz")
            self.assertEqual(health["status"], "ok")

            zenodo_config = read_json(f"{base_url}/api/datasets/zenodo")
            self.assertEqual(zenodo_config["repository"], "Zenodo")

            openaire_config = read_json(f"{base_url}/api/datasets/openaire")
            self.assertEqual(openaire_config["catalogue"], "OpenAIRE")
            self.assertFalse(openaire_config["direct_upload_supported"])

            legal_compliance = read_json(f"{base_url}/api/legal-compliance")
            default_policy = legal_compliance["default_policy"]
            if not isinstance(default_policy, dict):
                raise TypeError("Expected default_policy to be a JSON object")
            self.assertEqual(
                default_policy["legal_verdict"],
                "reviewable baseline, not legal certification",
            )
            self.assertIn("finalization_items", legal_compliance)

            with open_test_http_url(f"{base_url}/") as response:
                html = response.read().decode("utf-8")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("DEALIoT Management Console", html)

            with self.assertRaises(error.HTTPError) as not_found:
                open_test_http_url(f"{base_url}/missing")
            self.assertEqual(not_found.exception.code, HTTPStatus.NOT_FOUND)

            post = request.Request(  # noqa: S310
                f"{base_url}/api/operations/trigger-media-backfill",
                data=b"[]",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(error.HTTPError) as bad_request:
                open_test_http_url(post)
            self.assertEqual(bad_request.exception.code, HTTPStatus.BAD_REQUEST)

            with patch(
                "management_console.app.trigger_media_backfill",
                return_value=(HTTPStatus.ACCEPTED, {"status": "queued"}),
            ):
                post = request.Request(  # noqa: S310
                    f"{base_url}/api/operations/trigger-media-backfill",
                    data=b'{"conf":{"limit":1}}',
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                response = read_json_from_request(post)
            self.assertEqual(response["status"], "queued")

            with patch(
                "management_console.app.export_dataset_to_zenodo",
                return_value={"status": "draft_created", "dataset_id": "dataset"},
            ):
                post = request.Request(  # noqa: S310
                    f"{base_url}/api/datasets/zenodo/export",
                    data=b'{"dataset_id":"dataset.telemetry.sensor-minimised"}',
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                response = read_json_from_request(post)
            self.assertEqual(response["status"], "draft_created")

            with patch(
                "management_console.app.export_dataset_to_openaire",
                return_value={"status": "metadata_package_created", "dataset_id": "dataset"},
            ):
                post = request.Request(  # noqa: S310
                    f"{base_url}/api/datasets/openaire/export",
                    data=b'{"dataset_id":"dataset.telemetry.sensor-minimised"}',
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                response = read_json_from_request(post)
            self.assertEqual(response["status"], "metadata_package_created")

            with patch(
                "management_console.app.export_dataset_to_zenodo",
                side_effect=app.ZenodoExportError(
                    HTTPStatus.CONFLICT,
                    "missing_zenodo_token",
                    "Set ZENODO_ACCESS_TOKEN before exporting to Zenodo.",
                ),
            ):
                post = request.Request(  # noqa: S310
                    f"{base_url}/api/datasets/zenodo/export",
                    data=b'{"dataset_id":"dataset.telemetry.sensor-minimised"}',
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(error.HTTPError) as blocked:
                    open_test_http_url(post)
            self.assertEqual(blocked.exception.code, HTTPStatus.CONFLICT)

    def test_http_handler_requires_bearer_token_when_configured(self) -> None:
        with (
            patch.dict("os.environ", {"MANAGEMENT_CONSOLE_TOKEN": "unit-token"}, clear=True),
            running_console_server() as base_url,
        ):
            health = read_json(f"{base_url}/healthz")
            self.assertEqual(health["status"], "ok")

            with self.assertRaises(error.HTTPError) as unauthorized_get:
                open_test_http_url(f"{base_url}/api/datasets/zenodo")
            self.assertEqual(unauthorized_get.exception.code, HTTPStatus.UNAUTHORIZED)

            get_request = request.Request(  # noqa: S310
                f"{base_url}/api/datasets/zenodo",
                headers={"Authorization": "Bearer unit-token"},
            )
            response = read_json_from_request(get_request)
            self.assertEqual(response["repository"], "Zenodo")

            post = request.Request(  # noqa: S310
                f"{base_url}/api/operations/trigger-media-backfill",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(error.HTTPError) as unauthorized_post:
                open_test_http_url(post)
            self.assertEqual(unauthorized_post.exception.code, HTTPStatus.UNAUTHORIZED)

            with patch(
                "management_console.app.trigger_media_backfill",
                return_value=(HTTPStatus.ACCEPTED, {"status": "queued"}),
            ):
                authorized_post = request.Request(  # noqa: S310
                    f"{base_url}/api/operations/trigger-media-backfill",
                    data=b"{}",
                    method="POST",
                    headers={
                        "Authorization": "Bearer unit-token",
                        "Content-Type": "application/json",
                    },
                )
                response = read_json_from_request(authorized_post)
            self.assertEqual(response["status"], "queued")

    def test_unified_dealiot_prefix_serves_ui_assets_and_api(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            running_console_server() as base_url,
        ):
            with open_test_http_url(f"{base_url}/dealiot") as response:
                html = response.read().decode("utf-8")
            self.assertIn('href="/dealiot/styles.css"', html)
            self.assertIn('src="/dealiot/app.js"', html)

            with open_test_http_url(f"{base_url}/dealiot/app.js") as response:
                javascript = response.read().decode("utf-8")
            self.assertIn('publicBasePath = "/dealiot"', javascript)

            architecture = read_json(f"{base_url}/dealiot/api/architecture")
            self.assertIn("components", architecture)

    def test_production_mode_allows_only_anonymous_health_without_auth_config(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"MANAGEMENT_CONSOLE_PRODUCTION_MODE": "true"},
                clear=True,
            ),
            patch(
                "management_console.app.readiness_payload",
                return_value=(HTTPStatus.OK, {"status": "ready"}),
            ),
            running_console_server() as base_url,
        ):
            health = read_json(f"{base_url}/healthz")
            self.assertEqual(health["status"], "ok")
            readiness = read_json(f"{base_url}/readyz")
            self.assertEqual(readiness["status"], "ready")

            for path in ("/", "/app.js", "/api/datasets/zenodo"):
                with self.subTest(path=path), self.assertRaises(error.HTTPError) as blocked:
                    open_test_http_url(f"{base_url}{path}")
                self.assertEqual(blocked.exception.code, HTTPStatus.UNAUTHORIZED)

            post = request.Request(  # noqa: S310
                f"{base_url}/api/operations/trigger-media-backfill",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(error.HTTPError) as blocked_post:
                open_test_http_url(post)
            self.assertEqual(blocked_post.exception.code, HTTPStatus.UNAUTHORIZED)

    def test_production_mode_accepts_configured_bearer_for_static_and_api_routes(self) -> None:
        environment = {
            "MANAGEMENT_CONSOLE_PRODUCTION_MODE": "true",
            "MANAGEMENT_CONSOLE_TOKEN": "unit-token",
        }
        with (
            patch.dict("os.environ", environment, clear=True),
            running_console_server() as base_url,
        ):
            for path in ("/", "/api/datasets/zenodo"):
                with self.subTest(path=path):
                    authorized = request.Request(  # noqa: S310
                        f"{base_url}{path}",
                        headers={"Authorization": "Bearer unit-token"},
                    )
                    with open_test_http_url(authorized) as response:
                        self.assertEqual(response.status, HTTPStatus.OK)
                        self.assertEqual(
                            response.headers["Strict-Transport-Security"],
                            "max-age=31536000; includeSubDomains",
                        )

    def test_oidc_introspection_maps_read_and_write_roles(self) -> None:
        active_read = app.SimpleHttpResponse(
            HTTPStatus.OK,
            b'{"active":true,"iss":"https://identity.test","aud":"archideal",'
            b'"realm_access":{"roles":["dealiot-read"]}}',
        )
        active_write = app.SimpleHttpResponse(
            HTTPStatus.OK,
            b'{"active":true,"iss":"https://identity.test","aud":["archideal"],'
            b'"roles":["dealiot-write"]}',
        )
        oidc_env = {
            "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL": "https://identity.test/introspect",
            "MANAGEMENT_CONSOLE_OIDC_ISSUER": "https://identity.test",
            "MANAGEMENT_CONSOLE_OIDC_AUDIENCE": "archideal",
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_ID": "console",
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET": "secret",
        }

        with (
            patch.dict("os.environ", oidc_env, clear=True),
            patch("management_console.app.open_http_request", return_value=active_read),
        ):
            self.assertEqual(app.authorization_level("Bearer read-token"), "read")

        with (
            patch.dict("os.environ", oidc_env, clear=True),
            patch("management_console.app.open_http_request", return_value=active_write),
        ):
            self.assertEqual(app.authorization_level("Bearer write-token"), "write")

    def test_oidc_groups_claim_maps_to_console_roles(self) -> None:
        active_operator = app.SimpleHttpResponse(
            HTTPStatus.OK,
            b'{"active":true,"iss":"https://identity.test","aud":"archideal",'
            b'"groups":["archideal-operators"]}',
        )
        oidc_env = {
            "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL": (
                "https://identity.test/introspect"
            ),
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_ID": "console",
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET": "secret",
            "MANAGEMENT_CONSOLE_OIDC_ISSUER": "https://identity.test",
            "MANAGEMENT_CONSOLE_OIDC_AUDIENCE": "archideal",
            "MANAGEMENT_CONSOLE_OIDC_READ_ROLES": "archideal-operators",
            "MANAGEMENT_CONSOLE_OIDC_WRITE_ROLES": "archideal-operators",
        }

        with (
            patch.dict("os.environ", oidc_env, clear=True),
            patch(
                "management_console.app.open_http_request",
                return_value=active_operator,
            ),
        ):
            self.assertEqual(app.authorization_level("Bearer id-token"), "write")

    def test_oidc_introspection_rejects_wrong_issuer_or_audience(self) -> None:
        oidc_env = {
            "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL": "https://identity.test/introspect",
            "MANAGEMENT_CONSOLE_OIDC_ISSUER": "https://identity.test",
            "MANAGEMENT_CONSOLE_OIDC_AUDIENCE": "archideal",
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_ID": "console",
            "MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET": "secret",
            "MANAGEMENT_CONSOLE_OIDC_READ_ROLES": "archideal-operators",
        }
        wrong_issuer = app.SimpleHttpResponse(
            HTTPStatus.OK,
            b'{"active":true,"iss":"https://evil.test","aud":"archideal",'
            b'"groups":["archideal-operators"]}',
        )
        wrong_audience = app.SimpleHttpResponse(
            HTTPStatus.OK,
            b'{"active":true,"iss":"https://identity.test","aud":"other",'
            b'"groups":["archideal-operators"]}',
        )

        for response in (wrong_issuer, wrong_audience):
            with (
                self.subTest(response=response.body),
                patch.dict("os.environ", oidc_env, clear=True),
                patch("management_console.app.open_http_request", return_value=response),
            ):
                self.assertIsNone(app.authorization_level("Bearer id-token"))

    def test_production_auth_validation_rejects_incomplete_oidc(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {
                    "MANAGEMENT_CONSOLE_PRODUCTION_MODE": "true",
                    "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL": (
                        "https://identity.test/introspect"
                    ),
                },
                clear=True,
            ),
            self.assertRaisesRegex(RuntimeError, "Incomplete production"),
        ):
            app.validate_production_auth_config()

    def test_run_uses_configured_bind_and_port(self) -> None:
        fake_server = Mock()
        fake_server.__enter__ = Mock(return_value=fake_server)
        fake_server.__exit__ = Mock(return_value=None)

        with (
            patch.dict(
                "os.environ",
                {"MANAGEMENT_CONSOLE_BIND": "127.0.0.1", "MANAGEMENT_CONSOLE_PORT": "8181"},
            ),
            patch("management_console.app.ThreadingHTTPServer", return_value=fake_server) as ctor,
            patch("builtins.print"),
        ):
            app.run()

        ctor.assert_called_once_with(("127.0.0.1", 8181), app.ManagementConsoleHandler)
        fake_server.serve_forever.assert_called_once()


def read_json_from_request(req: request.Request) -> dict[str, object]:
    with open_test_http_url(req) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("Expected JSON object response")
    return cast("dict[str, object]", parsed)


if __name__ == "__main__":
    unittest.main()
