#!/usr/bin/env python3
"""Validate the exact, freshly prepared production synthetic Job."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")


def validate_production_smoke_job(
    job: dict,
    *,
    expected_release: str,
    expected_invocation: str,
    expected_image: str,
) -> None:
    """Reject a completed Job unless identity, image and outcome are exact."""
    if not isinstance(job, dict) or job.get("kind") != "Job":
        raise ValueError("smoke snapshot must contain one Job object")
    expected_name = f"production-smoke-{expected_invocation}"
    if len(expected_name) > 63 or not DNS_LABEL.fullmatch(expected_name):
        raise ValueError("expected smoke Job name is not a valid DNS label")

    metadata = job.get("metadata", {})
    if metadata.get("name") != expected_name:
        raise ValueError("smoke Job name does not match this invocation")
    if metadata.get("deletionTimestamp") is not None:
        raise ValueError("smoke Job is terminating")
    if not metadata.get("uid") or not metadata.get("creationTimestamp"):
        raise ValueError("smoke Job has no Kubernetes creation identity")
    labels = metadata.get("labels", {})
    expected_labels = {
        "app.kubernetes.io/name": "production-smoke",
        "archideal.io/release": expected_release,
        "archideal.io/invocation": expected_invocation,
    }
    for name, value in expected_labels.items():
        if labels.get(name) != value:
            raise ValueError(f"smoke Job label {name} does not match this invocation")

    pod_template = job.get("spec", {}).get("template", {})
    pod_labels = pod_template.get("metadata", {}).get("labels", {})
    for name in ("archideal.io/release", "archideal.io/invocation"):
        if pod_labels.get(name) != expected_labels[name]:
            raise ValueError(f"smoke Pod template label {name} is not bound")
    pod_spec = pod_template.get("spec", {})
    containers = pod_spec.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise ValueError("smoke Job must contain exactly one container")
    container = containers[0]
    if container.get("name") != "publish" or container.get("image") != expected_image:
        raise ValueError("smoke Job image does not match IMAGE_DEALIOT_CONSOLE")
    if pod_spec.get("initContainers") not in (None, []):
        raise ValueError("smoke Job must not inject additional init containers")

    status = job.get("status", {})
    completed = any(
        condition.get("type") == "Complete" and condition.get("status") == "True"
        for condition in status.get("conditions", [])
        if isinstance(condition, dict)
    )
    if (
        not completed
        or status.get("succeeded") != 1
        or status.get("active", 0) != 0
        or status.get("failed", 0) != 0
    ):
        raise ValueError("smoke Job did not complete exactly once without failure")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--expected-invocation", required=True)
    parser.add_argument("--expected-image", required=True)
    args = parser.parse_args()
    try:
        validate_production_smoke_job(
            json.loads(args.job.read_text(encoding="utf-8")),
            expected_release=args.expected_release,
            expected_invocation=args.expected_invocation,
            expected_image=args.expected_image,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(
        f"Production smoke invocation {args.expected_invocation} is complete "
        f"for release {args.expected_release}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
