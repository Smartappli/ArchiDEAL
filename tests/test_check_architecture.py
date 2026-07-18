from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
CHECK_PATH = ROOT / "scripts/check-architecture.py"


def load_check_module():
    spec = importlib.util.spec_from_file_location("archideal_check_architecture", CHECK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the architecture check module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = load_check_module()

    def test_health_checks_use_the_dealiot_vernemq_component_id(self) -> None:
        def fake_wait_for(url, _predicate, _description, timeout=120):
            del timeout
            if url.endswith("/dealiot/api/health"):
                return {
                    "checks": [
                        {"id": "kafka", "status": "healthy"},
                        {"id": "vernemq", "status": "healthy"},
                    ]
                }
            return {}

        with mock.patch.object(self.check, "wait_for", side_effect=fake_wait_for):
            self.check.health_checks("http://archideal.test")

    def test_bearer_token_is_loaded_from_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "token"
            token_file.write_text("short-lived-token\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"ARCHIDEAL_BEARER_TOKEN_FILE": str(token_file)},
                clear=False,
            ):
                headers = self.check.request_headers()

        self.assertEqual(headers, {"Authorization": "Bearer short-lived-token"})

    def test_ingest_token_is_loaded_from_a_separate_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "ingest-token"
            token_file.write_text("write-only-token\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"ARCHIDEAL_INGEST_TOKEN_FILE": str(token_file)},
                clear=False,
            ):
                headers = self.check.ingest_headers()

        self.assertEqual(
            headers,
            {"X-DEALDATA-INGEST-TOKEN": "write-only-token"},
        )

    def test_service_readiness_rejects_login_pages_and_unavailable_database(self) -> None:
        self.assertFalse(self.check.service_is_ready("<html>login</html>", "gateway"))
        self.assertFalse(
            self.check.service_is_ready(
                {"status": "ok", "service": "gps", "database": "unavailable"},
                "gps",
                require_database=True,
            )
        )

    def test_http_request_exposes_redirect_without_following_it(self) -> None:
        url = "https://archideal.test/protected"
        redirect = self.check.HTTPError(
            url,
            302,
            "Found",
            {"location": "https://identity.test/login"},
            io.BytesIO(b""),
        )
        opener = mock.Mock()
        opener.open.side_effect = redirect
        with mock.patch.object(
            self.check,
            "build_opener",
            return_value=opener,
        ) as build_opener, mock.patch.object(
            self.check,
            "urlopen",
        ) as urlopen:
            result = self.check.http_request(url, follow_redirects=False)

        self.assertEqual(result.status, 302)
        self.assertEqual(result.final_url, url)
        self.assertEqual(result.headers["location"], "https://identity.test/login")
        self.assertTrue(
            any(
                isinstance(handler, self.check.NoRedirectHandler)
                for handler in build_opener.call_args.args
            )
        )
        urlopen.assert_not_called()
        self.assertTrue(
            self.check.service_is_ready(
                {"status": "ok", "service": "gps", "database": "available"},
                "gps",
                require_database=True,
            )
        )

    def test_production_auth_checks_cover_authenticated_and_anonymous_routes(self) -> None:
        base_url = "https://archideal.test"
        repositories_url = (
            f"{base_url}/dealhost/api/gateway/github/repositories/"
        )
        webhook_url = f"{base_url}/dealhost/api/gateway/github/webhook/"
        responses = [
            self.check.HTTPResult(
                200,
                {"repositories": []},
                repositories_url,
                {"content-type": "application/json"},
            ),
            self.check.HTTPResult(302, "", repositories_url, {"location": "/login"}),
            self.check.HTTPResult(
                401,
                {"detail": "Invalid GitHub signature."},
                webhook_url,
                {"content-type": "application/json"},
            ),
        ]
        with mock.patch.object(
            self.check,
            "request_headers",
            return_value={"Authorization": "Bearer opaque"},
        ), mock.patch.object(
            self.check,
            "http_request",
            side_effect=responses,
        ) as request:
            self.check.production_auth_checks(base_url)

        calls = request.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args, (repositories_url,))
        self.assertEqual(calls[0].kwargs["headers"], {"Authorization": "Bearer opaque"})
        self.assertFalse(calls[0].kwargs["follow_redirects"])
        self.assertEqual(calls[1].kwargs["headers"], {})
        self.assertFalse(calls[1].kwargs["follow_redirects"])
        self.assertEqual(calls[2].args, (webhook_url,))
        self.assertEqual(calls[2].kwargs["method"], "POST")
        self.assertEqual(calls[2].kwargs["headers"], {})
        self.assertEqual(calls[2].kwargs["json_body"], {})
        self.assertFalse(calls[2].kwargs["follow_redirects"])

    def test_production_auth_checks_reject_anonymous_success(self) -> None:
        base_url = "https://archideal.test"
        url = f"{base_url}/dealhost/api/gateway/github/repositories/"
        responses = [
            self.check.HTTPResult(200, {"repositories": []}, url, {}),
            self.check.HTTPResult(200, {"repositories": []}, url, {}),
        ]
        with mock.patch.object(
            self.check,
            "request_headers",
            return_value={"Authorization": "Bearer opaque"},
        ), mock.patch.object(
            self.check,
            "http_request",
            side_effect=responses,
        ):
            with self.assertRaisesRegex(RuntimeError, "anonymous DEALHost"):
                self.check.production_auth_checks(base_url)

    def test_production_auth_checks_require_downstream_webhook_hmac_rejection(self) -> None:
        base_url = "https://archideal.test"
        repositories_url = (
            f"{base_url}/dealhost/api/gateway/github/repositories/"
        )
        webhook_url = f"{base_url}/dealhost/api/gateway/github/webhook/"
        responses = [
            self.check.HTTPResult(
                200,
                {"repositories": []},
                repositories_url,
                {},
            ),
            self.check.HTTPResult(302, "", repositories_url, {}),
            self.check.HTTPResult(302, "", webhook_url, {}),
        ]
        with mock.patch.object(
            self.check,
            "request_headers",
            return_value={"Authorization": "Bearer opaque"},
        ), mock.patch.object(
            self.check,
            "http_request",
            side_effect=responses,
        ):
            with self.assertRaisesRegex(RuntimeError, "HMAC validation"):
                self.check.production_auth_checks(base_url)

    def test_api_ingest_creates_replays_and_queries_one_event_per_layer(self) -> None:
        base_url = "https://archideal.test"
        gps_url = f"{base_url}/dealdata/gps/api/ingest/wildfi/gps/"
        sensor_url = f"{base_url}/dealdata/sensor/api/ingest/wildfi/sensor/"
        responses = [
            self.check.HTTPResult(201, {"duplicate": False}, gps_url, {}),
            self.check.HTTPResult(200, {"duplicate": True}, gps_url, {}),
            self.check.HTTPResult(201, {"duplicate": False}, sensor_url, {}),
            self.check.HTTPResult(200, {"duplicate": True}, sensor_url, {}),
        ]
        with mock.patch.object(
            self.check,
            "request_headers",
            return_value={"Authorization": "Bearer opaque"},
        ), mock.patch.object(
            self.check,
            "ingest_headers",
            return_value={"X-DEALDATA-INGEST-TOKEN": "opaque-ingest"},
        ), mock.patch.object(
            self.check,
            "http_request",
            side_effect=responses,
        ) as request, mock.patch.object(
            self.check,
            "wait_for_events",
        ) as wait_for_events, mock.patch.object(
            self.check,
            "event_count",
            side_effect=[1, 1],
        ) as event_count:
            self.check.exercise_api_ingest(base_url)

        calls = request.call_args_list
        self.assertEqual(
            [call.args[0] for call in calls],
            [gps_url, gps_url, sensor_url, sensor_url],
        )
        for call in calls:
            self.assertEqual(call.kwargs["method"], "POST")
            self.assertFalse(call.kwargs["follow_redirects"])
            self.assertEqual(
                call.kwargs["headers"],
                {
                    "Authorization": "Bearer opaque",
                    "X-DEALDATA-INGEST-TOKEN": "opaque-ingest",
                },
            )
        self.assertEqual(calls[0].kwargs["json_body"], calls[1].kwargs["json_body"])
        self.assertEqual(calls[2].kwargs["json_body"], calls[3].kwargs["json_body"])
        self.assertNotEqual(
            calls[0].kwargs["json_body"]["event_id"],
            calls[2].kwargs["json_body"]["event_id"],
        )
        device_id = calls[0].kwargs["json_body"]["device_id"]
        self.assertEqual(device_id, calls[2].kwargs["json_body"]["device_id"])
        wait_for_events.assert_called_once_with(base_url, device_id)
        self.assertEqual(
            event_count.call_args_list,
            [
                mock.call(base_url, "gps", device_id),
                mock.call(base_url, "sensor", device_id),
            ],
        )

    def test_api_ingest_fails_if_the_first_event_is_reported_as_duplicate(self) -> None:
        base_url = "https://archideal.test"
        gps_url = f"{base_url}/dealdata/gps/api/ingest/wildfi/gps/"
        with mock.patch.object(
            self.check,
            "request_headers",
            return_value={},
        ), mock.patch.object(
            self.check,
            "ingest_headers",
            return_value={"X-DEALDATA-INGEST-TOKEN": "opaque"},
        ), mock.patch.object(
            self.check,
            "http_request",
            return_value=self.check.HTTPResult(
                201,
                {"duplicate": True},
                gps_url,
                {},
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "first gps ingest"):
                self.check.exercise_api_ingest(base_url)

    def test_full_production_main_runs_auth_and_api_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bearer_file = Path(directory) / "bearer"
            ingest_file = Path(directory) / "ingest"
            bearer_file.write_text("opaque-bearer", encoding="utf-8")
            ingest_file.write_text("opaque-ingest", encoding="utf-8")
            environment = {
                "ARCHIDEAL_BASE_URL": "https://archideal.test",
                "ARCHIDEAL_BEARER_TOKEN_FILE": str(bearer_file),
                "ARCHIDEAL_INGEST_TOKEN_FILE": str(ingest_file),
            }
            argv = [
                "check-architecture.py",
                "--production",
                "--exercise-api-ingest",
            ]
            with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
                self.check.sys,
                "argv",
                argv,
            ), mock.patch.object(
                self.check,
                "health_checks",
            ) as health, mock.patch.object(
                self.check,
                "production_auth_checks",
            ) as auth, mock.patch.object(
                self.check,
                "exercise_api_ingest",
            ) as ingest:
                self.check.main()

        health.assert_called_once_with("https://archideal.test")
        auth.assert_called_once_with("https://archideal.test")
        ingest.assert_called_once_with("https://archideal.test")

    def test_health_only_does_not_run_full_production_probes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bearer_file = Path(directory) / "bearer"
            bearer_file.write_text("opaque-bearer", encoding="utf-8")
            environment = {
                "ARCHIDEAL_BASE_URL": "https://archideal.test",
                "ARCHIDEAL_BEARER_TOKEN_FILE": str(bearer_file),
            }
            argv = ["check-architecture.py", "--production", "--health-only"]
            with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
                self.check.sys,
                "argv",
                argv,
            ), mock.patch.object(
                self.check,
                "health_checks",
            ), mock.patch.object(
                self.check,
                "production_auth_checks",
            ) as auth, mock.patch.object(
                self.check,
                "exercise_api_ingest",
            ) as ingest:
                self.check.main()

        auth.assert_not_called()
        ingest.assert_not_called()

    def test_api_ingest_mode_requires_a_token_file_reference(self) -> None:
        environment = {
            "ARCHIDEAL_BASE_URL": "http://127.0.0.1:8080",
            "ARCHIDEAL_INGEST_TOKEN_FILE": "",
        }
        argv = ["check-architecture.py", "--exercise-api-ingest"]
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
            self.check.sys,
            "argv",
            argv,
        ), mock.patch.object(
            self.check,
            "health_checks",
        ) as health, mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            with self.assertRaises(SystemExit):
                self.check.main()
        health.assert_not_called()


if __name__ == "__main__":
    unittest.main()
