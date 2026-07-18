#!/usr/bin/env python3
"""Stamp and split production controllers for ordered, single-pass rollouts."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

import yaml


REVISION = re.compile(r"^[0-9a-f]{64}$")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")


def prepare(inputs: list[Path], output: Path, revision: str) -> list[str]:
    """Write one stamped Deployment/StatefulSet manifest per controller."""
    if not REVISION.fullmatch(revision):
        raise ValueError("runtime revision must be exactly 64 lowercase hexadecimal characters")
    if output.exists():
        raise ValueError("rollout output directory already exists")
    output.mkdir(parents=True)
    names: list[str] = []
    for source in inputs:
        for document in yaml.safe_load_all(source.read_text(encoding="utf-8")):
            if not isinstance(document, dict):
                continue
            kind = document.get("kind")
            name = document.get("metadata", {}).get("name")
            if kind not in {"Deployment", "StatefulSet"} or not isinstance(name, str):
                raise ValueError(f"unexpected rollout document in {source}")
            if not DNS_LABEL.fullmatch(name) or name in names:
                raise ValueError(f"invalid or duplicate controller name: {name!r}")
            annotations = document["spec"]["template"]["metadata"].setdefault(
                "annotations",
                {},
            )
            annotations["archideal.io/runtime-revision"] = revision
            destination = output / f"{name}.yaml"
            destination.write_text(
                yaml.safe_dump(document, sort_keys=False),
                encoding="utf-8",
            )
            names.append(name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()
    if not all(path.is_file() for path in args.inputs):
        parser.error("every rollout input must be an existing file")
    try:
        names = prepare(args.inputs, args.output, args.revision)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        if args.output.exists():
            shutil.rmtree(args.output)
        parser.error(str(exc))
    if not names:
        shutil.rmtree(args.output)
        parser.error("no rollout controllers were found")
    for name in names:
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
