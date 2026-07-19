from __future__ import annotations

import importlib.util
import io
from http import HTTPStatus
from pathlib import Path
import unittest
from unittest import mock
from urllib import error


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/check-device-registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_device_registry", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the device registry check module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckDeviceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = load_module()

    def test_expected_http_error_is_returned_as_json_contract(self) -> None:
        response = error.HTTPError(
            "http://archideal.test/dealiot/api/devices/device-1",
            HTTPStatus.PRECONDITION_FAILED,
            "Precondition Failed",
            {"Content-Type": "application/json"},
            io.BytesIO(b'{"error":"device_revision_conflict"}'),
        )
        with mock.patch.object(
            self.check.NO_REDIRECT_OPENER, "open", side_effect=response
        ):
            status, payload, _headers = self.check.json_request(
                response.url,
                method="PATCH",
                expected_error_status=HTTPStatus.PRECONDITION_FAILED,
            )

        self.assertEqual(status, HTTPStatus.PRECONDITION_FAILED)
        self.assertEqual(payload, {"error": "device_revision_conflict"})

    def test_redirects_are_rejected_before_an_operator_bearer_can_be_forwarded(
        self,
    ) -> None:
        redirect = error.HTTPError(
            "https://archideal.test/dealiot/api/devices",
            HTTPStatus.FOUND,
            "Found",
            {"Location": "https://attacker.example/collect"},
            io.BytesIO(b"redirect"),
        )
        with (
            mock.patch.object(
                self.check.NO_REDIRECT_OPENER,
                "open",
                side_effect=redirect,
            ) as open_mock,
            self.assertRaisesRegex(RuntimeError, "HTTP 302"),
        ):
            self.check.json_request(
                redirect.url,
                headers={"Authorization": "Bearer opaque-test-token"},
            )

        sent_request = open_mock.call_args.args[0]
        self.assertEqual(
            sent_request.get_header("Authorization"),
            "Bearer opaque-test-token",
        )
        self.assertIsNone(
            self.check.RejectRedirects().redirect_request(
                sent_request,
                None,
                HTTPStatus.FOUND,
                "Found",
                redirect.headers,
                "https://attacker.example/collect",
            )
        )

    def test_registry_check_covers_stale_revision_and_soft_retirement(self) -> None:
        device_v1 = {
            "device_id": "device-1",
            "display_name": "ArchiDEAL smoke device",
            "status": "provisioning",
            "revision": 1,
        }
        device_v2 = {**device_v1, "status": "active", "revision": 2}
        responses = [
            (HTTPStatus.CREATED, {"device": device_v1}, {"ETag": '"1"'}),
            (HTTPStatus.OK, {"device": device_v2}, {"ETag": '"2"'}),
            (
                HTTPStatus.PRECONDITION_FAILED,
                {"error": "device_revision_conflict"},
                {},
            ),
            (HTTPStatus.OK, {"device": device_v2}, {"ETag": '"2"'}),
            (HTTPStatus.NO_CONTENT, {}, {"ETag": '"3"'}),
            (HTTPStatus.NOT_FOUND, {"error": "device_not_found"}, {}),
        ]
        with mock.patch.object(
            self.check, "json_request", side_effect=responses
        ) as request_call:
            self.check.check_registry("http://archideal.test/dealiot", "device-1")

        self.assertEqual(request_call.call_count, 6)
        stale_call = request_call.call_args_list[2]
        self.assertEqual(stale_call.kwargs["headers"], {"If-Match": '"1"'})
        self.assertEqual(
            stale_call.kwargs["expected_error_status"],
            HTTPStatus.PRECONDITION_FAILED,
        )
        delete_call = request_call.call_args_list[4]
        self.assertEqual(delete_call.kwargs["method"], "DELETE")
        self.assertEqual(delete_call.kwargs["headers"], {"If-Match": '"2"'})

    def test_registry_check_sends_bearer_identity_on_every_call(self) -> None:
        device = {
            "device_id": "device-1",
            "display_name": "ArchiDEAL smoke device",
            "status": "active",
            "revision": 2,
        }
        responses = [
            (
                HTTPStatus.CREATED,
                {"device": {**device, "status": "provisioning", "revision": 1}},
                {"ETag": '"1"'},
            ),
            (HTTPStatus.OK, {"device": device}, {"ETag": '"2"'}),
            (
                HTTPStatus.PRECONDITION_FAILED,
                {"error": "device_revision_conflict"},
                {},
            ),
            (HTTPStatus.OK, {"device": device}, {"ETag": '"2"'}),
            (HTTPStatus.NO_CONTENT, {}, {"ETag": '"3"'}),
            (HTTPStatus.NOT_FOUND, {"error": "device_not_found"}, {}),
        ]
        with mock.patch.object(
            self.check,
            "json_request",
            side_effect=responses,
        ) as request_call:
            self.check.check_registry(
                "https://archideal.test/dealiot",
                "device-1",
                bearer_token="opaque-test-token",
            )

        for call in request_call.call_args_list:
            self.assertEqual(
                call.kwargs["headers"]["Authorization"],
                "Bearer opaque-test-token",
            )


if __name__ == "__main__":
    unittest.main()
