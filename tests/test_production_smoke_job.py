from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy/kubernetes/validate-production-smoke-job.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_production_smoke_job",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load production smoke Job validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionSmokeJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.image = "registry.example.org/console@sha256:" + "a" * 64
        cls.release = "release-1"
        cls.invocation = "20260718043000-aaaaaaaaaaaa"

    def job(self) -> dict:
        return {
            "kind": "Job",
            "metadata": {
                "name": f"production-smoke-{self.invocation}",
                "uid": "c4fd6b21-0eab-4f5d-b98a-f48d7e0c25c9",
                "creationTimestamp": "2026-07-18T04:30:01Z",
                "labels": {
                    "app.kubernetes.io/name": "production-smoke",
                    "archideal.io/release": self.release,
                    "archideal.io/invocation": self.invocation,
                },
            },
            "spec": {
                "template": {
                    "metadata": {
                        "labels": {
                            "archideal.io/release": self.release,
                            "archideal.io/invocation": self.invocation,
                        }
                    },
                    "spec": {
                        "containers": [{"name": "publish", "image": self.image}]
                    },
                }
            },
            "status": {
                "succeeded": 1,
                "conditions": [{"type": "Complete", "status": "True"}],
            },
        }

    def validate(self, job: dict) -> None:
        self.module.validate_production_smoke_job(
            job,
            expected_release=self.release,
            expected_invocation=self.invocation,
            expected_image=self.image,
        )

    def test_exact_fresh_completed_job_is_accepted(self) -> None:
        self.validate(self.job())

    def test_stale_identity_wrong_image_or_failed_job_is_rejected(self) -> None:
        mutations = []
        stale = copy.deepcopy(self.job())
        stale["metadata"]["labels"]["archideal.io/invocation"] = "old-invocation"
        mutations.append(stale)
        wrong_image = copy.deepcopy(self.job())
        wrong_image["spec"]["template"]["spec"]["containers"][0]["image"] = (
            "registry.example.org/wrong@sha256:" + "b" * 64
        )
        mutations.append(wrong_image)
        failed = copy.deepcopy(self.job())
        failed["status"] = {"failed": 1}
        mutations.append(failed)

        for job in mutations:
            with self.subTest(job=job):
                with self.assertRaises(ValueError):
                    self.validate(job)
