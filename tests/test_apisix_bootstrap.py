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
            mock.patch.object(self.bootstrap, "wait_for_admin_api"),
            mock.patch.object(self.bootstrap, "request", return_value=201) as request,
        ):
            self.bootstrap.main()

        request.assert_called_once_with(
            "/apisix/admin/routes/archideal-interface",
            method="PUT",
            payload={"uris": ["/", "/*"], "priority": -100},
        )


if __name__ == "__main__":
    unittest.main()
