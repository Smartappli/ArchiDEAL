#!/usr/bin/env python3
"""Give one-shot production Jobs a fresh identity for every invocation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import secrets

import yaml


DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")
MAX_INVOCATION_ID_LENGTH = 32


def new_invocation_id() -> str:
    """Return a short, sortable and collision-resistant DNS label."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{timestamp}-{secrets.token_hex(6)}"


def _load_job(path: Path, expected_name: str) -> dict:
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise ValueError(f"{path} must contain exactly one YAML document")
    job = documents[0]
    labels = job.get("metadata", {}).get("labels", {})
    if (
        job.get("apiVersion") != "batch/v1"
        or job.get("kind") != "Job"
        or labels.get("app.kubernetes.io/name") != expected_name
    ):
        raise ValueError(f"{path} is not the expected {expected_name} Job")
    return job


def _stamp_job(job: dict, *, name: str, invocation_id: str) -> None:
    if len(name) > 63 or not DNS_LABEL.fullmatch(name):
        raise ValueError(f"generated Kubernetes Job name is invalid: {name!r}")
    labels = job["metadata"].setdefault("labels", {})
    pod_labels = job["spec"]["template"]["metadata"].setdefault("labels", {})
    release = labels.get("archideal.io/release")
    if not isinstance(release, str) or not release:
        raise ValueError("one-shot Job has no archideal.io/release label")
    labels["archideal.io/invocation"] = invocation_id
    pod_labels["archideal.io/invocation"] = invocation_id
    pod_labels["archideal.io/release"] = release
    job["metadata"]["name"] = name


def _set_smoke_device(job: dict, device_id: str) -> None:
    containers = job["spec"]["template"]["spec"].get("containers", [])
    if len(containers) != 1:
        raise ValueError("the production smoke Job must contain exactly one container")
    matches = [
        item
        for item in containers[0].get("env", [])
        if item.get("name") == "SMOKE_DEVICE_ID"
    ]
    if len(matches) != 1 or "valueFrom" in matches[0]:
        raise ValueError("the production smoke Job must define one literal SMOKE_DEVICE_ID")
    matches[0]["value"] = device_id


def prepare_jobs(
    *,
    bootstrap: Path | None,
    synthetic: Path | None,
    private_network: Path | None = None,
    kafka: Path | None = None,
    invocation_id: str | None = None,
) -> dict[str, str]:
    """Specialize rendered Job templates in place and return their identities."""
    if (
        bootstrap is None
        and synthetic is None
        and private_network is None
        and kafka is None
    ):
        raise ValueError("at least one Job path is required")
    invocation_id = invocation_id or new_invocation_id()
    if (
        len(invocation_id) > MAX_INVOCATION_ID_LENGTH
        or not DNS_LABEL.fullmatch(invocation_id)
    ):
        raise ValueError(
            "invocation ID must be a DNS label of at most "
            f"{MAX_INVOCATION_ID_LENGTH} characters"
        )

    prepared: list[tuple[Path, dict]] = []
    result = {"invocation_id": invocation_id}
    if bootstrap is not None:
        bootstrap_job = _load_job(bootstrap, "apisix-bootstrap")
        bootstrap_name = f"apisix-bootstrap-{invocation_id}"
        _stamp_job(
            bootstrap_job,
            name=bootstrap_name,
            invocation_id=invocation_id,
        )
        prepared.append((bootstrap, bootstrap_job))
        result["apisix_bootstrap_job"] = bootstrap_name

    if synthetic is not None:
        synthetic_job = _load_job(synthetic, "production-smoke")
        synthetic_name = f"production-smoke-{invocation_id}"
        device_id = f"archideal-smoke-{invocation_id}"
        _stamp_job(
            synthetic_job,
            name=synthetic_name,
            invocation_id=invocation_id,
        )
        _set_smoke_device(synthetic_job, device_id)
        prepared.append((synthetic, synthetic_job))
        result["production_smoke_job"] = synthetic_name
        result["smoke_device_id"] = device_id

    if private_network is not None:
        private_network_job = _load_job(
            private_network,
            "private-network-preflight",
        )
        private_network_name = f"private-network-preflight-{invocation_id}"
        _stamp_job(
            private_network_job,
            name=private_network_name,
            invocation_id=invocation_id,
        )
        prepared.append((private_network, private_network_job))
        result["private_network_preflight_job"] = private_network_name

    if kafka is not None:
        kafka_job = _load_job(kafka, "kafka-preflight")
        kafka_name = f"kafka-preflight-{invocation_id}"
        _stamp_job(
            kafka_job,
            name=kafka_name,
            invocation_id=invocation_id,
        )
        prepared.append((kafka, kafka_job))
        result["kafka_preflight_job"] = kafka_name

    # Validate every input before replacing either file, so malformed paired Jobs
    # cannot leave the ephemeral render only half-specialized.
    for path, job in prepared:
        path.write_text(yaml.safe_dump(job, sort_keys=False), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=Path)
    parser.add_argument("--synthetic", type=Path)
    parser.add_argument("--private-network", type=Path)
    parser.add_argument("--kafka", type=Path)
    parser.add_argument("--invocation-id")
    parser.add_argument("--metadata-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare_jobs(
            bootstrap=args.bootstrap,
            synthetic=args.synthetic,
            private_network=args.private_network,
            kafka=args.kafka,
            invocation_id=args.invocation_id,
        )
        args.metadata_output.write_text(
            json.dumps(result, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
