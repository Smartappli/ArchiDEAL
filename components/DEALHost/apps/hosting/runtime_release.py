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


def validate_runtime_profile(profile: ModuleRuntimeProfile) -> dict[str, Any]:
    if not profile.enabled or profile.verified_at is None:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} is not enabled and verified."
        )
    if profile.schema_version != 1 or not isinstance(profile.spec, dict):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} uses an unsupported schema."
        )
    expected_digest = sha256_json(profile.spec)
    if profile.spec_digest != expected_digest:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile digest for {profile.module.slug} does not match its spec."
        )
    allowed_fields = {
        "kind",
        "container_port",
        "healthcheck_path",
        "resources",
        "configuration",
        "network_egress",
    }
    if set(profile.spec) - allowed_fields:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} contains unsupported fields."
        )
    if profile.spec.get("kind") != "deployment":
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} is not a stateless deployment."
        )
    container_port = profile.spec.get("container_port")
    if (
        not isinstance(container_port, int)
        or isinstance(container_port, bool)
        or not 1 <= container_port <= 65535
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} has an invalid container port."
        )
    healthcheck_path = profile.spec.get("healthcheck_path")
    if (
        not isinstance(healthcheck_path, str)
        or not healthcheck_path.startswith("/")
        or healthcheck_path.startswith("//")
        or len(healthcheck_path) > 255
        or any(character.isspace() for character in healthcheck_path)
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} has an invalid healthcheck path."
        )
    resources = profile.spec.get("resources")
    if not isinstance(resources, dict) or set(resources) != {"requests", "limits"}:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} must declare requests and limits."
        )
    for group in ("requests", "limits"):
        resource_values = resources[group]
        if not isinstance(resource_values, dict) or set(resource_values) != {
            "cpu",
            "memory",
        }:
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {profile.module.slug} has incomplete resources."
            )
        if any(
            not isinstance(value, str) or not RESOURCE_VALUE_PATTERN.fullmatch(value)
            for value in resource_values.values()
        ):
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {profile.module.slug} has invalid resource values."
            )
    configuration = profile.spec.get("configuration", {})
    if not isinstance(configuration, dict) or set(configuration) - {"plain", "secret"}:
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} has an invalid configuration schema."
        )
    for group in ("plain", "secret"):
        keys = configuration.get(group, [])
        if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {profile.module.slug} has invalid configuration keys."
            )
    network_egress = profile.spec.get("network_egress", [])
    if not isinstance(network_egress, list) or any(
        not isinstance(item, dict)
        or set(item) != {"host", "port"}
        or not isinstance(item["host"], str)
        or not item["host"]
        or any(character.isspace() for character in item["host"])
        or not isinstance(item["port"], int)
        or isinstance(item["port"], bool)
        or not 1 <= item["port"] <= 65535
        for item in network_egress
    ):
        raise RuntimeReleaseNotDeployable(
            f"Runtime profile for {profile.module.slug} has invalid egress rules."
        )
    return profile.spec


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
        _validate_release_still_matches_application(existing, application)
        _validate_environment_policy(existing.manifest, environment)
        return existing

    modules = list(
        application.modules.select_related("runtime_profile").order_by("slug")
    )
    if not modules:
        raise RuntimeReleaseNotDeployable("The application has no deployable modules.")
    manifest_modules: list[dict[str, Any]] = []
    for module in modules:
        if not module.enabled:
            raise RuntimeReleaseNotDeployable(f"Module {module.slug} is disabled.")
        if module.deployment_target != module.DeploymentTarget.KUBERNETES:
            raise RuntimeReleaseNotDeployable(
                f"Module {module.slug} is not declared for Kubernetes."
            )
        image_match = IMAGE_DIGEST_PATTERN.fullmatch(module.image)
        if image_match is None:
            raise RuntimeReleaseNotDeployable(
                f"Module {module.slug} must use an immutable sha256 image digest."
            )
        try:
            profile = module.runtime_profile
        except ModuleRuntimeProfile.DoesNotExist as exc:
            raise RuntimeReleaseNotDeployable(
                f"Module {module.slug} has no reviewed runtime profile."
            ) from exc
        spec = validate_runtime_profile(profile)
        manifest_modules.append(
            {
                "module_id": module.id,
                "slug": module.slug,
                "image": module.image,
                "profile_schema_version": profile.schema_version,
                "profile_digest": profile.spec_digest,
                "spec": spec,
            }
        )
    manifest = {
        "schema_version": 1,
        "application": {
            "id": application.id,
            "slug": application.slug,
        },
        "version": application_version.version,
        "version_source": application_version.source,
        "modules": manifest_modules,
    }
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
                "The immutable runtime release conflicts with the current module catalog."
            )
        return release


