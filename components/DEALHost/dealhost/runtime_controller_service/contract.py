from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
import uuid

from .config import ControllerSettings


_COMPONENT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SECRET_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_IMAGE = re.compile(r"^[a-z0-9](?:[a-z0-9._/-]*[a-z0-9])?@sha256:[0-9a-f]{64}$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CPU = re.compile(r"^(?:[1-9][0-9]*|[1-9][0-9]*m)$")
_MEMORY = re.compile(r"^[1-9][0-9]*(?:Ki|Mi|Gi)$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class ContractError(ValueError):
    def __init__(
        self,
        detail: str,
        *,
        code: str = "invalid_runtime_contract",
        status_code: int = 422,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class Component:
    module_id: int
    slug: str
    image: str
    container_port: int
    healthcheck_path: str
    resources: dict[str, dict[str, str]]
    plain_keys: frozenset[str]
    secret_keys: frozenset[str]
    configuration: dict[str, str]
    secret_refs: dict[str, str]
    scaling: dict[str, int | str]


@dataclass(frozen=True)
class DesiredDeployment:
    deployment_id: str
    environment: str
    generation: int
    desired_state: str
    release_digest: str
    manifest: dict[str, Any]
    components: tuple[Component, ...]
    normalized_payload: dict[str, Any]


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def payload_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def validate_request_id(value: str) -> str:
    normalized = value.strip()
    if not _REQUEST_ID.fullmatch(normalized):
        raise ContractError(
            "Idempotency-Key must contain 8-128 safe characters.",
            code="invalid_idempotency_key",
            status_code=400,
        )
    return normalized


def validate_deployment_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ContractError(
            "The deployment identifier must be a canonical UUID.",
            status_code=400,
        ) from exc
    canonical = str(parsed)
    if value != canonical:
        raise ContractError(
            "The deployment identifier must be a canonical UUID.",
            status_code=400,
        )
    return canonical


def parse_desired_deployment(
    value: object,
    settings: ControllerSettings,
    *,
    allow_absent: bool = False,
) -> DesiredDeployment:
    payload = _object(value, "Runtime payload")
    _exact_fields(
        payload,
        {
            "deployment_id",
            "environment",
            "generation",
            "desired_state",
            "release",
            "configuration",
            "secret_refs",
            "scaling",
        },
        "Runtime payload",
    )
    deployment_id = validate_deployment_id(payload.get("deployment_id"))
    environment = payload.get("environment")
    if environment != settings.environment:
        raise ContractError(
            "The requested runtime environment is not managed by this controller.",
            code="environment_not_managed",
            status_code=409,
        )
    generation = _positive_int(payload.get("generation"), "generation")
    desired_state = payload.get("desired_state")
    allowed_desired_states = {"running", "stopped"}
    if allow_absent:
        allowed_desired_states.add("absent")
    if desired_state not in allowed_desired_states:
        raise ContractError(
            "The requested desired state is unsupported by this operation."
        )

    release = _object(payload.get("release"), "Release")
    _exact_fields(release, {"digest", "manifest"}, "Release")
    release_digest = release.get("digest")
    manifest = _object(release.get("manifest"), "Release manifest")
    if not isinstance(release_digest, str) or not _HEX_DIGEST.fullmatch(release_digest):
        raise ContractError("The release digest is invalid.")
    if payload_digest(manifest) != release_digest:
        raise ContractError(
            "The release manifest does not match its digest.",
            code="release_integrity_failed",
        )

    manifest_components = _parse_manifest(manifest, settings)
    configuration = _component_mapping(payload.get("configuration"), "Configuration")
    secret_refs = _component_mapping(payload.get("secret_refs"), "Secret references")
    scaling = _object(payload.get("scaling"), "Scaling")
    expected_slugs = set(manifest_components)
    for label, mapping in (
        ("Configuration", configuration),
        ("Secret references", secret_refs),
        ("Scaling", scaling),
    ):
        unknown = set(mapping) - expected_slugs
        if unknown:
            raise ContractError(
                f"{label} contains unknown components: {', '.join(sorted(unknown))}."
            )
    if set(scaling) != expected_slugs:
        raise ContractError("Scaling must define every release component.")

    components: list[Component] = []
    normalized_configuration: dict[str, dict[str, str]] = {}
    normalized_secret_refs: dict[str, dict[str, str]] = {}
    normalized_scaling: dict[str, dict[str, int | str]] = {}
    for slug, manifest_component in manifest_components.items():
        plain_values = _validate_values(
            configuration.get(slug, {}),
            allowed=manifest_component["plain_keys"],
            slug=slug,
            secret=False,
        )
        secret_values = _validate_values(
            secret_refs.get(slug, {}),
            allowed=manifest_component["secret_keys"],
            slug=slug,
            secret=True,
        )
        scaling_policy = _scaling_policy(scaling[slug], slug, settings.max_replicas)
        normalized_configuration[slug] = plain_values
        normalized_secret_refs[slug] = secret_values
        normalized_scaling[slug] = scaling_policy
        components.append(
            Component(
                module_id=manifest_component["module_id"],
                slug=slug,
                image=manifest_component["image"],
                container_port=manifest_component["container_port"],
                healthcheck_path=manifest_component["healthcheck_path"],
                resources=manifest_component["resources"],
                plain_keys=manifest_component["plain_keys"],
                secret_keys=manifest_component["secret_keys"],
                configuration=plain_values,
                secret_refs=secret_values,
                scaling=scaling_policy,
            )
        )

    normalized_payload = {
        "deployment_id": deployment_id,
        "environment": environment,
        "generation": generation,
        "desired_state": desired_state,
        "release": {"digest": release_digest, "manifest": manifest},
        "configuration": normalized_configuration,
        "secret_refs": normalized_secret_refs,
        "scaling": normalized_scaling,
    }
    return DesiredDeployment(
        deployment_id=deployment_id,
        environment=environment,
        generation=generation,
        desired_state=desired_state,
        release_digest=release_digest,
        manifest=manifest,
        components=tuple(components),
        normalized_payload=normalized_payload,
    )


def _parse_manifest(
    manifest: dict[str, Any],
    settings: ControllerSettings,
) -> dict[str, dict[str, Any]]:
    _exact_fields(
        manifest,
        {"schema_version", "application", "version", "version_source", "modules"},
        "Release manifest",
    )
    if manifest.get("schema_version") != 1:
        raise ContractError("The release manifest schema is unsupported.")
    application = _object(manifest.get("application"), "Release application")
    _exact_fields(application, {"id", "slug"}, "Release application")
    if not isinstance(application.get("id"), int) or isinstance(
        application.get("id"), bool
    ):
        raise ContractError("The release application identifier is invalid.")
    if not isinstance(application.get("slug"), str) or not application["slug"]:
        raise ContractError("The release application slug is invalid.")
    if not isinstance(manifest.get("version"), str) or not manifest["version"]:
        raise ContractError("The release version is invalid.")
    if not isinstance(manifest.get("version_source"), str):
        raise ContractError("The release version source is invalid.")
    modules = manifest.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= 20:
        raise ContractError("A release must contain between 1 and 20 components.")

    parsed: dict[str, dict[str, Any]] = {}
    module_ids: set[int] = set()
    for raw_component in modules:
        component = _object(raw_component, "Release component")
        _exact_fields(
            component,
            {
                "module_id",
                "slug",
                "image",
                "profile_schema_version",
                "profile_digest",
                "spec",
            },
            "Release component",
        )
        module_id = _positive_int(component.get("module_id"), "module_id")
        slug = component.get("slug")
        image = component.get("image")
        profile_digest = component.get("profile_digest")
        if (
            not isinstance(slug, str)
            or not _COMPONENT_SLUG.fullmatch(slug)
            or slug in parsed
            or module_id in module_ids
        ):
            raise ContractError(
                "Release component identities must be unique and canonical."
            )
        if (
            not isinstance(image, str)
            or not _IMAGE.fullmatch(image)
            or not any(
                image.startswith(prefix) for prefix in settings.allowed_image_prefixes
            )
        ):
            raise ContractError(
                f"Image for {slug} is not an allowed immutable digest.",
                code="image_policy_rejected",
            )
        if component.get("profile_schema_version") != 1:
            raise ContractError(f"Runtime profile for {slug} is unsupported.")
        spec = _object(component.get("spec"), f"Runtime profile for {slug}")
        if (
            not isinstance(profile_digest, str)
            or not _HEX_DIGEST.fullmatch(profile_digest)
            or payload_digest(spec) != profile_digest
        ):
            raise ContractError(f"Runtime profile digest for {slug} is invalid.")
        parsed[slug] = _parse_profile(module_id, slug, image, spec)
        module_ids.add(module_id)
    return parsed


def _parse_profile(
    module_id: int,
    slug: str,
    image: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    _exact_fields(
        spec,
        {
            "kind",
            "container_port",
            "healthcheck_path",
            "resources",
            "configuration",
            "network_egress",
        },
        f"Runtime profile for {slug}",
        optional={"configuration", "network_egress"},
    )
    if spec.get("kind") != "deployment":
        raise ContractError(f"Only stateless deployments are supported for {slug}.")
    port = _positive_int(spec.get("container_port"), "container_port")
    if port > 65535:
        raise ContractError(f"Container port for {slug} is invalid.")
    health = spec.get("healthcheck_path")
    if (
        not isinstance(health, str)
        or not health.startswith("/")
        or health.startswith("//")
        or len(health) > 255
        or any(character.isspace() for character in health)
    ):
        raise ContractError(f"Healthcheck path for {slug} is invalid.")
    resources = _resources(spec.get("resources"), slug)
    configuration = _object(
        spec.get("configuration", {}), f"Configuration schema for {slug}"
    )
    _exact_fields(
        configuration,
        {"plain", "secret"},
        f"Configuration schema for {slug}",
        optional={"plain", "secret"},
    )
    plain = _key_set(configuration.get("plain", []), slug)
    secret = _key_set(configuration.get("secret", []), slug)
    if plain & secret:
        raise ContractError(
            f"Configuration keys for {slug} cannot be both plain and secret."
        )
    network_egress = spec.get("network_egress", [])
    if not isinstance(network_egress, list):
        raise ContractError(f"Network egress for {slug} is invalid.")
    if network_egress:
        raise ContractError(
            f"FQDN network egress for {slug} is not enforced by this controller and is rejected.",
            code="network_egress_unsupported",
        )
    return {
        "module_id": module_id,
        "image": image,
        "container_port": port,
        "healthcheck_path": health,
        "resources": resources,
        "plain_keys": plain,
        "secret_keys": secret,
    }


def _resources(value: object, slug: str) -> dict[str, dict[str, str]]:
    resources = _object(value, f"Resources for {slug}")
    _exact_fields(resources, {"requests", "limits"}, f"Resources for {slug}")
    normalized: dict[str, dict[str, str]] = {}
    for group in ("requests", "limits"):
        entries = _object(resources.get(group), f"Resource {group} for {slug}")
        _exact_fields(entries, {"cpu", "memory"}, f"Resource {group} for {slug}")
        cpu = entries.get("cpu")
        memory = entries.get("memory")
        if not isinstance(cpu, str) or not _CPU.fullmatch(cpu):
            raise ContractError(f"CPU {group} for {slug} is invalid.")
        if not isinstance(memory, str) or not _MEMORY.fullmatch(memory):
            raise ContractError(f"Memory {group} for {slug} is invalid.")
        normalized[group] = {"cpu": cpu, "memory": memory}
    if _cpu_millis(normalized["requests"]["cpu"]) > _cpu_millis(
        normalized["limits"]["cpu"]
    ) or _memory_kib(normalized["requests"]["memory"]) > _memory_kib(
        normalized["limits"]["memory"]
    ):
        raise ContractError(f"Resource requests for {slug} cannot exceed limits.")
    return normalized


def _key_set(value: object, slug: str) -> frozenset[str]:
    if (
        not isinstance(value, list)
        or len(value) > 50
        or any(
            not isinstance(item, str) or not _ENV_KEY.fullmatch(item) for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise ContractError(f"Configuration schema keys for {slug} are invalid.")
    return frozenset(value)


def _component_mapping(value: object, label: str) -> dict[str, dict[str, str]]:
    mapping = _object(value, label)
    normalized: dict[str, dict[str, str]] = {}
    for slug, entries in mapping.items():
        if not isinstance(slug, str) or not _COMPONENT_SLUG.fullmatch(slug):
            raise ContractError(f"{label} contains an invalid component slug.")
        raw_entries = _object(entries, f"{label} for {slug}")
        normalized[slug] = dict(raw_entries)
    return normalized


def _validate_values(
    values: dict[str, str],
    *,
    allowed: frozenset[str],
    slug: str,
    secret: bool,
) -> dict[str, str]:
    if len(values) > 50:
        raise ContractError(f"Too many configuration values for {slug}.")
    normalized: dict[str, str] = {}
    total = 0
    for key, value in values.items():
        if (
            not isinstance(key, str)
            or not _ENV_KEY.fullmatch(key)
            or key not in allowed
        ):
            raise ContractError(f"Configuration key {key!s} is not allowed for {slug}.")
        if not isinstance(value, str) or len(value) > 2048 or "\x00" in value:
            raise ContractError(f"Configuration value for {key} is invalid.")
        if secret and not _SECRET_NAME.fullmatch(value):
            raise ContractError(f"Secret reference for {key} is invalid.")
        total += len(key.encode("utf-8")) + len(value.encode("utf-8"))
        if total > 16_384:
            raise ContractError(f"Configuration for {slug} exceeds 16 KiB.")
        normalized[key] = value
    return normalized


def _scaling_policy(
    value: object,
    slug: str,
    maximum_allowed: int,
) -> dict[str, int | str]:
    policy = _object(value, f"Scaling for {slug}")
    mode = policy.get("mode")
    if mode == "fixed":
        _exact_fields(policy, {"mode", "replicas"}, f"Scaling for {slug}")
        replicas = _positive_int(policy.get("replicas"), "replicas")
        if replicas > maximum_allowed:
            raise ContractError(
                f"Fixed scaling for {slug} exceeds the controller replica limit."
            )
        return {"mode": "fixed", "replicas": replicas}
    if mode == "autoscale":
        _exact_fields(
            policy,
            {"mode", "min_replicas", "max_replicas", "target_cpu_utilization"},
            f"Scaling for {slug}",
        )
        minimum = _positive_int(policy.get("min_replicas"), "min_replicas")
        maximum = _positive_int(policy.get("max_replicas"), "max_replicas")
        target = _positive_int(
            policy.get("target_cpu_utilization"), "target_cpu_utilization"
        )
        if minimum > maximum or maximum > maximum_allowed or not 10 <= target <= 90:
            raise ContractError(f"Autoscaling for {slug} violates controller limits.")
        return {
            "mode": "autoscale",
            "min_replicas": minimum,
            "max_replicas": maximum,
            "target_cpu_utilization": target,
        }
    raise ContractError(f"Scaling mode for {slug} is unsupported.")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractError(f"{label} must be a JSON object.")
    return value


def _exact_fields(
    value: dict[str, Any],
    allowed: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    unknown = set(value) - allowed
    missing = allowed - optional - set(value)
    if unknown or missing:
        raise ContractError(
            f"{label} fields are invalid (missing={sorted(missing)}, unknown={sorted(unknown)})."
        )


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ContractError(f"{label} must be a positive integer.")
    return value


def _cpu_millis(value: str) -> int:
    return int(value[:-1]) if value.endswith("m") else int(value) * 1000


def _memory_kib(value: str) -> int:
    number = int(value[:-2])
    suffix = value[-2:]
    return number * {"Ki": 1, "Mi": 1024, "Gi": 1024 * 1024}[suffix]
