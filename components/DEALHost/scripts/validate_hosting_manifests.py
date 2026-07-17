from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS_DIR = ROOT / "manifests"
APISIX_ROUTES_FILE = ROOT / "infra" / "apisix" / "routes.json"
RENOVATE_FILE = ROOT / "renovate.json"
UNPINNED_IMAGE_TAGS = {"latest", "local-placeholder"}
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SOURCE_DEPENDENCY_VERSIONING = {"github-tags", "git-sha"}


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return {}

    if not isinstance(payload, dict):
        errors.append(f"{path}: JSON root must be an object")
        return {}
    return payload


def _json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def _required_string(
    payload: dict[str, Any],
    path: Path,
    field: str,
    errors: list[str],
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: missing or invalid string field '{field}'")
        return ""
    return value.strip()


def _required_int(
    payload: dict[str, Any],
    path: Path,
    field: str,
    errors: list[str],
) -> int | None:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{path}: missing or invalid integer field '{field}'")
        return None
    return value


def _validate_module_public_route(
    payload: dict[str, Any],
    path: Path,
    errors: list[str],
) -> bool:
    fields = ("public_path", "upstream_host", "upstream_port")
    present = [field for field in fields if payload.get(field) not in (None, "")]
    if not present:
        return False
    if len(present) != len(fields):
        errors.append(
            f"{path}: public modules must define public_path, "
            "upstream_host and upstream_port together",
        )
        return False

    _required_string(payload, path, "public_path", errors)
    _required_string(payload, path, "upstream_host", errors)
    _required_int(payload, path, "upstream_port", errors)
    return True


def _module_repository_full_name(payload: dict[str, Any]) -> str:
    owner = payload.get("repository_owner")
    name = payload.get("repository_name")
    if isinstance(owner, str) and isinstance(name, str) and owner and name:
        return f"{owner}/{name}"
    return ""


def _is_false(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    return str(value).strip().casefold() in {"0", "false", "no", "off"}


def _image_tag(image: str) -> str:
    if "@" in image:
        return "digest"
    if ":" not in image.rsplit("/", maxsplit=1)[-1]:
        return "latest"
    return image.rsplit(":", maxsplit=1)[-1]


def _has_tagged_repository_image(payload: dict[str, Any]) -> bool:
    image = payload.get("image")
    if not isinstance(image, str):
        return False

    image_without_digest = image.split("@", maxsplit=1)[0]
    repository, separator, tag = image_without_digest.rpartition(":")
    if not separator or not tag:
        return False
    return "/" in repository


def _is_source_path_covered(
    source_path: str,
    module_slug: str,
    mappings: list[dict[str, Any]],
) -> bool:
    normalized = source_path.strip().replace("\\", "/").strip("/")
    if not normalized or normalized == ".":
        return any(
            str(mapping.get("module_slug", "")).strip() == module_slug
            for mapping in mappings
        )

    normalized_with_slash = f"{normalized}/"
    for mapping in mappings:
        if str(mapping.get("module_slug", "")).strip() != module_slug:
            continue
        prefix = str(mapping.get("prefix", "")).replace("\\", "/").lstrip("/")
        if prefix.rstrip("/") == normalized or prefix.startswith(normalized_with_slash):
            return True
        if normalized_with_slash.startswith(prefix):
            return True
    return False


def _route_id_for_module(module_slug: str) -> str:
    if module_slug.startswith("module-"):
        return module_slug
    return f"module-{module_slug}"


def _validate_modules(
    errors: list[str],
    warnings: list[str],
) -> tuple[
    set[str],
    dict[str, dict[str, Any]],
    dict[str, str],
    dict[str, str],
]:
    module_slugs: set[str] = set()
    public_modules: dict[str, dict[str, Any]] = {}
    module_repositories: dict[str, str] = {}
    module_source_paths: dict[str, str] = {}
    strict_images = os.getenv("HOSTING_MANIFEST_STRICT_IMAGES", "").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }

    for path in _json_files(MANIFESTS_DIR / "modules"):
        payload = _load_json(path, errors)
        name = _required_string(payload, path, "name", errors)
        slug = _required_string(payload, path, "slug", errors)
        image = _required_string(payload, path, "image", errors)
        if not name or not slug:
            continue
        if slug in module_slugs:
            errors.append(f"{path}: duplicate module slug '{slug}'")
            continue

        module_slugs.add(slug)
        repository = _module_repository_full_name(payload)
        if repository:
            module_repositories[slug] = repository
        source_path = str(payload.get("source_path", "")).strip()
        if repository and source_path:
            module_source_paths[slug] = source_path
        if image:
            tag = _image_tag(image)
            if tag in UNPINNED_IMAGE_TAGS:
                production_ready = not _is_false(payload.get("production_ready", True))
                message = (
                    f"{path}: image '{image}' uses unpinned tag '{tag}'. "
                    "Set production_ready=false for local placeholders or pin a "
                    "release/digest before production."
                )
                if strict_images and production_ready:
                    errors.append(message)
                else:
                    warnings.append(message)
        if _validate_module_public_route(payload, path, errors):
            public_modules[slug] = payload

    if not module_slugs:
        errors.append("manifests/modules: no module manifest found")
    return module_slugs, public_modules, module_repositories, module_source_paths


def _validate_module_refs(
    payload: dict[str, Any],
    path: Path,
    module_slugs: set[str],
    errors: list[str],
) -> None:
    refs = payload.get("module_slugs", [])
    if refs is None:
        return
    if not isinstance(refs, list):
        errors.append(f"{path}: module_slugs must be a list")
        return

    for ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"{path}: module_slugs entries must be non-empty strings")
        elif ref not in module_slugs:
            errors.append(f"{path}: unknown module slug reference '{ref}'")