def _validate_release_still_matches_application(
    release: RuntimeRelease,
    application: HostedApplication,
) -> None:
    manifest = release.manifest
    if (
        not isinstance(manifest, dict)
        or sha256_json(manifest) != release.manifest_digest
        or manifest.get("schema_version") != 1
    ):
        raise RuntimeReleaseNotDeployable(
            "The immutable runtime release failed its integrity check."
        )

    application_snapshot = manifest.get("application")
    if (
        not isinstance(application_snapshot, dict)
        or application_snapshot.get("id") != application.id
        or application_snapshot.get("slug") != application.slug
        or manifest.get("version") != release.application_version.version
    ):
        raise RuntimeReleaseNotDeployable(
            "The immutable runtime release no longer matches its application version."
        )

    raw_modules = manifest.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise RuntimeReleaseNotDeployable(
            "The immutable runtime release has an invalid module catalog."
        )
    snapshots: dict[int, dict[str, Any]] = {}
    for raw_module in raw_modules:
        if not isinstance(raw_module, dict):
            raise RuntimeReleaseNotDeployable(
                "The immutable runtime release has an invalid module catalog."
            )
        module_id = raw_module.get("module_id")
        if (
            not isinstance(module_id, int)
            or isinstance(module_id, bool)
            or module_id in snapshots
        ):
            raise RuntimeReleaseNotDeployable(
                "The immutable runtime release has an invalid module catalog."
            )
        snapshots[module_id] = raw_module

    modules = list(application.modules.select_related("runtime_profile"))
    if {module.id for module in modules} != set(snapshots):
        raise RuntimeReleaseNotDeployable(
            "The application module set changed after this version was published; "
            "publish a new version before deploying it."
        )
    for module in modules:
        snapshot = snapshots[module.id]
        try:
            profile = module.runtime_profile
        except ModuleRuntimeProfile.DoesNotExist as exc:
            raise RuntimeReleaseNotDeployable(
                f"Runtime profile for {module.slug} changed after publication; "
                "publish a new version before deploying it."
            ) from exc
        spec = validate_runtime_profile(profile)
        if (
            not module.enabled
            or module.deployment_target != module.DeploymentTarget.KUBERNETES
            or snapshot.get("slug") != module.slug
            or snapshot.get("image") != module.image
            or snapshot.get("profile_schema_version") != profile.schema_version
            or snapshot.get("profile_digest") != profile.spec_digest
            or snapshot.get("spec") != spec
        ):
            raise RuntimeReleaseNotDeployable(
                f"Module {module.slug} changed after this version was published; "
                "publish a new version before deploying it."
            )


def _validate_environment_policy(
    manifest: dict[str, Any],
    environment: RuntimeEnvironment,
) -> None:
    if not environment.enabled or environment.orchestrator != "kubernetes":
        raise RuntimeReleaseNotDeployable("The runtime environment is not enabled.")
    policy = environment.policy
    if not isinstance(policy, dict):
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
    for module in manifest.get("modules", []):
        image = module.get("image", "")
        if not any(image.startswith(prefix) for prefix in allowed_registries):
            raise RuntimeReleaseNotDeployable(
                f"Image registry for {module.get('slug', 'module')} is not allowed."
            )
