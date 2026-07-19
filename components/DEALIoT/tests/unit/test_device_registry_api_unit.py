from __future__ import annotations

import json
import sys
import threading
import unittest
from contextlib import contextmanager
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch
from urllib import error, request

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console import app  # noqa: E402


@contextmanager
def running_console_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.ManagementConsoleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def device(revision: int = 1) -> dict[str, object]:
    return {
        "device_id": "field-01",
        "display_name": "Field device",
        "kind": "sensor",
        "status": "active",
        "mqtt_topic": "devices/field-01/telemetry",
        "capabilities": ["temperature"],
        "settings": {"sample_interval_seconds": 60},
        "labels": {"site": "north"},
        "revision": revision,
        "created_at": "2026-07-19T00:00:00+00:00",
        "updated_at": "2026-07-19T00:00:00+00:00",
        "retired_at": None,
        "created_by": "operator-1",
        "updated_by": "operator-1",
    }


def json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(  # noqa: S310  # nosec B310
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    return request.urlopen(req, timeout=5)  # noqa: S310  # nosec B310


class DeviceRegistryApiUnitTests(unittest.TestCase):
    def test_readiness_requires_current_registry_schema_when_configured(self) -> None:
        dependency_checks = [
            {"id": "vernemq", "status": "healthy", "detail": "test"},
            {"id": "kafka", "status": "healthy", "detail": "test"},
        ]
        environment = {"DEALIOT_REGISTRY_DATABASE_HOST": "registry-db"}
        with (
            patch.dict("os.environ", environment, clear=True),
            patch(
                "management_console.app.required_component_checks",
                return_value=dependency_checks,
            ),
            patch("management_console.app.device_registry.check_readiness") as registry_check,
        ):
            status, payload = app.readiness_payload()

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["scope"]["required"], ["vernemq", "kafka", "dealiot-registry"])
        self.assertEqual(payload["checks"][-1]["status"], "healthy")
        registry_check.assert_called_once_with()

        with (
            patch.dict("os.environ", environment, clear=True),
            patch(
                "management_console.app.required_component_checks",
                return_value=dependency_checks,
            ),
            patch(
                "management_console.app.device_registry.check_readiness",
                side_effect=app.device_registry.RegistryUnavailableError("schema missing"),
            ),
        ):
            status, payload = app.readiness_payload()

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["checks"][-1]["status"], "unreachable")
        self.assertNotIn("schema missing", payload["checks"][-1]["detail"])

    def test_production_readiness_fails_closed_without_registry_configuration(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"MANAGEMENT_CONSOLE_PRODUCTION_MODE": "true"},
                clear=True,
            ),
            patch(
                "management_console.app.required_component_checks",
                return_value=[
                    {"id": "vernemq", "status": "healthy", "detail": "test"},
                    {"id": "kafka", "status": "healthy", "detail": "test"},
                ],
            ),
        ):
            status, payload = app.readiness_payload()

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["checks"][-1]["id"], "dealiot-registry")
        self.assertEqual(payload["checks"][-1]["status"], "unreachable")

    def test_crud_routes_preserve_public_prefix_and_etag_contract(self) -> None:
        first = device()
        second = device(revision=2)
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "management_console.app.device_registry.list_devices",
                return_value={"devices": [first], "next_cursor": None},
            ) as list_devices,
            patch(
                "management_console.app.device_registry.get_device",
                return_value=first,
            ),
            patch(
                "management_console.app.device_registry.create_device",
                return_value=first,
            ) as create_device,
            patch(
                "management_console.app.device_registry.update_device",
                return_value=second,
            ) as update_device,
            patch(
                "management_console.app.device_registry.retire_device",
                return_value=3,
            ) as retire_device,
            running_console_server() as base_url,
        ):
            with json_request(f"{base_url}/dealiot/api/devices?status=active&limit=10") as response:
                listed = json.loads(response.read())
            self.assertEqual(listed["devices"][0]["device_id"], "field-01")
            list_devices.assert_called_once_with(
                status="active",
                kind=None,
                query=None,
                limit=10,
                cursor=None,
            )

            with json_request(
                f"{base_url}/dealiot/api/devices",
                method="POST",
                payload={"device_id": "field-01"},
            ) as response:
                self.assertEqual(response.status, HTTPStatus.CREATED)
                self.assertEqual(response.headers["ETag"], '"1"')
                self.assertEqual(
                    response.headers["Location"],
                    "/dealiot/api/devices/field-01",
                )
            create_device.assert_called_once_with(
                {"device_id": "field-01"},
                "development-user",
            )

            with json_request(f"{base_url}/dealiot/api/devices/field-01") as response:
                detail = json.loads(response.read())
                self.assertEqual(response.headers["ETag"], '"1"')
            self.assertEqual(detail["device"]["kind"], "sensor")

            with self.assertRaises(error.HTTPError) as missing_match:
                json_request(
                    f"{base_url}/dealiot/api/devices/field-01",
                    method="PATCH",
                    payload={"status": "suspended"},
                )
            self.assertEqual(missing_match.exception.code, HTTPStatus.PRECONDITION_REQUIRED)

            with json_request(
                f"{base_url}/dealiot/api/devices/field-01",
                method="PATCH",
                payload={"status": "suspended"},
                headers={"If-Match": '"1"'},
            ) as response:
                self.assertEqual(response.headers["ETag"], '"2"')
            update_device.assert_called_once_with(
                "field-01",
                {"status": "suspended"},
                "development-user",
                1,
            )

            with self.assertRaises(error.HTTPError) as delete_with_body:
                json_request(
                    f"{base_url}/dealiot/api/devices/field-01",
                    method="DELETE",
                    payload={"unexpected": True},
                    headers={"If-Match": '"2"'},
                )
            self.assertEqual(delete_with_body.exception.code, HTTPStatus.BAD_REQUEST)
            retire_device.assert_not_called()

            with json_request(
                f"{base_url}/dealiot/api/devices/field-01",
                method="DELETE",
                headers={"If-Match": '"2"'},
            ) as response:
                self.assertEqual(response.status, HTTPStatus.NO_CONTENT)
                self.assertEqual(response.headers["ETag"], '"3"')
            retire_device.assert_called_once_with("field-01", "development-user", 2)

    def test_device_routes_distinguish_unauthenticated_and_forbidden(self) -> None:
        environment = {
            "MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL": "https://identity.test/introspect"
        }

        def read_only_principal(authorization: str | None):
            if authorization is None:
                return None
            return app.Principal(
                subject="reader-1",
                roles=frozenset({"dealiot-read"}),
                level="read",
            )

        with (
            patch.dict("os.environ", environment, clear=True),
            patch(
                "management_console.app.authenticated_principal",
                side_effect=read_only_principal,
            ),
            running_console_server() as base_url,
        ):
            with self.assertRaises(error.HTTPError) as unauthorized:
                json_request(f"{base_url}/dealiot/api/devices")
            self.assertEqual(unauthorized.exception.code, HTTPStatus.UNAUTHORIZED)

            with self.assertRaises(error.HTTPError) as forbidden:
                json_request(
                    f"{base_url}/dealiot/api/devices",
                    method="POST",
                    payload={"device_id": "field-01"},
                    headers={"Authorization": "Bearer reader-token"},
                )
            self.assertEqual(forbidden.exception.code, HTTPStatus.FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