def _validate_tools_and_applications(
    module_slugs: set[str],
    errors: list[str],
) -> None:
    for category in ("tools", "applications"):
        for path in _json_files(MANIFESTS_DIR / category):
            payload = _load_json(path, errors)
            _required_string(payload, path, "name", errors)
            _required_string(payload, path, "slug", errors)
            _validate_module_refs(payload, path, module_slugs, errors)


def _validate_source_dependency(
    payload: dict[str, Any],
    path: Path,
    repository: str,
    errors: list[str],
) -> None:
    dependency = payload.get("source_dependency")
    if not isinstance(dependency, dict):
        errors.append(f"{path}: missing or invalid object field 'source_dependency'")
        return

    dependency_type = _required_string(dependency, path, "type", errors)
    if dependency_type and dependency_type != "github-repository":
        errors.append(
            f"{path}: source_dependency.type must be 'github-repository'",
        )

    dependency_repository = _required_string(
        dependency,
        path,
        "repository_full_name",
        errors,
    )
    if (
        dependency_repository
        and repository
        and dependency_repository.casefold() != repository.casefold()
    ):
        errors.append(
            f"{path}: source_dependency.repository_full_name must match "
            "repository_full_name",
        )

    versioning = _required_string(dependency, path, "versioning", errors)
    if versioning and versioning not in SOURCE_DEPENDENCY_VERSIONING:
        allowed = ", ".join(sorted(SOURCE_DEPENDENCY_VERSIONING))
        errors.append(
            f"{path}: source_dependency.versioning must be one of: {allowed}",
        )

    version = _required_string(dependency, path, "version", errors)
    ref = _required_string(dependency, path, "ref", errors)
    commit_sha = _required_string(dependency, path, "commit_sha", errors)
    if commit_sha and not GIT_SHA_PATTERN.fullmatch(commit_sha):
        errors.append(
            f"{path}: source_dependency.commit_sha must be a 40-character "
            "lowercase Git SHA",
        )
    if versioning == "github-tags" and ref and not ref.startswith("refs/tags/"):
        errors.append(
            f"{path}: source_dependency.ref must point to refs/tags/ "
            "when versioning is github-tags",
        )
    if versioning == "github-tags" and version and ref != f"refs/tags/{version}":
        errors.append(
            f"{path}: source_dependency.ref must match "
            "refs/tags/{source_dependency.version}",
        )
    if versioning == "git-sha" and ref and not ref.startswith("refs/heads/"):
        errors.append(
            f"{path}: source_dependency.ref must point to refs/heads/ "
            "when versioning is git-sha",
        )
    if versioning == "git-sha" and version and commit_sha:
        expected_version = f"sha-{commit_sha[:12]}"
        if version != expected_version:
            errors.append(
                f"{path}: source_dependency.version must be '{expected_version}' "
                "for git-sha dependencies",
            )


