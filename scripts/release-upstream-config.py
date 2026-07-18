#!/usr/bin/env python3
"""Validate reviewed upstream image pins and emit a GitHub Actions matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


SCHEMA_VERSION = "archideal.upstream-pins/v1"
EXPECTED_VALUES_KEYS = {"IMAGE_APISIX", "IMAGE_OAUTH2_PROXY"}
ENTRY_FIELDS = {
    "name",
    "values_key",
    "expected_repository",
    "source_repository",
    "build_repository",
    "source_release_prefix",
    "minimum_version",
    "image_tag_suffix",
    "runtime_contract",
    "image",
    "source_release",
}
RUNTIME_CONTRACTS = {
    "apisix-version-non-root-v1",
    "oauth2-proxy-sensitive-flags-v1",
}
IMAGE_RE = re.compile(
    r"(?P<repository>[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+)"
    r"@sha256:(?P<digest>[0-9a-f]{64})"
)
SEMVER_RE = re.compile(r"v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+)")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VALUES_KEY_RE = re.compile(r"IMAGE_[A-Z0-9_]+")
TAG_SUFFIX_RE = re.compile(r"(?:|-[a-z0-9][a-z0-9.-]*)")


class ConfigError(ValueError):
    """The reviewed upstream pin file is not safe to consume."""


def _required_string(entry: dict[str, object], field: str, index: int) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or (field != "image_tag_suffix" and not value):
        raise ConfigError(f"images[{index}].{field} must be a non-empty string")
    return value


def _github_repository_url(value: str, field: str, index: int) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", parsed.path)
    ):
        raise ConfigError(f"images[{index}].{field} must be an exact GitHub repository URL")


def _version_tuple(value: str) -> tuple[int, int, int]:
    return tuple(map(int, value.split(".")))  # type: ignore[return-value]


def load_matrix(config_path: Path) -> dict[str, list[dict[str, str]]]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {config_path}: {exc}") from exc

    if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "images"}:
        raise ConfigError("top-level fields must be exactly schemaVersion and images")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise ConfigError(f"schemaVersion must be {SCHEMA_VERSION}")
    images = payload["images"]
    if not isinstance(images, list):
        raise ConfigError("images must be a list")

    matrix: list[dict[str, str]] = []
    values_keys: set[str] = set()
    names: set[str] = set()
    for index, raw_entry in enumerate(images):
        if not isinstance(raw_entry, dict) or set(raw_entry) != ENTRY_FIELDS:
            raise ConfigError(
                f"images[{index}] fields must be exactly {sorted(ENTRY_FIELDS)}"
            )
        entry = {
            field: _required_string(raw_entry, field, index) for field in ENTRY_FIELDS
        }

        name = entry["name"]
        values_key = entry["values_key"]
        if not SLUG_RE.fullmatch(name) or name in names:
            raise ConfigError(f"images[{index}].name must be a unique lowercase slug")
        if not VALUES_KEY_RE.fullmatch(values_key) or values_key in values_keys:
            raise ConfigError(f"images[{index}].values_key must be a unique image key")
        names.add(name)
        values_keys.add(values_key)

        image_match = IMAGE_RE.fullmatch(entry["image"])
        if image_match is None:
            raise ConfigError(
                f"images[{index}].image must be a lowercase repository@sha256 reference"
            )
        if image_match.group("repository") != entry["expected_repository"]:
            raise ConfigError(f"images[{index}].image does not use expected_repository")
        if image_match.group("digest") == "0" * 64:
            raise ConfigError(f"images[{index}].image must not use a placeholder digest")

        _github_repository_url(entry["source_repository"], "source_repository", index)
        _github_repository_url(entry["build_repository"], "build_repository", index)
        prefix = entry["source_release_prefix"]
        if not prefix.startswith(entry["source_repository"] + "/releases/tag/"):
            raise ConfigError(
                f"images[{index}].source_release_prefix must belong to source_repository"
            )
        if not entry["source_release"].startswith(prefix):
            raise ConfigError(f"images[{index}].source_release must use the approved prefix")
        source_tag = entry["source_release"][len(prefix) :]
        source_match = SEMVER_RE.fullmatch(source_tag)
        minimum_match = SEMVER_RE.fullmatch(entry["minimum_version"])
        if source_match is None or minimum_match is None:
            raise ConfigError(
                f"images[{index}] must select a stable semantic source release"
            )
        selected_version = source_match.group("version")
        minimum_version = minimum_match.group("version")
        if _version_tuple(selected_version) < _version_tuple(minimum_version):
            raise ConfigError(
                f"images[{index}] selects {selected_version} below {minimum_version}"
            )
        if not TAG_SUFFIX_RE.fullmatch(entry["image_tag_suffix"]):
            raise ConfigError(f"images[{index}].image_tag_suffix is not a safe tag suffix")
        if entry["runtime_contract"] not in RUNTIME_CONTRACTS:
            raise ConfigError(f"images[{index}].runtime_contract is unsupported")

        matrix.append(entry)

    if values_keys != EXPECTED_VALUES_KEYS:
        raise ConfigError(
            "upstream pins must contain exactly " + ", ".join(sorted(EXPECTED_VALUES_KEYS))
        )
    return {"include": matrix}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--github-output",
        type=Path,
        help="append the validated matrix to this GitHub Actions output file",
    )
    args = parser.parse_args()

    try:
        matrix = load_matrix(args.config)
    except ConfigError as exc:
        print(f"Invalid upstream pin configuration: {exc}", file=sys.stderr)
        return 1

    serialized = json.dumps(matrix, separators=(",", ":"), sort_keys=True)
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"matrix={serialized}\n")
    print(
        "Validated immutable upstream pins: "
        + ", ".join(item["name"] for item in matrix["include"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
