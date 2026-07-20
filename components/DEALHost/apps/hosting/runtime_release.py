from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from django.db import transaction

from .models import (
    ApplicationVersion,
    HostedApplication,
    ModuleRuntimeProfile,
    RuntimeEnvironment,
    RuntimeRelease,
)


IMAGE_DIGEST_PATTERN = re.compile(
    r"^(?P<repository>[a-z0-9][a-z0-9._/-]*[a-z0-9])@sha256:[0-9a-f]{64}$"
)
RUNTIME_COMPONENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
RESOURCE_VALUE_PATTERN = re.compile(r"^[0-9]+(?:m|Ki|Mi|Gi)?$")


class RuntimeReleaseNotDeployable(ValueError):
    def __init__(self, detail: str, *, code: str = "release_not_deployable") -> None:
        super().__init__(detail)
        self.code = code


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def snapshot_application_runtime(application: HostedApplication) -> dict[str, Any]:
    """Capture the runtime catalog exactly once when a version is published."""

    modules: list[dict[str, Any]] = []
    for module in (
        application.modules.select_for_update()
        .select_related("runtime_profile")
        .order_by("slug")
    ):
        try:
            profile = module.runtime_profile
        except ModuleRuntimeProfile.DoesNotExist:
            profile_snapshot = None
        else:
            profile_snapshot = {
                "schema_version": profile.schema_version,
                "spec": json.loads(canonical_json(profile.spec)),
                "spec_digest": profile.spec_digest,
                "enabled": profile.enabled,
                "verified_at": (
                    profile.verified_at.isoformat() if profile.verified_at else None
                ),
            }
        modules.append(
            {
                "module_id": module.id,
                "slug": module.slug,
                "image": module.image,
                "enabled": module.enabled,
                "deployment_target": module.deployment_target,
                "profile": profile_snapshot,
            }
        )
    return {
        "schema_version": 1,
        "application": {"id": application.id, "slug": application.slug},
        "modules": modules,
    }


def validate_runtime_profile(profile: ModuleRuntimeProfile) -> dict[str, Any]:
    """Validate an editable profile before it is captured in a release snapshot."""

    return _validate_profile_snapshot(
        profile.module.slug,
        {
            "schema_version": profile.schema_version,
            "spec": profile.spec,
            "spec_digest": profile.spec_digest,
            "enabled": profile.enabled,
            "verified_at": profile.verified_at.isoformat()
            if profile.verified_at
            else None,
        },
    )


def runtime_release_for(
    application: HostedApplication,
    version: str,
    environment: RuntimeEnvironment,
) -> RuntimeRelease:
    try:
        application_version = application.versions.get(version=version)
    except ApplicationVersion.DoesNotExist as exc:
        raise RuntimeReleaseNotDeployable(
            "Only published application versions can be deployed."
        ) from exc

    existing = RuntimeRelease.objects.filter(
        application_version=application_version
    ).first()
    if existing is not None:
        _validate_release_integrity(existing, application)
        _validate_environment_policy(existing.manifest, environment)
        return existing

    snapshot = _version_runtime_snapshot(application_version, application)
    manifest = _manifest_from_snapshot(application_version, application, snapshot)
    _validate_environment_policy(manifest, environment)
    digest = sha256_json(manifest)
    with transaction.atomic():
        release, created = RuntimeRelease.objects.get_or_create(
            application_version=application_version,
            defaults={"manifest": manifest, "manifest_digest": digest},
        )
        if not created and (
            release.manifest_digest != digest or release.manifest != manifest
        ):
            raise RuntimeReleaseNotDeployable(
                "The immutable runtime release conflicts with its published snapshot."
            )
        _validate_release_integrity(release, application)
        return release


def _version_runtime_snapshot(
    application_version: ApplicationVersion,
    application: HostedApplication,
) -> dict[str, Any]:
    snapshot = application_version.runtime_snapshot
    digest = application_version.runtime_snapshot_digest
    if not snapshot and not digest:
        # Versions created before runtime snapshots existed are materialized once. The
        # row lock makes the first deploy the immutable publication boundary.
        with transaction.atomic():
            locked = ApplicationVersion.objects.select_for_update().get(
                pk=application_version.pk
            )
            if not locked.runtime_snapshot and not locked.runtime_snapshot_digest:
                locked.runtime_snapshot = snapshot_application_runtime(application)
                locked.runtime_snapshot_digest = sha256_json(locked.runtime_snapshot)
                locked.save(
                    update_fields=["runtime_snapshot", "runtime_snapshot_digest"]
                )
            snapshot = locked.runtime_snapshot
            digest = locked.runtime_snapshot_digest
    if (
        not isinstance(snapshot, dict)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or sha256_json(snapshot) != digest
    ):
        raise RuntimeReleaseNotDeployable(
            "The published runtime snapshot failed its integrity check."
        )
    return snapshot


