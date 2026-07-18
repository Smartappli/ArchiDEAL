from pathlib import Path
import re
import unittest


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