def _validate_repository_manifests(
    module_slugs: set[str],
    public_modules: dict[str, dict[str, Any]],
    module_repositories: dict[str, str],
    module_source_paths: dict[str, str],
    errors: list[str],
) -> list[dict[str, Any]]:
    repository_manifests: list[dict[str, Any]] = []
    repositories_seen: set[str] = set()

    for path in _json_files(MANIFESTS_DIR / "repositories"):
        payload = _load_json(path, errors)
        repository = _required_string(payload, path, "repository_full_name", errors)
        if repository and repository in repositories_seen:
            errors.append(f"{path}: duplicate repository '{repository}'")
        repositories_seen.add(repository)
        _validate_source_dependency(payload, path, repository, errors)

        allowed_events = payload.get("allowed_events", [])
        if not isinstance(allowed_events, list) or not allowed_events:
            errors.append(f"{path}: allowed_events must be a non-empty list")
        elif not all(isinstance(event, str) and event for event in allowed_events):
            errors.append(f"{path}: allowed_events entries must be non-empty strings")

        mappings = payload.get("path_mappings", [])
        if not isinstance(mappings, list) or not mappings:
            errors.append(f"{path}: path_mappings must be a non-empty list")
        else:
            for index, mapping in enumerate(mappings):
                if not isinstance(mapping, dict):
                    errors.append(f"{path}: path_mappings[{index}] must be an object")
                    continue
                prefix = _required_string(mapping, path, "prefix", errors)
                module_slug = _required_string(mapping, path, "module_slug", errors)
                if prefix and module_slug and module_slug not in module_slugs:
                    errors.append(
                        f"{path}: path mapping '{prefix}' references "
                        f"unknown module '{module_slug}'",
                    )

        valid_mappings = [mapping for mapping in mappings if isinstance(mapping, dict)]
        for module_slug, source_path in sorted(module_source_paths.items()):
            if module_repositories.get(module_slug) != repository:
                continue
            if not _is_source_path_covered(source_path, module_slug, valid_mappings):
                errors.append(
                    f"{path}: module '{module_slug}' source_path '{source_path}' "
                    "is not covered by repository path_mappings",
                )

        route_default_slugs: set[str] = set()
        route_defaults = payload.get("route_defaults", [])
        if not isinstance(route_defaults, list):
            errors.append(f"{path}: route_defaults must be a list")
        else:
            for index, route in enumerate(route_defaults):
                if not isinstance(route, dict):
                    errors.append(f"{path}: route_defaults[{index}] must be an object")
                    continue
                module_slug = _required_string(route, path, "module_slug", errors)
                _required_string(route, path, "public_path", errors)
                _required_string(route, path, "upstream_host", errors)
                _required_int(route, path, "upstream_port", errors)
                if module_slug:
                    route_default_slugs.add(module_slug)
                    if module_slug not in module_slugs:
                        errors.append(
                            f"{path}: route default references unknown module "
                            f"'{module_slug}'",
                        )

        for module_slug in sorted(public_modules):
            if module_repositories.get(module_slug) != repository:
                continue
            if module_slug not in route_default_slugs:
                errors.append(
                    f"{path}: public module '{module_slug}' is missing from "
                    "route_defaults",
                )

        if repository:
            repository_manifests.append(payload)

    if not repository_manifests:
        errors.append("manifests/repositories: no repository manifest found")
    return repository_manifests


