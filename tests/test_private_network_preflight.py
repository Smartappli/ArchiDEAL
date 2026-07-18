from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import unittest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy/apisix/private_network_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("private_network_preflight", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load private network preflight module")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the defining module through sys.modules.
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ENVIRONMENT = {
    "KAFKA_BOOTSTRAP_SERVERS": (
        "kafka-0.example.org:9093,kafka-1.example.org:9093,"
        "kafka-2.example.org:9093"
    ),
    "KAFKA_EGRESS_CIDR": "10.100.0.0/24",
    "MQTT_HOST": "mqtt.example.org",
    "MQTT_EGRESS_CIDR": "10.100.1.0/24",
    "POSTGRES_METADATA_HOST": "metadata.example.org",
    "POSTGRES_METADATA_EGRESS_CIDR": "10.100.2.0/24",
    "POSTGRES_DATA_HOST": "data.example.org",
    "POSTGRES_DATA_EGRESS_CIDR": "10.100.3.0/24",
    "VALKEY_HOST": "valkey.example.org",
    "VALKEY_EGRESS_CIDR": "10.100.4.0/24",
    "ETCD_ENDPOINT_1": "https://etcd-0.example.org:2379",
    "ETCD_ENDPOINT_2": "https://etcd-1.example.org:2379",
    "ETCD_ENDPOINT_3": "https://etcd-2.example.org:2379",
    "ETCD_EGRESS_CIDR": "10.100.5.0/24",
}

APPROVED_ADDRESSES = {
    "kafka-0.example.org": ["10.100.0.10"],
    "kafka-1.example.org": ["10.100.0.11"],
    "kafka-2.example.org": ["10.100.0.12"],
    "mqtt.example.org": ["10.100.1.10"],
    "metadata.example.org": ["10.100.2.10"],
    "data.example.org": ["10.100.3.10"],
    "valkey.example.org": ["10.100.4.10"],
    "etcd-0.example.org": ["10.100.5.10"],
    "etcd-1.example.org": ["10.100.5.11"],
    "etcd-2.example.org": ["10.100.5.12"],
}


def resolver_for(addresses: dict[str, list[str]]):
    def resolve(host: str, port: int, *, type: int):
        if type != socket.SOCK_STREAM:
            raise AssertionError("preflight must request stream addresses")
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, type, 6, "", (address, port))
            for address in addresses.get(host, [])
        ]

    return resolve


class PrivateNetworkPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_every_private_endpoint_must_resolve_inside_its_cidr(self) -> None:
        endpoints, addresses = self.module.validate_private_dns(
            ENVIRONMENT,
            resolver=resolver_for(APPROVED_ADDRESSES),
        )
        self.assertEqual(endpoints, 10)
        self.assertEqual(addresses, 10)

    def test_one_out_of_range_answer_fails_the_complete_contract(self) -> None:
        answers = {key: list(value) for key, value in APPROVED_ADDRESSES.items()}
        answers["kafka-1.example.org"].append("10.100.99.20")
        with self.assertRaisesRegex(ValueError, "outside its approved CIDR") as raised:
            self.module.validate_private_dns(
                ENVIRONMENT,
                resolver=resolver_for(answers),
            )
        self.assertNotIn("10.100.99.20", str(raised.exception))
        self.assertNotIn("10.100.0.0/24", str(raised.exception))

    def test_an_uncovered_ipv6_answer_is_rejected(self) -> None:
        answers = {key: list(value) for key, value in APPROVED_ADDRESSES.items()}
        answers["valkey.example.org"].append("fd00::10")
        with self.assertRaisesRegex(ValueError, "outside its approved CIDR"):
            self.module.validate_private_dns(
                ENVIRONMENT,
                resolver=resolver_for(answers),
            )

    def test_empty_dns_answer_fails_closed(self) -> None:
        answers = {key: list(value) for key, value in APPROVED_ADDRESSES.items()}
        answers["mqtt.example.org"] = []
        with self.assertRaisesRegex(ValueError, "DNS returned no addresses"):
            self.module.validate_private_dns(
                ENVIRONMENT,
                resolver=resolver_for(answers),
            )

    def test_invalid_etcd_port_is_rejected_before_dns(self) -> None:
        environment = dict(ENVIRONMENT)
        environment["ETCD_ENDPOINT_2"] = "https://etcd-1.example.org:443"
        with self.assertRaisesRegex(ValueError, "TCP port 2379"):
            self.module.configured_endpoints(environment)


if __name__ == "__main__":
    unittest.main()
