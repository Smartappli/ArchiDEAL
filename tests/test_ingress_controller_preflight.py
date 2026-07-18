from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy/kubernetes/validate-ingress-controller.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ingress_controller_preflight", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ingress controller preflight module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def controller_pod(
    name: str,
    address: str,
    *,
    arguments: list[str] | None = None,
    ready: bool = True,
    host_network: bool = False,
    extra_addresses: list[str] | None = None,
) -> dict:
    addresses = [address, *(extra_addresses or [])]
    return {
        "metadata": {
            "name": name,
            "labels": {
                "app.kubernetes.io/name": "ingress-nginx",
                "app.kubernetes.io/component": "controller",
            },
        },
        "spec": {
            "hostNetwork": host_network,
            "containers": [
                {
                    "name": "controller",
                    "args": arguments or [],
                }
            ],
        },
        "status": {
            "phase": "Running",
            "podIP": address,
            "podIPs": [{"ip": item} for item in addresses],
            "conditions": [
                {"type": "Ready", "status": "True" if ready else "False"}
            ],
        },
    }


class IngressControllerPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def validate(self, pods: list[dict], **overrides):
        options = {
            "ingress_class": "nginx",
            "controller_class": "k8s.io/ingress-nginx",
            "proxy_cidr": "10.42.0.0/24",
        }
        options.update(overrides)
        return self.module.validate_ingress_controllers(
            {"apiVersion": "v1", "kind": "PodList", "items": pods},
            **options,
        )

    def test_ready_default_ingress_nginx_is_covered(self) -> None:
        self.assertEqual(
            self.validate([controller_pod("controller-0", "10.42.0.10")]),
            (1, 1),
        )

    def test_custom_class_requires_matching_explicit_arguments(self) -> None:
        arguments = [
            "--controller-class",
            "k8s.io/ingress-nginx",
            "--ingress-class=archideal-public",
        ]
        self.assertEqual(
            self.validate(
                [controller_pod("controller-0", "10.42.0.10", arguments=arguments)],
                ingress_class="archideal-public",
            ),
            (1, 1),
        )

    def test_at_least_one_ready_matching_controller_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "no Ready ingress-nginx"):
            self.validate(
                [controller_pod("controller-0", "10.42.0.10", ready=False)]
            )
        with self.assertRaisesRegex(ValueError, "no Ready ingress-nginx"):
            self.validate(
                [
                    controller_pod(
                        "controller-1",
                        "10.42.0.11",
                        arguments=["--ingress-class=some-other-class"],
                    )
                ]
            )

    def test_every_ready_controller_address_must_be_covered(self) -> None:
        pods = [
            controller_pod("controller-0", "10.42.0.10"),
            controller_pod("controller-1", "10.43.0.10"),
        ]
        with self.assertRaisesRegex(ValueError, "outside INGRESS_PROXY_CIDR") as raised:
            self.validate(pods)
        self.assertNotIn("10.43.0.10", str(raised.exception))

    def test_dual_stack_answer_requires_complete_cidr_coverage(self) -> None:
        pod = controller_pod(
            "controller-0",
            "10.42.0.10",
            extra_addresses=["fd42::10"],
        )
        with self.assertRaisesRegex(ValueError, "outside INGRESS_PROXY_CIDR"):
            self.validate([pod])

    def test_host_network_controller_is_rejected(self) -> None:
        pod = controller_pod(
            "controller-0",
            "10.42.0.10",
            host_network=True,
        )
        with self.assertRaisesRegex(ValueError, "hostNetwork"):
            self.validate([pod])

    def test_non_official_controller_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "k8s.io/ingress-nginx"):
            self.validate(
                [controller_pod("controller-0", "10.42.0.10")],
                controller_class="example.com/controller",
            )


if __name__ == "__main__":
    unittest.main()