def _manifest_from_snapshot(
    application_version: ApplicationVersion,
    application: HostedApplication,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    application_snapshot = snapshot.get("application")
    raw_modules = snapshot.get("modules")
    if (
        snapshot.get("schema_version") != 1
        or not isinstance(application_snapshot, dict)
        or application_snapshot.get("id") != application.id
        or not isinstance(application_snapshot.get("slug"), str)
        or not isinstance(raw_modules, list)
        or not raw_modules
        or len(raw_modules) > 100
    ):
        raise RuntimeReleaseNotDeployable(
            "The published runtime snapshot has an invalid module catalog."
        )

    manifest_modules: list[dict[str, Any]] = []
    module_ids: set[int] = set()
    module_slugs: set[str] = set()
    for raw_module in raw_modules:
        if not isinstance(raw_module, dict):
            raise RuntimeReleaseNotDeployable(
                "The published runtime snapshot has an invalid module catalog."
            )
        module_id = raw_module.get("module_id")
        module_slug = raw_module.get("slug")
        image = raw_module.get("image")
        if (
            not isinstance(module_id, int)
            or isinstance(module_id, bool)
            or module_id < 1
            or module_id in module_ids
            or not isinstance(module_slug, str)
            or not RUNTIME_COMPONENT_PATTERN.fullmatch(module_slug)
            or module_slug in module_slugs
        ):
            raise RuntimeReleaseNotDeployable(
                "The published runtime snapshot has invalid component identifiers."
            )
        module_ids.add(module_id)
        module_slugs.add(module_slug)
        if raw_module.get("enabled") is not True:
            raise RuntimeReleaseNotDeployable(f"Module {module_slug} is disabled.")
        if raw_module.get("deployment_target") != "kubernetes":
            raise RuntimeReleaseNotDeployable(
                f"Module {module_slug} is not declared for Kubernetes."
            )
        if not isinstance(image, str) or not IMAGE_DIGEST_PATTERN.fullmatch(image):
            raise RuntimeReleaseNotDeployable(
                f"Module {module_slug} must use an immutable sha256 image digest."
            )
        profile_snapshot = raw_module.get("profile")
        if not isinstance(profile_snapshot, dict):
            raise RuntimeReleaseNotDeployable(
                f"Module {module_slug} has no reviewed runtime profile."
            )
        spec = _validate_profile_snapshot(module_slug, profile_snapshot)
        manifest_modules.append(
            {
                "module_id": module_id,
                "slug": module_slug,
                "image": image,
                "profile_schema_version": profile_snapshot["schema_version"],
                "profile_digest": profile_snapshot["spec_digest"],
                "spec": spec,
            }
        )

    return {
        "schema_version": 1,
        "application": application_snapshot,
        "version": application_version.version,
        "version_source": application_version.source,
        "modules": manifest_modules,
    }


def _validate_profile_snapshot(
    module_slug: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if profile.get("enabled") is not True or not isinstance(
        profile.get("verified_at"), str
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} is not enabled and verified."
        )
    spec = profile.get("spec")
    if profile.get("schema_version") != 1 or not isinstance(spec, dict):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} uses an unsupported schema."
        )
    expected_digest = sha256_json(spec)
    if profile.get("spec_digest") != expected_digest:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile digest for {module_slug} does not match its spec."
        )
    allowed_fields = {
        "kind",
        "container_port",
        "healthcheck_path",
        "resources",
        "configuration",
        "network_egress",
    }
    if set(spec) - allowed_fields:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} contains unsupported fields."
        )
    if spec.get("kind") != "deployment":
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} is not a stateless deployment."
        )
    container_port = spec.get("container_port")
    if (
        not isinstance(container_port, int)
        or isinstance(container_port, bool)
        or not 1 <= container_port <= 65535
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} has an invalid container port."
        )
    healthcheck_path = spec.get("healthcheck_path")
    if (
        not isinstance(healthcheck_path, str)
        or not healthcheck_path.startswith("/")
        or healthcheck_path.startswith("//")
        or len(healthcheck_path) > 255
        or any(character.isspace() for character in healthcheck_path)
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} has an invalid healthcheck path."
        )
    resources = spec.get("resources")
    if not isinstance(resources, dict) or set(resources) != {"requests", "limits"}:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} must declare requests and limits."
        )
    for group in ("requests", "limits"):
        resource_values = resources[group]
        if not isinstance(resource_values, dict) or set(resource_values) != {
            "cpu",
            "memory",
        }:
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {module_slug} has incomplete resources."
            )
        if any(
            not isinstance(value, str) or not RESOURCE_VALUE_PATTERN.fullmatch(value)
            for value in resource_values.values()
        ):
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {module_slug} has invalid resource values."
            )
    configuration = spec.get("configuration", {})
    if not isinstance(configuration, dict) or set(configuration) - {"plain", "secret"}:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} has an invalid configuration schema."
        )
    for group in ("plain", "secret"):
        keys = configuration.get(group, [])
        if (
            not isinstance(keys, list)
            or len(keys) > 50
            or len(set(keys)) != len(keys)
            or any(
                not isinstance(key, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key)
                for key in keys
            )
        ):
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {module_slug} has invalid configuration keys."
            )
    if set(configuration.get("plain", [])) & set(configuration.get("secret", [])):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} reuses plain keys as secrets."
        )
    network_egress = spec.get("network_egress", [])
    if not isinstance(network_egress, list) or any(
        not isinstance(item, dict)
        or set(item) != {"host", "port"}
        or not isinstance(item["host"], str)
        or not item["host"]
        or len(item["host"]) > 253
        or any(character.isspace() for character in item["host"])
        or not isinstance(item["port"], int)
        or isinstance(item["port"], bool)
        or not 1 <= item["port"] <= 65535
        for item in network_egress
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {module_slug} has invalid egress rules."
        )
    return json.loads(canonical_json(spec))


