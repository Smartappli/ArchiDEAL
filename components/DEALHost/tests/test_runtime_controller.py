from unittest.mock import patch

import httpx
from django.test import SimpleTestCase

from apps.hosting.runtime_controller import (
    RuntimeControllerClient,
    RuntimeControllerError,
    _snapshot,
)
from dealhost.settings.env import RuntimeControllerConfig


class RecordingHttpClient:
    response = httpx.Response(
        200,
        json={"lines": ["ready"], "cursor": "cursor-1", "truncated": False},
    )
    client_options: dict[str, object] = {}
    request_options: dict[str, object] = {}

    def __init__(self, **kwargs) -> None:
        type(self).client_options = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def request(self, method, path, **kwargs):
        type(self).request_options = {
            "method": method,
            "path": path,
            **kwargs,
        }
        return type(self).response


class RuntimeControllerClientTests(SimpleTestCase):
    def setUp(self) -> None:
        self.config = RuntimeControllerConfig(
            base_url="https://runtime-controller.internal",
            token="controller-test-token",  # nosec B106 - test fixture.
            timeout_seconds=5,
            ca_file="/var/run/runtime-controller-ca/ca.crt",
        )

    @patch("apps.hosting.runtime_controller.httpx.Client", RecordingHttpClient)
    def test_log_contract_forwards_component_window_and_safe_http_options(self) -> None:
        result = RuntimeControllerClient(self.config).logs(
            "controller-runtime-1",
            component="runtime-api",
            tail=200,
            since_seconds=3600,
            request_id="operation-123",
        )

        self.assertEqual(result.lines, ("ready",))
        self.assertFalse(RecordingHttpClient.client_options["follow_redirects"])
        self.assertFalse(RecordingHttpClient.client_options["trust_env"])
        self.assertEqual(
            RecordingHttpClient.client_options["verify"],
            "/var/run/runtime-controller-ca/ca.crt",
        )
        self.assertEqual(
            RecordingHttpClient.request_options["params"],
            {
                "component": "runtime-api",
                "tail": 200,
                "since_seconds": 3600,
            },
        )
        headers = RecordingHttpClient.request_options["headers"]
        self.assertEqual(headers["Authorization"], "Bearer controller-test-token")
        self.assertEqual(headers["Idempotency-Key"], "operation-123")

    def test_rejects_unsafe_controller_and_component_identifiers(self) -> None:
        client = RuntimeControllerClient(self.config)

        with self.assertRaises(RuntimeControllerError):
            client.logs(
                "../../deployment",
                component="runtime-api",
                tail=10,
                since_seconds=60,
                request_id="operation-123",
            )
        with self.assertRaises(RuntimeControllerError):
            client.logs(
                "controller-runtime-1",
                component="../other",
                tail=10,
                since_seconds=60,
                request_id="operation-123",
            )

    def test_snapshot_rejects_an_inconsistent_identifier(self) -> None:
        with self.assertRaisesMessage(
            RuntimeControllerError,
            "inconsistent deployment identifier",
        ):
            _snapshot(
                {
                    "id": "another-runtime",
                    "state": "running",
                    "observed_generation": 1,
                    "components": [],
                },
                expected_id="expected-runtime",
            )

    def test_snapshot_rejects_duplicate_component_slugs(self) -> None:
        component = {
            "slug": "runtime-api",
            "image_digest": "ghcr.io/smartappli/runtime@sha256:" + "a" * 64,
            "desired_replicas": 1,
            "ready_replicas": 1,
            "available_replicas": 1,
            "state": "running",
            "health": "healthy",
            "restart_count": 0,
        }

        with self.assertRaisesMessage(
            RuntimeControllerError,
            "duplicate runtime components",
        ):
            _snapshot(
                {
                    "id": "expected-runtime",
                    "state": "running",
                    "observed_generation": 1,
                    "components": [component, dict(component)],
                },
                expected_id="expected-runtime",
            )