def _validate_apisix_routes(
    public_modules: dict[str, dict[str, Any]],
    repository_manifests: list[dict[str, Any]],
    errors: list[str],
) -> None:
    payload = _load_json(APISIX_ROUTES_FILE, errors)
    routes = payload.get("routes", [])
    if not isinstance(routes, list) or not routes:
        errors.append(f"{APISIX_ROUTES_FILE}: routes must be a non-empty list")
        return

    route_ids: set[str] = set()
    routes_by_id: dict[str, dict[str, Any]] = {}
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"{APISIX_ROUTES_FILE}: routes[{index}] must be an object")
            continue
        route_id = _required_string(route, APISIX_ROUTES_FILE, "id", errors)
        _required_string(route, APISIX_ROUTES_FILE, "uri", errors)
        _required_string(route, APISIX_ROUTES_FILE, "name", errors)
        if route_id in route_ids:
            errors.append(f"{APISIX_ROUTES_FILE}: duplicate route id '{route_id}'")
        route_ids.add(route_id)
        routes_by_id[route_id] = route

    for module_slug, module in sorted(public_modules.items()):
        route_id = _route_id_for_module(module_slug)
        route = routes_by_id.get(route_id)
        if route is None:
            errors.append(
                f"{APISIX_ROUTES_FILE}: missing public route '{route_id}'",
            )
            continue
        expected_uri = "/" + str(module["public_path"]).strip("/") + "/*"
        if route.get("uri") != expected_uri:
            errors.append(
                f"{APISIX_ROUTES_FILE}: route '{route_id}' uri should be "
                f"'{expected_uri}'",
            )

    for manifest in repository_manifests:
        for route_default in manifest.get("route_defaults", []):
            if not isinstance(route_default, dict):
                continue
            module_slug = route_default.get("module_slug")
            if not isinstance(module_slug, str) or not module_slug:
                continue
            route_id = _route_id_for_module(module_slug)
            route = routes_by_id.get(route_id)
            if route is None:
                errors.append(
                    f"{APISIX_ROUTES_FILE}: missing default route '{route_id}'",
                )
                continue
            expected_node = (
                f"{route_default.get('upstream_host')}:"
                f"{route_default.get('upstream_port')}"
            )
            nodes = route.get("upstream", {}).get("nodes", {})
            if expected_node not in nodes:
                errors.append(
                    f"{APISIX_ROUTES_FILE}: route '{route_id}' should target "
                    f"'{expected_node}'",
                )


def _validate_renovate(errors: list[str]) -> None:
    payload = _load_json(RENOVATE_FILE, errors)
    enabled_managers = payload.get("enabledManagers", [])
    if "custom.regex" not in enabled_managers:
        errors.append(f"{RENOVATE_FILE}: custom.regex manager must stay enabled")
    if payload.get("dependencyDashboard") is not True:
        errors.append(f"{RENOVATE_FILE}: dependencyDashboard must be enabled")

    managers = payload.get("customManagers", [])
    if not isinstance(managers, list) or not managers:
        errors.append(
            f"{RENOVATE_FILE}: customManagers must define manifest image scan"
        )
        return

    has_module_image_manager = any(
        isinstance(manager, dict)
        and any(
            "manifests/modules" in str(pattern)
            for pattern in manager.get("managerFilePatterns", [])
        )
        and any(
            "currentValue" in str(match) for match in manager.get("matchStrings", [])
        )
        for manager in managers
    )
    if not has_module_image_manager:
        errors.append(
            f"{RENOVATE_FILE}: missing custom manager for manifests/modules images",
        )

    package_rules = payload.get("packageRules", [])
    if not isinstance(package_rules, list):
        errors.append(f"{RENOVATE_FILE}: packageRules must be a list")
        package_rules = []
    has_smartappli_rule = any(
        isinstance(rule, dict)
        and "smartappli-ghcr" in rule.get("labels", [])
        and any(
            str(package).startswith("ghcr.io/smartappli/")
            for package in rule.get("matchPackageNames", [])
        )
        for rule in package_rules
    )
    if not has_smartappli_rule:
        errors.append(f"{RENOVATE_FILE}: missing Smartappli GHCR package rule")

    has_public_image_rule = any(
        isinstance(rule, dict) and "public-image" in rule.get("labels", [])
        for rule in package_rules
    )
    if not has_public_image_rule:
        errors.append(f"{RENOVATE_FILE}: missing public image package rule")

    has_matchable_module_image = any(
        _has_tagged_repository_image(_load_json(path, errors))
        for path in _json_files(MANIFESTS_DIR / "modules")
    )
    if not has_matchable_module_image:
        errors.append(
            f"{RENOVATE_FILE}: custom module image manager does not match any module",
        )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    (
        module_slugs,
        public_modules,
        module_repositories,
        module_source_paths,
    ) = _validate_modules(errors, warnings)
    _validate_tools_and_applications(module_slugs, errors)
    repository_manifests = _validate_repository_manifests(
        module_slugs,
        public_modules,
        module_repositories,
        module_source_paths,
        errors,
    )
    _validate_apisix_routes(public_modules, repository_manifests, errors)
    _validate_renovate(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(
        "Hosting manifests validation passed "
        f"({len(module_slugs)} modules, {len(repository_manifests)} repositories, "
        f"{len(public_modules)} public modules)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