def _validate_release_integrity(
    release: RuntimeRelease,
    application: HostedApplication,
) -> None:
    manifest = release.manifest
    if (
        not isinstance(manifest, dict)
        or sha256_json(manifest) != release.manifest_digest
        or manifest.get("schema_version") != 1
        or manifest.get("version") != release.application_version.version
    ):
        raise RuntimeReleaseNotDeployable(
            "The immutable runtime release failed its integrity check."
        )
    application_snapshot = manifest.get("application")
    raw_modules = manifest.get("modules")
    if (
        release.application_version.application_id != application.id
        or not isinstance(application_snapshot, dict)
        or application_snapshot.get("id") != application.id
        or not isinstance(application_snapshot.get("slug"), str)
        or not isinstance(raw_modules, list)
        or not raw_modules
    ):
        raise RuntimeReleaseNotDeployable(
            "The immutable runtime release has an invalid application catalog."
        )


def _validate_environment_policy(
    manifest: dict[str, Any],
    environment: RuntimeEnvironment,
) -> None:
    if not environment.enabled or environment.orchestrator != "kubernetes":
        raise RuntimeReleaseNotDeployable("The runtime environment is not enabled.")
    policy = environment.policy
    capabilities = environment.capabilities
    if not isinstance(policy, dict) or not isinstance(capabilities, dict):
        raise RuntimeReleaseNotDeployable("The runtime environment policy is invalid.")
    allowed_registries = policy.get("allowed_registries", [])
    if not isinstance(allowed_registries, list) or any(
        not isinstance(prefix, str) or not prefix for prefix in allowed_registries
    ):
        raise RuntimeReleaseNotDeployable("The runtime registry policy is invalid.")
    if policy.get("requires_image_digest") is not True:
        raise RuntimeReleaseNotDeployable(
            "The runtime environment must require immutable image digests."
        )
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise RuntimeReleaseNotDeployable(
            "The immutable runtime release has an invalid module catalog."
        )
    for module in modules:
        if not isinstance(module, dict):
            raise RuntimeReleaseNotDeployable(
                "The immutable runtime release has an invalid module catalog."
            )
        image = module.get("image")
        slug = module.get("slug", "module")
        if not isinstance(image, str) or not any(
            image.startswith(prefix) for prefix in allowed_registries
        ):
            raise RuntimeReleaseNotDeployable(
                f"Image registry for {slug} is not allowed."
            )
        spec = module.get("spec")
        if (
            isinstance(spec, dict)
            and spec.get("network_egress")
            and capabilities.get("network_egress") is not True
        ):
            raise RuntimeReleaseNotDeployable(
                f"Network egress requested by {slug} is not supported in this environment."
            )
