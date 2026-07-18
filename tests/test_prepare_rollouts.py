from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy/kubernetes/prepare-rollouts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("archideal_prepare_rollouts", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load rollout preparation module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrepareRolloutsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_controllers_are_split_and_stamped_without_claiming_scale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "controllers.yaml"
            source.write_text(
                """apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-a
spec:
  selector: {matchLabels: {app: service-a}}
  template:
    metadata:
      labels: {app: service-a}
      annotations: {archideal.io/release: release-1}
    spec: {containers: []}
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: service-b
spec:
  selector: {matchLabels: {app: service-b}}
  template:
    metadata:
      labels: {app: service-b}
    spec: {containers: []}
""",
                encoding="utf-8",
            )
            output = root / "prepared"
            revision = "a" * 64

            names = self.module.prepare([source], output, revision)

            self.assertEqual(names, ["service-a", "service-b"])
            for name in names:
                document = yaml.safe_load(
                    (output / f"{name}.yaml").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    document["spec"]["template"]["metadata"]["annotations"][
                        "archideal.io/runtime-revision"
                    ],
                    revision,
                )
                self.assertNotIn("replicas", document["spec"])

    def test_invalid_revision_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "controllers.yaml"
            source.write_text("", encoding="utf-8")
            output = root / "prepared"

            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                self.module.prepare([source], output, "not-a-revision")

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
