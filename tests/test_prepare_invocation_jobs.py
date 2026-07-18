from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy/kubernetes/prepare-invocation-jobs.py"
BOOTSTRAP = ROOT / "deploy/kubernetes/base/bootstrap.yaml"
SYNTHETIC = ROOT / "deploy/kubernetes/overlays/production/synthetic-smoke.yaml"
PRIVATE_NETWORK = ROOT / "deploy/kubernetes/base/private-network-preflight.yaml"
KAFKA_PREFLIGHT = ROOT / "deploy/kubernetes/base/preflight.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_invocation_jobs", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load invocation Job preparation module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrepareInvocationJobsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_retry_gets_new_jobs_and_new_mqtt_database_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bootstrap = root / "bootstrap.yaml"
            synthetic = root / "synthetic.yaml"
            bootstrap.write_text(
                BOOTSTRAP.read_text(encoding="utf-8").replace(
                    "${RELEASE_ID}", "release-1"
                ),
                encoding="utf-8",
            )
            synthetic.write_text(
                SYNTHETIC.read_text(encoding="utf-8")
                .replace("${RELEASE_ID}", "release-1")
                .replace("${IMAGE_DEALIOT_CONSOLE}", "registry/image@sha256:" + "a" * 64)
                .replace("${MQTT_HOST}", "mqtt.example.org"),
                encoding="utf-8",
            )

            first = self.module.prepare_jobs(
                bootstrap=bootstrap,
                synthetic=synthetic,
                invocation_id="20260718043000-aaaaaaaaaaaa",
            )
            first_synthetic = yaml.safe_load(synthetic.read_text(encoding="utf-8"))
            second = self.module.prepare_jobs(
                bootstrap=bootstrap,
                synthetic=synthetic,
                invocation_id="20260718043100-bbbbbbbbbbbb",
            )

            self.assertNotEqual(
                first["apisix_bootstrap_job"], second["apisix_bootstrap_job"]
            )
            self.assertNotEqual(
                first["production_smoke_job"], second["production_smoke_job"]
            )
            self.assertNotEqual(first["smoke_device_id"], second["smoke_device_id"])
            self.assertLessEqual(len(second["apisix_bootstrap_job"]), 63)
            self.assertLessEqual(len(second["production_smoke_job"]), 63)

            second_bootstrap = yaml.safe_load(bootstrap.read_text(encoding="utf-8"))
            second_synthetic = yaml.safe_load(synthetic.read_text(encoding="utf-8"))
            for job in (second_bootstrap, second_synthetic):
                self.assertEqual(
                    job["metadata"]["labels"]["archideal.io/invocation"],
                    second["invocation_id"],
                )
                self.assertEqual(
                    job["spec"]["template"]["metadata"]["labels"][
                        "archideal.io/invocation"
                    ],
                    second["invocation_id"],
                )
            env = {
                item["name"]: item
                for item in second_synthetic["spec"]["template"]["spec"][
                    "containers"
                ][0]["env"]
            }
            self.assertEqual(env["SMOKE_DEVICE_ID"]["value"], second["smoke_device_id"])
            first_env = {
                item["name"]: item
                for item in first_synthetic["spec"]["template"]["spec"][
                    "containers"
                ][0]["env"]
            }
            self.assertNotEqual(
                first_env["SMOKE_DEVICE_ID"]["value"],
                env["SMOKE_DEVICE_ID"]["value"],
            )

    def test_invalid_invocation_id_does_not_modify_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            synthetic = Path(temporary_directory) / "synthetic.yaml"
            original = SYNTHETIC.read_text(encoding="utf-8")
            synthetic.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "at most 32"):
                self.module.prepare_jobs(
                    bootstrap=None,
                    synthetic=synthetic,
                    invocation_id="a" * 33,
                )

            self.assertEqual(synthetic.read_text(encoding="utf-8"), original)

    def test_private_network_preflight_gets_the_same_fresh_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            private_network = Path(temporary_directory) / "private-network.yaml"
            private_network.write_text(
                PRIVATE_NETWORK.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            first = self.module.prepare_jobs(
                bootstrap=None,
                synthetic=None,
                private_network=private_network,
                invocation_id="20260718043200-cccccccccccc",
            )
            second = self.module.prepare_jobs(
                bootstrap=None,
                synthetic=None,
                private_network=private_network,
                invocation_id="20260718043300-dddddddddddd",
            )

            job = yaml.safe_load(private_network.read_text(encoding="utf-8"))
            expected_name = (
                "private-network-preflight-20260718043300-dddddddddddd"
            )
            self.assertNotEqual(
                first["private_network_preflight_job"],
                second["private_network_preflight_job"],
            )
            self.assertEqual(second["private_network_preflight_job"], expected_name)
            self.assertEqual(job["metadata"]["name"], expected_name)
            for labels in (
                job["metadata"]["labels"],
                job["spec"]["template"]["metadata"]["labels"],
            ):
                self.assertEqual(
                    labels["archideal.io/invocation"],
                    second["invocation_id"],
                )

    def test_kafka_preflight_is_fresh_for_a_same_release_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            kafka = Path(temporary_directory) / "kafka.yaml"
            kafka.write_text(
                KAFKA_PREFLIGHT.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            first = self.module.prepare_jobs(
                bootstrap=None,
                synthetic=None,
                kafka=kafka,
                invocation_id="20260718043400-eeeeeeeeeeee",
            )
            second = self.module.prepare_jobs(
                bootstrap=None,
                synthetic=None,
                kafka=kafka,
                invocation_id="20260718043500-ffffffffffff",
            )

            job = yaml.safe_load(kafka.read_text(encoding="utf-8"))
            self.assertNotEqual(
                first["kafka_preflight_job"],
                second["kafka_preflight_job"],
            )
            self.assertEqual(
                second["kafka_preflight_job"],
                "kafka-preflight-20260718043500-ffffffffffff",
            )
            self.assertEqual(
                job["metadata"]["labels"]["archideal.io/invocation"],
                second["invocation_id"],
            )
            self.assertEqual(
                job["spec"]["template"]["metadata"]["labels"][
                    "archideal.io/invocation"
                ],
                second["invocation_id"],
            )


if __name__ == "__main__":
    unittest.main()
