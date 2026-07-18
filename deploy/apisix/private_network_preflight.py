#!/usr/bin/env python3
"""Fail closed when private dependency DNS escapes its approved CIDR."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
import socket
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit


Resolver = Callable[..., Sequence[tuple]]


@dataclass(frozen=True)
class DependencyEndpoint:
    """One non-secret endpoint and the network its DNS answers must remain in."""

    label: str
    host: str
    port: int
    network: ipaddress.IPv4Network | ipaddress.IPv6Network


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"required configuration is missing: {name}")
    return value


def _network(environment: Mapping[str, str], name: str):
    raw = _required(environment, name)
    try:
        return ipaddress.ip_network(raw, strict=True)
    except ValueError as exc:
        raise ValueError(f"configured CIDR is invalid: {name}") from exc


def _host_port(value: str, *, expected_port: int, label: str) -> tuple[str, int]:
    host, separator, raw_port = value.rpartition(":")
    if not separator or not host or not raw_port.isascii() or not raw_port.isdigit():
        raise ValueError(f"{label} must use the host:port form")
    port = int(raw_port)
    if port != expected_port:
        raise ValueError(f"{label} must use TCP port {expected_port}")
    return host, port


def _https_endpoint(value: str, *, expected_port: int, label: str) -> tuple[str, int]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid HTTPS endpoint") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (port or 443) != expected_port
    ):
        raise ValueError(
            f"{label} must be an HTTPS endpoint on TCP port {expected_port}"
        )
    return parsed.hostname, port or 443


def configured_endpoints(
    environment: Mapping[str, str],
) -> tuple[DependencyEndpoint, ...]:
    """Build the complete endpoint/CIDR contract from non-secret environment."""
    endpoints: list[DependencyEndpoint] = []

    kafka_network = _network(environment, "KAFKA_EGRESS_CIDR")
    raw_brokers = _required(environment, "KAFKA_BOOTSTRAP_SERVERS").split(",")
    if not raw_brokers or any(not broker.strip() for broker in raw_brokers):
        raise ValueError("KAFKA_BOOTSTRAP_SERVERS contains an empty broker")
    for index, broker in enumerate(raw_brokers, start=1):
        host, port = _host_port(
            broker.strip(), expected_port=9093, label=f"Kafka broker {index}"
        )
        endpoints.append(
            DependencyEndpoint(f"Kafka broker {index}", host, port, kafka_network)
        )

    simple_dependencies = (
        ("MQTT", "MQTT_HOST", 8883, "MQTT_EGRESS_CIDR"),
        (
            "PostgreSQL metadata",
            "POSTGRES_METADATA_HOST",
            5432,
            "POSTGRES_METADATA_EGRESS_CIDR",
        ),
        (
            "PostgreSQL data",
            "POSTGRES_DATA_HOST",
            5432,
            "POSTGRES_DATA_EGRESS_CIDR",
        ),
        ("Valkey", "VALKEY_HOST", 6380, "VALKEY_EGRESS_CIDR"),
    )
    for label, host_name, port, network_name in simple_dependencies:
        endpoints.append(
            DependencyEndpoint(
                label,
                _required(environment, host_name),
                port,
                _network(environment, network_name),
            )
        )

    etcd_network = _network(environment, "ETCD_EGRESS_CIDR")
    for index in range(1, 4):
        label = f"etcd endpoint {index}"
        host, port = _https_endpoint(
            _required(environment, f"ETCD_ENDPOINT_{index}"),
            expected_port=2379,
            label=label,
        )
        endpoints.append(DependencyEndpoint(label, host, port, etcd_network))

    return tuple(endpoints)


def resolve_endpoint(
    endpoint: DependencyEndpoint,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> int:
    """Resolve one endpoint, rejecting empty, malformed or out-of-range answers."""
    try:
        answers = resolver(
            endpoint.host,
            endpoint.port,
            type=socket.SOCK_STREAM,
        )
    except (OSError, socket.gaierror) as exc:
        raise ValueError(f"{endpoint.label}: DNS resolution failed") from exc

    addresses = set()
    for answer in answers:
        try:
            raw_address = answer[4][0].split("%", 1)[0]
            addresses.add(ipaddress.ip_address(raw_address))
        except (IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                f"{endpoint.label}: DNS returned a malformed address"
            ) from exc
    if not addresses:
        raise ValueError(f"{endpoint.label}: DNS returned no addresses")
    if any(address not in endpoint.network for address in addresses):
        # Do not include the answer or CIDR in logs. Operators can compare the
        # non-secret deployment values with DNS through their approved tooling.
        raise ValueError(
            f"{endpoint.label}: at least one DNS address is outside its approved CIDR"
        )
    return len(addresses)


def validate_private_dns(
    environment: Mapping[str, str],
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> tuple[int, int]:
    """Validate every configured dependency and return endpoint/address counts."""
    endpoints = configured_endpoints(environment)
    address_count = sum(
        resolve_endpoint(endpoint, resolver=resolver) for endpoint in endpoints
    )
    return len(endpoints), address_count


def main() -> int:
    try:
        endpoint_count, address_count = validate_private_dns(os.environ)
    except ValueError as exc:
        raise SystemExit(f"Private dependency DNS preflight failed: {exc}") from exc
    print(
        "Private dependency DNS preflight passed for "
        f"{endpoint_count} endpoints and {address_count} approved addresses."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
