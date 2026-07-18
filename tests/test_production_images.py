from pathlib import Path
import re
import tomllib
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PINNED_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
PRODUCTION_DOCKERFILES = (
    "deploy/apisix/Dockerfile",
    "components/DEALIoT/management-console/Dockerfile",
    "components/DEALIoT/mqtt-kafka-bridge/Dockerfile",
    "components/DEALHost/Dockerfile",
    "components/DEALData/core_layer/Dockerfile",
    "components/DEALData/gps_layer/Dockerfile",
    "components/DEALData/sensor_layer/Dockerfile",
    "components/DEALInterface/Dockerfile",
)


class ProductionImageContracts(unittest.TestCase):
    def test_every_production_base_image_is_pinned_by_digest(self) -> None:
        for relative_path in PRODUCTION_DOCKERFILES:
            with self.subTest(dockerfile=relative_path):
                dockerfile = ROOT / relative_path
                base_images = [
                    line.split()[1]
                    for line in dockerfile.read_text(encoding="utf-8").splitlines()
                    if line.strip().upper().startswith("FROM ")
                ]
                self.assertTrue(base_images)
                for image in base_images:
                    if image == "scratch":
                        continue
                    self.assertRegex(image, PINNED_IMAGE)

    def test_dealhost_installs_only_hash_locked_runtime_dependencies(self) -> None:
        dockerfile = (ROOT / "components/DEALHost/Dockerfile").read_text(
            encoding="utf-8"
        )
        lock = (ROOT / "components/DEALHost/requirements.lock").read_text(
            encoding="utf-8"
        )

        self.assertIn("--require-hashes", dockerfile)
        self.assertIn("--only-binary :all:", dockerfile)
        self.assertNotIn("pip install --no-cache-dir .", dockerfile)
        self.assertIn("--hash=sha256:", lock)
        self.assertIn("uv export --frozen", lock.splitlines()[1])

    def test_mqtt_bridge_runtime_avoids_unneeded_os_packages(self) -> None:
        manifest = tomllib.loads(
            (ROOT / "components/DEALIoT/mqtt-kafka-bridge/Cargo.toml").read_text(
                encoding="utf-8"
            )
        )
        rdkafka = manifest["dependencies"]["rdkafka"]

        self.assertFalse(rdkafka["default-features"])
        self.assertEqual(
            set(rdkafka["features"]),
            {"cmake-build", "libz-static", "ssl-vendored", "tokio"},
        )
        smoke_script = (ROOT / "scripts/smoke-architecture.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("mqtt-kafka-bridge --healthcheck", smoke_script)
        self.assertNotRegex(smoke_script, r"mqtt-kafka-bridge\s+\\?\s*wget\b")

    def test_production_build_contexts_exclude_common_secret_files(self) -> None:
        contexts = (
            "deploy/apisix/.dockerignore",
            "components/DEALIoT/.dockerignore",
            "components/DEALHost/.dockerignore",
            "components/DEALData/.dockerignore",
            "components/DEALInterface/.dockerignore",
        )
        for relative_path in contexts:
            with self.subTest(context=relative_path):
                ignore = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertRegex(ignore, r"(?m)^\*\*/\.env$|^\.env\*?$|^\.env\.\*$")
                self.assertRegex(ignore, r"(?m)^\*\*/\*\.key$|^\*\.key$")

    def test_security_scans_pin_the_reviewed_trivy_engine(self) -> None:
        trivy_steps = []
        for relative_path in (
            ".github/workflows/architecture-smoke.yml",
            ".github/workflows/release-images.yml",
            ".github/workflows/security.yml",
        ):
            workflow = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
            for job in workflow["jobs"].values():
                for step in job.get("steps", []):
                    if str(step.get("uses", "")).startswith("aquasecurity/trivy-action@"):
                        trivy_steps.append((relative_path, step))

        self.assertEqual(len(trivy_steps), 7)
        for relative_path, step in trivy_steps:
            with self.subTest(workflow=relative_path, step=step.get("name")):
                self.assertEqual(step.get("with", {}).get("version"), "v0.72.0")

    def test_architecture_smoke_covers_bridge_workspace_and_health_console(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/architecture-smoke.yml").read_text(
                encoding="utf-8"
            )
        )
        required_paths = {
            "components/DEALIoT/.dockerignore",
            "components/DEALIoT/Cargo.lock",
            "components/DEALIoT/Cargo.toml",
            "components/DEALIoT/management-console/**",
            "components/DEALIoT/mqtt-kafka-bridge/**",
        }
        events = workflow.get("on", workflow.get(True))
        self.assertIsInstance(events, dict)
        for event_name in ("push", "pull_request"):
            with self.subTest(event=event_name):
                configured_paths = set(events[event_name]["paths"])
                self.assertTrue(required_paths.issubset(configured_paths))

    def test_apisix_tool_image_contains_every_runtime_helper(self) -> None:
        dockerfile = (ROOT / "deploy/apisix/Dockerfile").read_text(encoding="utf-8")
        for helper in (
            "bootstrap.py",
            "health.py",
            "private_network_preflight.py",
        ):
            self.assertIn(helper, dockerfile)


if __name__ == "__main__":
    unittest.main()
