#!/usr/bin/env python3
"""Validate the live ingress-nginx identity behind the trusted-proxy CIDR."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from typing import Sequence, TextIO


OFFICIAL_CONTROLLER_CLASS = "k8s.io/ingress-nginx"
DEFAULT_INGRESS_CLASS = "nginx"


def _flag_value(arguments: Sequence[str], name: str, default: str) -> str:
    """Return the effective value of a Go-style --flag option."""
    value = default
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        prefix = f"--{name}="
        if argument.startswith(prefix):
            value = argument[len(prefix) :]
        elif argument == f"--{name}":
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                raise ValueError(f"controller argument --{name} has no value")
            index += 1
            value = arguments[index]
        index += 1
    if not value:
        raise ValueError(f"controller argument --{name} has an empty value")
    return value


def _is_ready(pod: dict) -> bool:
    metadata = pod.get("metadata", {})
    status = pod.get("status", {})
    return (
        not metadata.get("deletionTimestamp")
        and status.get("phase") == "Running"
        and any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in status.get("conditions", [])
        )
    )


def _controller_container(pod: dict) -> dict | None:
    labels = pod.get("metadata", {}).get("labels", {})
    if labels.get("app.kubernetes.io/name") != "ingress-nginx" or labels.get(
        "app.kubernetes.io/component"
    ) != "controller":
        return None
    return next(
        (
            container
            for container in pod.get("spec", {}).get("containers", [])
            if container.get("name") == "controller"
        ),
        None,
    )


def _pod_addresses(pod: dict) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    status = pod.get("status", {})
    raw_addresses = [
        item.get("ip")
        for item in status.get("podIPs", [])
        if isinstance(item, dict) and item.get("ip")
    ]
    if not raw_addresses and status.get("podIP"):
        raw_addresses = [status["podIP"]]
    addresses = set()
    for raw_address in raw_addresses:
        try:
            addresses.add(ipaddress.ip_address(raw_address.split("%", 1)[0]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("a Ready ingress controller has a malformed Pod IP") from exc
    if not addresses:
        raise ValueError("a Ready ingress controller has no Pod IP")
    return addresses


def validate_ingress_controllers(
    pod_list: dict,
    *,
    ingress_class: str,
    controller_class: str,
    proxy_cidr: str,
) -> tuple[int, int]:
    """Return matching Ready controller/address counts or fail closed."""
    if controller_class != OFFICIAL_CONTROLLER_CLASS:
        raise ValueError(
            f"IngressClass controller must be {OFFICIAL_CONTROLLER_CLASS}"
        )
    try:
        trusted_network = ipaddress.ip_network(proxy_cidr, strict=True)
    except ValueError as exc:
        raise ValueError("INGRESS_PROXY_CIDR is not a canonical network") from exc

    items = pod_list.get("items") if isinstance(pod_list, dict) else None
    if not isinstance(items, list):
        raise ValueError("kubectl input is not a PodList")

    matching: list[dict] = []
    for pod in items:
        if not isinstance(pod, dict) or not _is_ready(pod):
            continue
        container = _controller_container(pod)
        if container is None:
            continue
        command = container.get("command") or []
        args = container.get("args") or []
        if not isinstance(command, list) or not isinstance(args, list):
            raise ValueError("ingress controller command and arguments must be lists")
        arguments = [*command, *args]
        if not all(isinstance(argument, str) for argument in arguments):
            raise ValueError("ingress controller arguments must be strings")
        effective_controller_class = _flag_value(
            arguments,
            "controller-class",
            OFFICIAL_CONTROLLER_CLASS,
        )
        effective_ingress_class = _flag_value(
            arguments,
            "ingress-class",
            DEFAULT_INGRESS_CLASS,
        )
        if (
            effective_controller_class == controller_class
            and effective_ingress_class == ingress_class
        ):
            matching.append(pod)

    if not matching:
        raise ValueError(
            "no Ready ingress-nginx controller serves the configured IngressClass"
        )

    address_count = 0
    for pod in matching:
        if pod.get("spec", {}).get("hostNetwork") is True:
            raise ValueError(
                "hostNetwork ingress controllers cannot establish the trusted-proxy contract"
            )
        addresses = _pod_addresses(pod)
        if any(address not in trusted_network for address in addresses):
            # Avoid printing live Pod addresses or infrastructure ranges.
            raise ValueError(
                "a Ready ingress controller Pod IP is outside INGRESS_PROXY_CIDR"
            )
        address_count += len(addresses)

    return len(matching), address_count


def _load_pods(stream: TextIO) -> dict:
    try:
        data = json.load(stream)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("kubectl returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("kubectl input is not a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingress-class", required=True)
    parser.add_argument("--controller-class", required=True)
    parser.add_argument("--proxy-cidr", required=True)
    args = parser.parse_args()
    try:
        pod_list = _load_pods(sys.stdin)
        controller_count, address_count = validate_ingress_controllers(
            pod_list,
            ingress_class=args.ingress_class,
            controller_class=args.controller_class,
            proxy_cidr=args.proxy_cidr,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(
        "Ingress controller preflight passed for "
        f"{controller_count} Ready controllers and {address_count} trusted addresses."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
