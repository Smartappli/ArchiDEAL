#!/usr/bin/env python3
"""Verify a signed ArchiDEAL release and bind it to production values.

The renderer intentionally remains usable without network access. This verifier is the
promotion gate: it validates the signed release record, every evidence hash and the
keyless signatures/attestations of all first-party images before kubectl is invoked.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import yaml

import render as renderer


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
DEFAULT_POLICY = ROOT / "supply-chain-policy.yaml"
RELEASE_SCHEMA = "archideal.release/v2"
POLICY_SCHEMA = "archideal.supply-chain-policy/v1"
UPSTREAM_REVIEW_SCHEMA = "archideal.upstream-review/v2"
REGISTRY_TAG_PROOF_SCHEMA = "archideal.registry-tag-proof/v1"
SCAN_POLICY = "trivy:HIGH,CRITICAL:no-unfixed-exception"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
STABLE_VERSION = re.compile(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)$")
UPSTREAM_POLICY_FLOORS = {
    "IMAGE_APISIX": {
        "minimumVersion": "3.14.1",
        "imageTagSuffix": "-debian",
        "runtimeContract": "apisix-version-non-root-v1",
    },
    "IMAGE_OAUTH2_PROXY": {
        "minimumVersion": "7.15.3",
        "imageTagSuffix": "",
        "runtimeContract": "oauth2-proxy-sensitive-flags-v1",
    },
}
OAUTH2_PROXY_REQUIRED_FLAGS = (
    "provider",
    "oidc-issuer-url",
    "oidc-groups-claim",
    "oidc-extra-audience",
    "allowed-group",
    "scope",
    "code-challenge-method",
    "email-domain",
    "reverse-proxy",
    "upstream",
    "http-address",
    "metrics-address",
    "redirect-url",
    "proxy-prefix",
    "skip-provider-button",
    "silence-ping-logging",
    "trusted-proxy-ip",
    "skip-auth-route",
    "bearer-token-login-fallback",
    "extra-jwt-issuers",
    "session-store-type",
    "skip-jwt-bearer-tokens",
    "pass-authorization-header",
    "set-authorization-header",
    "pass-access-token",
    "set-xauthrequest",
    "pass-user-headers",
    "cookie-name",
    "cookie-path",
    "cookie-secure",
    "cookie-httponly",
    "cookie-samesite",
    "cookie-refresh",
    "cookie-expire",
    "cookie-csrf-per-request",
    "cookie-csrf-expire",
)


class ReleaseVerificationError(ValueError):
    """Raised when a release cannot be trusted for promotion."""


def fail(message: str) -> None:
    raise ReleaseVerificationError(message)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path}: {exc}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object.")
    actual = set(value)
    if actual != expected:
        fail(
            f"{label} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def parse_stable_version(value: Any, label: str, *, allow_v: bool = True) -> tuple[int, int, int]:
    if not isinstance(value, str):
        fail(f"{label} must be a stable semantic version.")
    match = STABLE_VERSION.fullmatch(value)
    if not match or (not allow_v and value.startswith("v")):
        fail(f"{label} must be a stable semantic version.")
    return tuple(int(part) for part in match.groups())


def load_policy(path: Path) -> dict[str, Any]:
    policy = yaml.load(path.read_text(encoding="utf-8"), Loader=renderer.UniqueKeyLoader)
    policy = require_keys(policy, {"schemaVersion", "release", "images"}, "policy")
    if policy["schemaVersion"] != POLICY_SCHEMA:
        fail(f"Unsupported policy schema: {policy['schemaVersion']!r}")
    release = require_keys(
        policy["release"],
        {
            "repository",
            "workflowPath",
            "workflowRef",
            "certificateIssuer",
            "certificateIdentity",
        },
        "policy.release",
    )
    if release != {
        "repository": "Smartappli/ArchiDEAL",
        "workflowPath": ".github/workflows/release-images.yml",
        "workflowRef": "refs/heads/main",
        "certificateIssuer": "https://token.actions.githubusercontent.com",
        "certificateIdentity": (
            "https://github.com/Smartappli/ArchiDEAL/.github/workflows/"
            "release-images.yml@refs/heads/main"
        ),
    }:
        fail("The release trust root differs from the reviewed ArchiDEAL main workflow.")
    images = policy["images"]
    if not isinstance(images, dict) or set(images) != {
        key for key in renderer.REQUIRED if key.startswith("IMAGE_")
    }:
        fail("Policy must define exactly all ten production image value keys.")
    components: set[str] = set()
    for values_key, image in images.items():
        kind = image.get("kind") if isinstance(image, dict) else None
        required = {"component", "kind", "repository"}
        if kind == "upstream":
            required |= {
                "sourceRepository",
                "buildRepository",
                "sourceReleasePrefix",
                "minimumVersion",
                "imageTagSuffix",
                "runtimeContract",
            }
        elif kind == "first-party":
            required |= {"context", "dockerfile"}
        else:
            fail(f"policy.images.{values_key}.kind is invalid.")
        image = require_keys(image, required, f"policy.images.{values_key}")
        component = image["component"]
        if (
            not isinstance(component, str)
            or not component
            or component in components
            or not isinstance(image["repository"], str)
            or "@" in image["repository"]
            or "://" in image["repository"]
        ):
            fail(f"policy.images.{values_key} has an unsafe component or repository.")
        if kind == "upstream":
            contract = UPSTREAM_POLICY_FLOORS.get(values_key)
            if contract is None:
                fail(f"policy.images.{values_key} is not an approved upstream image.")
            minimum = parse_stable_version(
                image["minimumVersion"],
                f"policy.images.{values_key}.minimumVersion",
                allow_v=False,
            )
            floor = parse_stable_version(
                contract["minimumVersion"],
                f"built-in minimum for {values_key}",
                allow_v=False,
            )
            if (
                minimum < floor
                or image["imageTagSuffix"] != contract["imageTagSuffix"]
                or image["runtimeContract"] != contract["runtimeContract"]
            ):
                fail(f"policy.images.{values_key} weakens the upstream runtime contract.")
        components.add(component)
    return policy


def image_repository(reference: str) -> str:
    match = renderer.IMAGE.fullmatch(reference)
    if not match:
        fail(f"Image is not digest-pinned: {reference!r}")
    return reference.rsplit("@sha256:", 1)[0]


def resolve_evidence(
    evidence_dir: Path,
    record: Any,
    label: str,
    used_names: set[str],
) -> Path:
    record = require_keys(record, {"file", "sha256"}, label)
    name = record["file"]
    expected_hash = record["sha256"]
    if (
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or name in {".", ".."}
        or name in used_names
        or not isinstance(expected_hash, str)
        or not SHA256.fullmatch(expected_hash)
    ):
        fail(f"{label} has an unsafe or duplicate evidence record.")
    used_names.add(name)
    path = evidence_dir / name
    if not path.is_file() or path.is_symlink():
        fail(f"Evidence file is missing or is a symlink: {name}")
    if file_sha256(path) != expected_hash:
        fail(f"Evidence digest mismatch: {name}")
    return path


def validate_sbom(path: Path, label: str) -> None:
    sbom = load_json(path)
    if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX":
        fail(f"{label} is not a CycloneDX JSON SBOM.")


def validate_scan(path: Path, label: str) -> None:
    scan = load_json(path)
    runs = scan.get("runs") if isinstance(scan, dict) else None
    if not isinstance(runs, list) or any(
        not isinstance(run, dict) or run.get("results", [])
        for run in runs
    ):
        fail(f"{label} contains a HIGH/CRITICAL vulnerability or invalid SARIF.")


def validate_registry_tag_proof(
    path: Path,
    *,
    component: str,
    reference: str,
    source_release: str,
    source_tag: str,
    approved_tag: str,
    repository: str,
    label: str,
) -> None:
    proof = require_keys(
        load_json(path),
        {
            "schemaVersion",
            "component",
            "sourceRelease",
            "sourceTag",
            "approvedImageTag",
            "taggedReference",
            "resolvedDigest",
            "immutableReference",
            "registryManifest",
        },
        label,
    )
    resolved_digest = f"sha256:{reference.rsplit('@sha256:', 1)[1]}"
    expected = {
        "schemaVersion": REGISTRY_TAG_PROOF_SCHEMA,
        "component": component,
        "sourceRelease": source_release,
        "sourceTag": source_tag,
        "approvedImageTag": approved_tag,
        "taggedReference": f"{repository}:{approved_tag}",
        "resolvedDigest": resolved_digest,
        "immutableReference": reference,
    }
    if {key: proof[key] for key in expected} != expected:
        fail(f"{label} does not bind the approved source tag to this digest.")
    manifest = proof["registryManifest"]
    media_type = manifest.get("mediaType") if isinstance(manifest, dict) else None
    if (
        not isinstance(manifest, dict)
        or manifest.get("schemaVersion") != 2
        or manifest.get("digest") != resolved_digest
        or not isinstance(media_type, str)
        or not re.fullmatch(
            r"application/vnd\.(?:oci\.image|docker\.distribution)\..+json",
            media_type,
        )
    ):
        fail(f"{label} lacks the registry manifest digest resolved by Buildx.")


def validate_upstream_runtime_output(
    path: Path,
    *,
    contract: str,
    release_version: str,
    label: str,
) -> None:
    if path.stat().st_size == 0 or path.stat().st_size > 1024 * 1024:
        fail(f"{label} has an invalid size.")
    try:
        output = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        fail(f"{label} is not UTF-8 text.")
    if contract == "apisix-version-non-root-v1":
        if not re.search(
            rf"(?<![0-9]){re.escape(release_version)}(?![0-9])",
            output,
        ):
            fail(f"{label} does not report the approved APISIX version.")
        return
    if contract == "oauth2-proxy-sensitive-flags-v1":
        missing = [
            flag
            for flag in OAUTH2_PROXY_REQUIRED_FLAGS
            if not re.search(
                rf"(?<![A-Za-z0-9-])--{re.escape(flag)}(?![A-Za-z0-9-])",
                output,
            )
        ]
        if missing:
            fail(f"{label} lacks required oauth2-proxy flags: {missing}")
        return
    fail(f"{label} uses an unsupported runtime contract.")


def validate_archived_sigstore_bundle(path: Path, label: str) -> None:
    """Validate archival bundle shape only; Cosign v3 verifies image objects in-registry."""
    bundle = load_json(path)
    media_type = bundle.get("mediaType") if isinstance(bundle, dict) else None
    verification_material = (
        bundle.get("verificationMaterial") if isinstance(bundle, dict) else None
    )
    payloads = [
        bundle.get(name)
        for name in ("messageSignature", "dsseEnvelope")
        if isinstance(bundle, dict) and bundle.get(name) is not None
    ]
    if (
        not isinstance(media_type, str)
        or not re.fullmatch(
            r"application/vnd\.dev\.sigstore\.bundle(?:\.v0\.[0-9]+\+json|\+json;version=0\.[0-9]+)",
            media_type,
        )
        or not isinstance(verification_material, dict)
        or not verification_material
        or len(payloads) != 1
        or not isinstance(payloads[0], dict)
        or not payloads[0]
    ):
        fail(f"{label} is not a structurally complete archived Sigstore bundle.")


def validate_timestamp(value: Any) -> None:
    if not isinstance(value, str):
        fail("generatedAt must be an RFC3339 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("generatedAt must be an RFC3339 timestamp.")
    if parsed.tzinfo is None:
        fail("generatedAt must include a timezone.")


def validate_manifest(
    manifest: Any,
    *,
    values: dict[str, str],
    policy: dict[str, Any],
    policy_path: Path,
    evidence_dir: Path,
) -> list[str]:
    manifest = require_keys(
        manifest,
        {
            "schemaVersion",
            "repository",
            "revision",
            "releaseId",
            "generatedAt",
            "workflow",
            "policySha256",
            "images",
        },
        "release manifest",
    )
    release_policy = policy["release"]
    if manifest["schemaVersion"] != RELEASE_SCHEMA:
        fail(f"Unsupported release schema: {manifest['schemaVersion']!r}")
    if manifest["repository"] != release_policy["repository"]:
        fail("Release repository does not match the trust policy.")
    if not isinstance(manifest["revision"], str) or not REVISION.fullmatch(
        manifest["revision"]
    ):
        fail("Release revision must be a full lowercase Git SHA-1.")
    release_id = manifest["releaseId"]
    if (
        not isinstance(release_id, str)
        or not renderer.RELEASE.fullmatch(release_id)
        or len(release_id) > 39
        or release_id in {"none", "pending"}
    ):
        fail("Release releaseId must be a lowercase DNS label of at most 39 characters.")
    if values["RELEASE_ID"] != release_id:
        fail("Values RELEASE_ID does not match the signed releaseId.")
    validate_timestamp(manifest["generatedAt"])
    workflow = require_keys(
        manifest["workflow"],
        {"path", "ref", "runId", "runAttempt", "event"},
        "release manifest.workflow",
    )
    if (
        workflow["path"] != release_policy["workflowPath"]
        or workflow["ref"] != release_policy["workflowRef"]
        or not isinstance(workflow["runId"], str)
        or not workflow["runId"].isdigit()
        or not isinstance(workflow["runAttempt"], str)
        or not workflow["runAttempt"].isdigit()
        or workflow["event"] not in {"push", "workflow_dispatch"}
    ):
        fail("Release workflow metadata is not an approved main-branch run.")
    if manifest["policySha256"] != file_sha256(policy_path):
        fail("Release was not assembled with this exact supply-chain policy.")

    images = manifest["images"]
    if not isinstance(images, list) or len(images) != len(policy["images"]):
        fail("Release must contain exactly ten image records.")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in images:
        if not isinstance(entry, dict) or not isinstance(entry.get("valuesKey"), str):
            fail("Each release image must have a valuesKey.")
        if entry["valuesKey"] in indexed:
            fail(f"Duplicate release image key: {entry['valuesKey']}")
        indexed[entry["valuesKey"]] = entry
    if set(indexed) != set(policy["images"]):
        fail("Release image keys do not match the production policy.")

    used_evidence: set[str] = set()
    first_party_references: list[str] = []
    for values_key, image_policy in policy["images"].items():
        entry = indexed[values_key]
        common_keys = {"valuesKey", "component", "kind", "reference", "evidence"}
        if image_policy["kind"] == "first-party":
            entry = require_keys(
                entry,
                common_keys | {"revision"},
                f"release image {values_key}",
            )
        else:
            entry = require_keys(
                entry,
                common_keys
                | {"sourceRepository", "buildRepository", "sourceRelease"},
                f"release image {values_key}",
            )
        if (
            entry["valuesKey"] != values_key
            or entry["component"] != image_policy["component"]
            or entry["kind"] != image_policy["kind"]
            or entry["reference"] != values[values_key]
            or image_repository(entry["reference"]) != image_policy["repository"]
        ):
            fail(f"{values_key} does not match the signed release and repository policy.")

        evidence = entry["evidence"]
        if image_policy["kind"] == "first-party":
            if entry["revision"] != manifest["revision"]:
                fail(f"{values_key} was not built from the release revision.")
            evidence = require_keys(
                evidence,
                {
                    "signature",
                    "attestations",
                    "scanPolicy",
                    "sbom",
                    "scan",
                    "provenance",
                    "signatureBundle",
                    "sbomAttestationBundle",
                    "provenanceAttestationBundle",
                },
                f"{values_key}.evidence",
            )
            if evidence["signature"] != {
                "issuer": release_policy["certificateIssuer"],
                "identity": release_policy["certificateIdentity"],
            } or evidence["attestations"] != ["cyclonedx", "slsaprovenance1"]:
                fail(f"{values_key} lacks the required keyless signature attestations.")
            if evidence["scanPolicy"] != SCAN_POLICY:
                fail(f"{values_key} has a weaker vulnerability policy.")
            sbom_path = resolve_evidence(
                evidence_dir, evidence["sbom"], f"{values_key}.sbom", used_evidence
            )
            scan_path = resolve_evidence(
                evidence_dir, evidence["scan"], f"{values_key}.scan", used_evidence
            )
            provenance_path = resolve_evidence(
                evidence_dir,
                evidence["provenance"],
                f"{values_key}.provenance",
                used_evidence,
            )
            signature_bundle_path = resolve_evidence(
                evidence_dir,
                evidence["signatureBundle"],
                f"{values_key}.signatureBundle",
                used_evidence,
            )
            sbom_bundle_path = resolve_evidence(
                evidence_dir,
                evidence["sbomAttestationBundle"],
                f"{values_key}.sbomAttestationBundle",
                used_evidence,
            )
            provenance_bundle_path = resolve_evidence(
                evidence_dir,
                evidence["provenanceAttestationBundle"],
                f"{values_key}.provenanceAttestationBundle",
                used_evidence,
            )
            validate_sbom(sbom_path, f"{values_key}.sbom")
            validate_scan(scan_path, f"{values_key}.scan")
            validate_archived_sigstore_bundle(
                signature_bundle_path, f"{values_key}.signatureBundle"
            )
            validate_archived_sigstore_bundle(
                sbom_bundle_path, f"{values_key}.sbomAttestationBundle"
            )
            validate_archived_sigstore_bundle(
                provenance_bundle_path,
                f"{values_key}.provenanceAttestationBundle",
            )
            provenance = require_keys(
                load_json(provenance_path),
                {"buildDefinition", "runDetails"},
                f"{values_key}.provenance",
            )
            build_definition = require_keys(
                provenance["buildDefinition"],
                {
                    "buildType",
                    "externalParameters",
                    "internalParameters",
                    "resolvedDependencies",
                },
                f"{values_key}.provenance.buildDefinition",
            )
            external_parameters = require_keys(
                build_definition["externalParameters"],
                {
                    "repository",
                    "revision",
                    "workflow",
                    "context",
                    "dockerfile",
                    "platform",
                },
                f"{values_key}.provenance.externalParameters",
            )
            run_details = require_keys(
                provenance["runDetails"],
                {"builder", "metadata"},
                f"{values_key}.provenance.runDetails",
            )
            expected_invocation = (
                f"https://github.com/{manifest['repository']}/actions/runs/"
                f"{workflow['runId']}/attempts/{workflow['runAttempt']}"
            )
            if (
                build_definition["buildType"]
                != "https://github.com/Attestations/GitHubActionsWorkflow@v1"
                or external_parameters
                != {
                    "repository": manifest["repository"],
                    "revision": manifest["revision"],
                    "workflow": release_policy["workflowPath"],
                    "context": image_policy["context"],
                    "dockerfile": image_policy["dockerfile"],
                    "platform": "linux/amd64",
                }
                or build_definition["internalParameters"] != {}
                or build_definition["resolvedDependencies"]
                != [
                    {
                        "uri": f"git+https://github.com/{manifest['repository']}",
                        "digest": {"gitCommit": manifest["revision"]},
                    }
                ]
                or run_details
                != {
                    "builder": {
                        "id": "https://github.com/docker/build-push-action"
                    },
                    "metadata": {"invocationId": expected_invocation},
                }
            ):
                fail(f"{values_key} provenance does not describe this build.")
            first_party_references.append(entry["reference"])
        else:
            source_release = entry.get("sourceRelease")
            source_prefix = image_policy["sourceReleasePrefix"]
            if (
                entry["sourceRepository"] != image_policy["sourceRepository"]
                or entry["buildRepository"] != image_policy["buildRepository"]
                or not isinstance(source_release, str)
                or not source_release.startswith(source_prefix)
                or len(source_release) <= len(source_prefix)
            ):
                fail(f"{values_key} lacks an approved upstream source release.")
            source_tag = source_release[len(source_prefix) :]
            source_version = parse_stable_version(
                source_tag,
                f"{values_key}.sourceRelease tag",
            )
            minimum_version = parse_stable_version(
                image_policy["minimumVersion"],
                f"policy.images.{values_key}.minimumVersion",
                allow_v=False,
            )
            if source_version < minimum_version:
                fail(f"{values_key} is below the approved minimum upstream version.")
            release_version = ".".join(str(part) for part in source_version)
            approved_tag = source_tag + image_policy["imageTagSuffix"]
            evidence = require_keys(
                evidence,
                {
                    "scanPolicy",
                    "sbom",
                    "scan",
                    "upstreamReview",
                    "registryTagProof",
                    "runtimeOutput",
                },
                f"{values_key}.evidence",
            )
            if evidence["scanPolicy"] != SCAN_POLICY:
                fail(f"{values_key} has a weaker vulnerability policy.")
            sbom_path = resolve_evidence(
                evidence_dir, evidence["sbom"], f"{values_key}.sbom", used_evidence
            )
            scan_path = resolve_evidence(
                evidence_dir, evidence["scan"], f"{values_key}.scan", used_evidence
            )
            review_path = resolve_evidence(
                evidence_dir,
                evidence["upstreamReview"],
                f"{values_key}.upstreamReview",
                used_evidence,
            )
            registry_tag_proof_path = resolve_evidence(
                evidence_dir,
                evidence["registryTagProof"],
                f"{values_key}.registryTagProof",
                used_evidence,
            )
            runtime_output_path = resolve_evidence(
                evidence_dir,
                evidence["runtimeOutput"],
                f"{values_key}.runtimeOutput",
                used_evidence,
            )
            validate_sbom(sbom_path, f"{values_key}.sbom")
            validate_scan(scan_path, f"{values_key}.scan")
            review = require_keys(
                load_json(review_path),
                {
                    "schemaVersion",
                    "component",
                    "reference",
                    "sourceRepository",
                    "buildRepository",
                    "sourceRelease",
                    "approvedImageTag",
                    "checks",
                },
                f"{values_key}.upstreamReview",
            )
            if review != {
                "schemaVersion": UPSTREAM_REVIEW_SCHEMA,
                "component": entry["component"],
                "reference": entry["reference"],
                "sourceRepository": entry["sourceRepository"],
                "buildRepository": entry["buildRepository"],
                "sourceRelease": entry["sourceRelease"],
                "approvedImageTag": approved_tag,
                "checks": {
                    "officialImageRepository": True,
                    "digestPinned": True,
                    "sourceVersionAtLeast": image_policy["minimumVersion"],
                    "registryTagResolvesToDigest": True,
                    "runtimeCompatibility": image_policy["runtimeContract"],
                    "independentTrivyScan": "HIGH,CRITICAL",
                    "independentCycloneDxSbom": True,
                    "upstreamCryptographicSignature": "not-assumed",
                },
            }:
                fail(f"{values_key} upstream review is incomplete.")
            validate_registry_tag_proof(
                registry_tag_proof_path,
                component=entry["component"],
                reference=entry["reference"],
                source_release=source_release,
                source_tag=source_tag,
                approved_tag=approved_tag,
                repository=image_policy["repository"],
                label=f"{values_key}.registryTagProof",
            )
            validate_upstream_runtime_output(
                runtime_output_path,
                contract=image_policy["runtimeContract"],
                release_version=release_version,
                label=f"{values_key}.runtimeOutput",
            )
    return first_party_references


def run_cosign(cosign: str, arguments: list[str], label: str) -> None:
    result = subprocess.run(
        [cosign, *arguments],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip()
        if len(detail) > 1000:
            detail = detail[-1000:]
        fail(f"Cosign verification failed for {label}: {detail}")


def verify_source_tree(
    source_root: Path,
    *,
    policy_path: Path,
    revision: str,
) -> None:
    if not source_root.is_dir() or source_root.is_symlink():
        fail(f"Source root is missing or symlinked: {source_root}")
    expected_policy = source_root / "deploy/kubernetes/supply-chain-policy.yaml"
    if policy_path != expected_policy:
        fail("The trust policy must come from the source tree being promoted.")

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode:
            detail = result.stderr.strip()
            fail(f"Cannot verify the release source tree: {detail}")
        return result.stdout.strip()

    top_level = Path(git("rev-parse", "--show-toplevel")).resolve()
    if top_level != source_root:
        fail("Source root must be the exact Git worktree root.")
    head = git("rev-parse", "--verify", "HEAD")
    if head != revision:
        fail(f"Source checkout {head} does not match signed revision {revision}.")
    dirty = git("status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        fail("Source checkout has tracked or untracked changes; promotion requires a clean tree.")


def verify_cosign(
    *,
    cosign: str,
    manifest_path: Path,
    bundle_path: Path,
    policy: dict[str, Any],
    revision: str,
    event: str,
    first_party_references: list[str] | None,
    verify_blob: bool = True,
) -> None:
    trust = policy["release"]
    identity_arguments = [
        "--certificate-identity",
        trust["certificateIdentity"],
        "--certificate-oidc-issuer",
        trust["certificateIssuer"],
        "--certificate-github-workflow-repository",
        trust["repository"],
        "--certificate-github-workflow-ref",
        trust["workflowRef"],
        "--certificate-github-workflow-sha",
        revision,
        "--certificate-github-workflow-trigger",
        event,
    ]
    if verify_blob:
        run_cosign(
            cosign,
            [
                "verify-blob",
                "--bundle",
                str(bundle_path),
                *identity_arguments,
                str(manifest_path),
            ],
            "release manifest",
        )
    if first_party_references is None:
        return
    for reference in first_party_references:
        # Cosign v3.0 does not accept a detached --bundle with image `verify` or
        # `verify-attestation`. The hash-bound local bundles are archival copies;
        # cryptographic promotion verification intentionally reads the exact digest's
        # signature and attestations from the registry and transparency log.
        run_cosign(
            cosign,
            ["verify", *identity_arguments, reference],
            f"{reference} signature",
        )
        for attestation_type in ("cyclonedx", "slsaprovenance1"):
            run_cosign(
                cosign,
                [
                    "verify-attestation",
                    "--type",
                    attestation_type,
                    *identity_arguments,
                    reference,
                ],
                f"{reference} {attestation_type} attestation",
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed verification of an ArchiDEAL production release."
    )
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--policy", default=DEFAULT_POLICY, type=Path)
    parser.add_argument("--source-root", default=REPOSITORY_ROOT, type=Path)
    parser.add_argument("--cosign", default="cosign")
    args = parser.parse_args()

    values_path = args.values.resolve()
    manifest_path = args.manifest.resolve()
    bundle_path = args.bundle.resolve()
    evidence_dir = args.evidence_dir.resolve()
    policy_path = args.policy.resolve()
    source_root = args.source_root.resolve()
    for path, label in (
        (values_path, "values"),
        (manifest_path, "release manifest"),
        (bundle_path, "Sigstore bundle"),
        (policy_path, "supply-chain policy"),
    ):
        if not path.is_file() or path.is_symlink():
            fail(f"Missing or symlinked {label}: {path}")
    if not evidence_dir.is_dir() or evidence_dir.is_symlink():
        fail(f"Missing or symlinked evidence directory: {evidence_dir}")
    cosign = shutil.which(args.cosign)
    if not cosign:
        fail(f"Cosign executable not found: {args.cosign}")

    policy = load_policy(policy_path)
    manifest = load_json(manifest_path)
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("revision"), str)
        or not isinstance(manifest.get("workflow"), dict)
        or not isinstance(manifest["workflow"].get("event"), str)
    ):
        fail("Release manifest does not contain revision and workflow event claims.")
    # Authenticate the release record before trusting any of its claims.
    verify_cosign(
        cosign=cosign,
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        policy=policy,
        revision=manifest["revision"],
        event=manifest["workflow"]["event"],
        first_party_references=None,
    )
    verify_source_tree(
        source_root,
        policy_path=policy_path,
        revision=manifest["revision"],
    )
    values = renderer.load_values(values_path, allow_example=False)
    first_party_references = validate_manifest(
        manifest,
        values=values,
        policy=policy,
        policy_path=policy_path,
        evidence_dir=evidence_dir,
    )
    verify_cosign(
        cosign=cosign,
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        policy=policy,
        revision=manifest["revision"],
        event=manifest["workflow"]["event"],
        first_party_references=first_party_references,
        verify_blob=False,
    )
    print(
        "Verified signed release "
        f"{manifest['revision']} with 8 first-party and 2 upstream images."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"release verification error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
