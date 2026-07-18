from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PATH = ROOT / "deploy/apisix/bootstrap.py"


def load_bootstrap_module():
    os.environ.setdefault("APISIX_ADMIN_KEY", "test-admin-key")
    spec = importlib.util.spec_from_file_location("archideal_apisix_bootstrap", BOOTSTRAP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the APISIX bootstrap module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApisixBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap = load_bootstrap_module()

    def test_readiness_query_uses_a_valid_apisix_page_size(self) -> None:
        with mock.patch.object(self.bootstrap, "request", return_value=200) as request:
            self.bootstrap.wait_for_admin_api()

        request.assert_called_once_with("/apisix/admin/routes?page=1&page_size=10")

    def test_main_puts_idempotent_routes_without_id_in_the_payload(self) -> None:
        route = {
            "id": "archideal-interface",
            "uris": ["/", "/*"],
            "priority": -100,
        }
        routes_file = mock.Mock()
        routes_file.read_text.return_value = json.dumps({"routes": [route]})

        with (
            mock.patch.object(self.bootstrap, "ROUTES_FILE", routes_file),
            mock.patch.object(self.bootstrap, "PLUGIN_METADATA_FILE", ""),
            mock.patch.object(self.bootstrap, "wait_for_admin_api"),
            mock.patch.object(self.bootstrap, "remove_stale_managed_routes") as remove,
            mock.patch.object(self.bootstrap, "request", return_value=201) as request,
        ):
            self.bootstrap.main()

        request.assert_called_once_with(
            "/apisix/admin/routes/archideal-interface",
            method="PUT",
            payload={"uris": ["/", "/*"], "priority": -100},
        )
        remove.assert_called_once_with({"archideal-interface"})

    def test_stale_bootstrap_routes_are_removed_but_dynamic_routes_are_preserved(self) -> None:
        response = {
            "total": 3,
            "list": [
                {"key": "/apisix/routes/archideal-interface", "value": {}},
                {"key": "/apisix/routes/archideal-obsolete", "value": {}},
                {"key": "/apisix/routes/module-dealdata", "value": {}},
            ],
        }
        with (
            mock.patch.object(
                self.bootstrap,
                "request_json",
                return_value=(200, response),
            ),
            mock.patch.object(self.bootstrap, "request", return_value=200) as request,
        ):
            self.bootstrap.remove_stale_managed_routes({"archideal-interface"})

        request.assert_called_once_with(
            "/apisix/admin/routes/archideal-obsolete",
            method="DELETE",
        )

    def test_route_listing_follows_pagination(self) -> None:
        first_page = {
            "total": 101,
            "list": [
                {"key": f"/apisix/routes/module-{index}", "value": {}}
                for index in range(100)
            ],
        }
        second_page = {
            "total": 101,
            "list": [
                {"key": "/apisix/routes/archideal-stale", "value": {}},
            ],
        }
        with mock.patch.object(
            self.bootstrap,
            "request_json",
            side_effect=[(200, first_page), (200, second_page)],
        ) as request_json:
            route_ids = self.bootstrap.installed_managed_route_ids()

        self.assertEqual(route_ids, {"archideal-stale"})
        self.assertEqual(request_json.call_count, 2)

    def test_plugin_metadata_is_installed_before_routes(self) -> None:
        metadata_file = mock.Mock()
        metadata_file.read_text.return_value = json.dumps(
            {
                "plugin_metadata": {
                    "opentelemetry": {
                        "collector": {"address": "otel:4318"},
                    },
                },
            }
        )

        with (
            mock.patch.object(
                self.bootstrap,
                "PLUGIN_METADATA_FILE",
                "/bootstrap/plugin-metadata.json",
            ),
            mock.patch.object(self.bootstrap, "Path", return_value=metadata_file),
            mock.patch.object(self.bootstrap, "request", return_value=201) as request,
        ):
            self.bootstrap.install_plugin_metadata()

        request.assert_called_once_with(
            "/apisix/admin/plugin_metadata/opentelemetry",
            method="PUT",
            payload={"collector": {"address": "otel:4318"}},
        )


if __name__ == "__main__":
    unittest.main()
