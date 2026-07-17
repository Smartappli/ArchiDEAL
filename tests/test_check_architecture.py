from __future__ import annotations

import importlib.util
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
