from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy/kubernetes/validate-release-coherence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_release_coherence", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load release coherence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseCoherenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def snapshots(self, release: str = "release-1") -> tuple[dict, dict]:
        image_values = self.image_values()
        controllers = []
        pods = []
        for name, kind in self.module.EXPECTED_CONTROLLERS.items():
            status = {
                "observedGeneration": 7,
                "readyReplicas": 2,
                "updatedReplicas": 2,
            }
            if kind == "Deployment":
                status.update({"availableReplicas": 2, "unavailableReplicas": 0})
            else:
                status.update(
                    {
                        "currentReplicas": 2,
                        "currentRevision": "revision-a",
                        "updateRevision": "revision-a",
                    }
                )
            pod_spec = {
                field: [
                    {"name": container_name, "image": image_values[values_key]}
                    for container_name, values_key in mapping.items()
                ]
                for field, mapping in self.module.EXPECTED_CONTROLLER_IMAGES[
                    name
                ].items()
            }
            controllers.append(
                {
                    "kind": kind,
                    "metadata": {"name": name, "generation": 7},
                    "spec": {
                        "replicas": 2,
                        "template": {
                            "metadata": {
                                "annotations": {"archideal.io/release": release}
                            },
                            "spec": copy.deepcopy(pod_spec),
                        },
                    },
                    "status": status,
                }
            )
            for index in range(2):
                pods.append(
                    {
                        "metadata": {
                            "name": f"{name}-{index}",
                            "labels": {"app.kubernetes.io/name": name},
                            "annotations": {"archideal.io/release": release},
                        },
                        "spec": copy.deepcopy(pod_spec),
                        "status": {
                            "phase": "Running",
                            "conditions": [{"type": "Ready", "status": "True"}],
                        },
                    }
                )
        return {"items": controllers}, {"items": pods}

    def image_values(self) -> dict[str, str]:
        return {
            key: f"registry.example.org/{key.lower()}@sha256:{index:064x}"
            for index, key in enumerate(sorted(self.module.EXPECTED_IMAGE_KEYS), 1)
        }

    def test_unanimous_converged_release_is_returned(self) -> None:
        controllers, pods = self.snapshots("release-1")

        release = self.module.validate_release_coherence(
            controllers,
            pods,
            expected_release="release-1",
        )

        self.assertEqual(release, "release-1")

    def test_mixed_controller_templates_are_rejected(self) -> None:
        controllers, pods = self.snapshots()
        controllers["items"][3]["spec"]["template"]["metadata"]["annotations"][
            "archideal.io/release"
        ] = "release-0"

        with self.assertRaisesRegex(ValueError, "mixed releases"):
            self.module.validate_release_coherence(controllers, pods)

    def test_ready_pod_from_previous_release_is_rejected(self) -> None:
        controllers, pods = self.snapshots()
        pods["items"][0]["metadata"]["annotations"][
            "archideal.io/release"
        ] = "release-0"

        with self.assertRaisesRegex(ValueError, "Ready pods from mixed releases"):
            self.module.validate_release_coherence(controllers, pods)

    def test_unavailable_or_unobserved_controller_is_rejected(self) -> None:
        controllers, pods = self.snapshots()
        controllers["items"][0]["status"]["observedGeneration"] = 6

        with self.assertRaisesRegex(ValueError, "generation is not fully observed"):
            self.module.validate_release_coherence(controllers, pods)

    def test_all_ten_live_image_values_are_bound(self) -> None:
        controllers, pods = self.snapshots()

        release = self.module.validate_release_coherence(
            controllers,
            pods,
            expected_release="release-1",
            image_values=self.image_values(),
        )

        self.assertEqual(release, "release-1")
        mapped_keys = {
            values_key
            for sections in self.module.EXPECTED_CONTROLLER_IMAGES.values()
            for mapping in sections.values()
            for values_key in mapping.values()
        }
        self.assertEqual(mapped_keys, self.module.EXPECTED_IMAGE_KEYS)
        self.assertEqual(len(mapped_keys), 10)

    def test_wrong_controller_or_ready_pod_image_is_rejected(self) -> None:
        controllers, pods = self.snapshots()
        controllers["items"][0]["spec"]["template"]["spec"]["containers"][0][
            "image"
        ] = "registry.example.org/wrong@sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "image does not match"):
            self.module.validate_controller_images(
                controllers,
                pods,
                self.image_values(),
            )

        controllers, pods = self.snapshots()
        pods["items"][0]["spec"]["containers"][0]["image"] = (
            "registry.example.org/wrong@sha256:" + "f" * 64
        )
        with self.assertRaisesRegex(ValueError, "image does not match"):
            self.module.validate_controller_images(
                controllers,
                pods,
                self.image_values(),
            )

    def test_only_succeeded_release_bound_ingress_is_accepted(self) -> None:
        ingress = {
            "kind": "Ingress",
            "metadata": {
                "name": "archideal",
                "labels": {"archideal.io/release": "release-1"},
                "annotations": {
                    "archideal.io/release": "release-1",
                    "archideal.io/promotion-state": "succeeded",
                    "archideal.io/promotion-release": "release-1",
                    "archideal.io/active-release": "release-1",
                },
            },
            "spec": {
                "rules": [{"host": "deal.example.org"}],
                "tls": [{"hosts": ["deal.example.org"]}],
            },
        }

        self.module.validate_promoted_ingress(
            ingress,
            expected_release="release-1",
            expected_host="deal.example.org",
        )
        ingress["metadata"]["annotations"]["archideal.io/promotion-state"] = "failed"
        with self.assertRaisesRegex(ValueError, "promotion-state"):
            self.module.validate_promoted_ingress(
                ingress,
                expected_release="release-1",
                expected_host="deal.example.org",
            )


if __name__ == "__main__":
    unittest.main()
