from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_slug


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _manifest_root() -> Path:
    return Path(settings.BASE_DIR) / "manifests"


def _load_repository_manifests() -> list[dict[str, Any]]:
    manifests_dir = _manifest_root() / "repositories"
    if not manifests_dir.exists():
        return []

    manifests: list[dict[str, Any]] = []
    for file_path in sorted(manifests_dir.glob("*.json")):
        with file_path.open(encoding="utf-8") as manifest_file:
            payload = json.load(manifest_file)
        if isinstance(payload, dict):
            manifests.append(payload)
    return manifests


def _manifest_by_repository(
    manifests: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(manifest.get("repository_full_name", "")).casefold(): manifest
        for manifest in manifests
        if manifest.get("repository_full_name")
    }


def _route_defaults_from_manifests(
    manifests: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    route_defaults: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        for route in manifest.get("route_defaults", []):
            if not isinstance(route, dict):
                continue
            module_slug = str(route.get("module_slug", "")).strip()
            if module_slug:
                route_defaults[module_slug] = route
    return route_defaults


def _known_module_slugs_from_manifests(manifests: list[dict[str, Any]]) -> set[str]:
    slugs: set[str] = set()
    for manifest in manifests:
        for mapping in manifest.get("path_mappings", []):
            if isinstance(mapping, dict) and mapping.get("module_slug"):
                slugs.add(str(mapping["module_slug"]))
        for route in manifest.get("route_defaults", []):
            if isinstance(route, dict) and route.get("module_slug"):
                slugs.add(str(route["module_slug"]))
    return slugs


def _route_id_for_module(module_slug: str) -> str:
    if module_slug.startswith("module-"):
        return module_slug
    return f"module-{module_slug}"


def normalize_module_slug(value: object) -> str:
    module_slug = str(value).strip()
    try:
        validate_slug(module_slug)
    except ValidationError as exc:
        msg = "module_slug must contain only letters, numbers, hyphens or underscores"
        raise ValueError(msg) from exc
    return module_slug


class GitHubService:
    def __init__(self) -> None:
        self.config = settings.GITHUB
        self.repository_manifests = _load_repository_manifests()
        self.repository_manifest_map = _manifest_by_repository(
            self.repository_manifests,
        )

    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.config.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def latest_commit(
        self,
        branch: str = "main",
        repository_full_name: str | None = None,
    ) -> dict:
        repository = (
            repository_full_name or self.expected_repository_full_name()
        ).strip()
        if not self.is_allowed_repository_full_name(repository):
            msg = f"Repository is not allowed: {repository}"
            raise ValueError(msg)
        if "/" not in repository:
            msg = f"Repository must use owner/name format: {repository}"
            raise ValueError(msg)

        owner, repository_name = repository.split("/", maxsplit=1)
        branch_ref = quote(branch, safe="")
        url = (
            f"https://api.github.com/repos/{owner}/"
            f"{repository_name}/commits/{branch_ref}"
        )
        response = httpx.get(url, headers=self.headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        if not signature:
            return False

        digest = hmac.new(
            self.config.webhook_secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
        expected = f"sha256={digest}"
        return hmac.compare_digest(expected, signature)

    def expected_repository_full_name(self) -> str:
        return f"{self.config.owner}/{self.config.repository}"

    def allowed_repository_full_names(self) -> tuple[str, ...]:
        return self.config.allowed_repositories or (
            self.expected_repository_full_name(),
        )

    def is_allowed_repository_full_name(self, repository: str) -> bool:
        repository = repository.strip()
        allowed = self.allowed_repository_full_names()
        return bool(repository) and any(
            repository.casefold() == candidate.casefold() for candidate in allowed
        )

    def repository_manifest(self, repository: str) -> dict[str, Any] | None:
        return self.repository_manifest_map.get(repository.strip().casefold())

    def allowed_events_for_repository(self, repository: str) -> tuple[str, ...]:
        manifest = self.repository_manifest(repository)
        if not manifest:
            return ("push",)
        allowed_events = manifest.get("allowed_events", ["push"])
        if not isinstance(allowed_events, list):
            return ("push",)
        return tuple(str(event) for event in allowed_events if event)

    def is_allowed_event(self, repository: str, event: str) -> bool:
        allowed_events = self.allowed_events_for_repository(repository)
        return any(
            event.casefold() == candidate.casefold() for candidate in allowed_events
        )

    def repository_integrations(self) -> list[dict[str, Any]]:
        integrations: list[dict[str, Any]] = []
        for manifest in self.repository_manifests:
            repository = str(manifest.get("repository_full_name", "")).strip()
            path_mappings = [
                mapping
                for mapping in manifest.get("path_mappings", [])
                if isinstance(mapping, dict)
            ]
            route_defaults = [
                route
                for route in manifest.get("route_defaults", [])
                if isinstance(route, dict)
            ]
            source_dependency = manifest.get("source_dependency", {})
            if not isinstance(source_dependency, dict):
                source_dependency = {}
            module_slugs = _deduplicate(
                [
                    str(mapping.get("module_slug", "")).strip()
                    for mapping in path_mappings
                    if mapping.get("module_slug")
                ],
            )
            integrations.append(
                {
                    "name": manifest.get("name", ""),
                    "slug": manifest.get("slug", ""),
                    "repository_full_name": repository,
                    "allowed": self.is_allowed_repository_full_name(repository),
                    "allowed_events": self.allowed_events_for_repository(repository),
                    "source_dependency": source_dependency,
                    "module_slugs": module_slugs,
                    "path_mapping_count": len(path_mappings),
                    "public_module_slugs": _deduplicate(
                        [
                            str(route.get("module_slug", "")).strip()
                            for route in route_defaults
                            if route.get("module_slug")
                        ],
                    ),
                },
            )
        return integrations

    def repository_full_name(self, payload: dict[str, Any]) -> str:
        repository = payload.get("repository")
        if not isinstance(repository, dict):
            return ""
        full_name = repository.get("full_name")
        return str(full_name) if full_name else ""

    def is_expected_repository(self, payload: dict[str, Any]) -> bool:
        repository = self.repository_full_name(payload)
        return self.is_allowed_repository_full_name(repository)

    def changed_paths(self, payload: dict[str, Any]) -> list[str]:
        paths: list[str] = []
        for commit in payload.get("commits", []):
            if not isinstance(commit, dict):
                continue
            for key in ("added", "modified", "removed"):
                values = commit.get(key, [])
                if isinstance(values, list):
                    paths.extend(str(value) for value in values if value)

        head_commit = payload.get("head_commit")
        if isinstance(head_commit, dict):
            for key in ("added", "modified", "removed"):
                values = head_commit.get(key, [])
                if isinstance(values, list):
                    paths.extend(str(value) for value in values if value)

        return sorted(_deduplicate(paths))

    def module_slug_for_path(self, path: str, repository: str = "") -> str | None:
        normalized = path.replace("\\", "/").lstrip("/")
        repository_manifest = self.repository_manifest(repository)
        if repository_manifest:
            manifests = [repository_manifest]
        elif repository:
            return None
        else:
            manifests = self.repository_manifests

        for manifest in manifests:
            for mapping in manifest.get("path_mappings", []):
                if not isinstance(mapping, dict):
                    continue
                prefix = str(mapping.get("prefix", ""))
                slug = str(mapping.get("module_slug", ""))
                if not prefix or not slug:
                    continue
                normalized_prefix = prefix.strip("/")
                if normalized == normalized_prefix or normalized.startswith(
                    f"{normalized_prefix}/",
                ):
                    return slug
        return None

    def module_slugs_for_paths(
        self,
        paths: list[str],
        repository: str = "",
    ) -> list[str]:
        slugs = [
            slug
            for path in paths
            if (slug := self.module_slug_for_path(path, repository=repository))
        ]
        return _deduplicate(slugs)

    def module_slugs_for_webhook(self, payload: dict[str, Any]) -> list[str]:
        explicit_slug = payload.get("module_slug")
        if isinstance(explicit_slug, str) and explicit_slug.strip():
            return [explicit_slug.strip()]

        explicit_slugs = payload.get("module_slugs")
        if isinstance(explicit_slugs, list):
            return _deduplicate(
                [str(slug).strip() for slug in explicit_slugs if str(slug).strip()],
            )

        repository = self.repository_full_name(payload)
        return self.module_slugs_for_paths(
            self.changed_paths(payload),
            repository=repository,
        )


class ApisixService:
    def __init__(self) -> None:
        self.config = settings.APISIX
        self.repository_manifests = _load_repository_manifests()
        self.route_defaults = _route_defaults_from_manifests(
            self.repository_manifests,
        )
        self.known_module_slugs = _known_module_slugs_from_manifests(
            self.repository_manifests,
        )

    def _skip_without_public_upstream(
        self,
        route_id: str,
        dry_run: bool,
    ) -> dict:
        return {
            "route_id": route_id,
            "skipped": True,
            "dry_run": dry_run,
            "reason": "module has no public upstream",
            "payload": None,
            "response": None,
        }

    def publish_route(self, module_slug: str, dry_run: bool = False) -> dict:
        module_slug = normalize_module_slug(module_slug)
        route_id = _route_id_for_module(module_slug)
        public_path = f"/{module_slug}"
        upstream_host = self.config.upstream_host
        upstream_port = self.config.upstream_port
        default_route = self.route_defaults.get(module_slug)
        if default_route:
            public_path = str(default_route["public_path"])
            upstream_host = str(default_route["upstream_host"])
            upstream_port = int(default_route["upstream_port"])

        from apps.hosting.models import Module

        module = Module.objects.filter(slug=module_slug, enabled=True).first()
        if module is not None:
            if (
                not module.public_path
                or not module.upstream_host
                or module.upstream_port is None
            ):
                return self._skip_without_public_upstream(route_id, dry_run)
            public_path = module.public_path or public_path
            upstream_host = module.upstream_host or upstream_host
            upstream_port = module.upstream_port or upstream_port
        elif module_slug in self.known_module_slugs and default_route is None:
            return self._skip_without_public_upstream(route_id, dry_run)

        public_path = "/" + public_path.strip("/")
        payload = {
            "uris": [public_path, f"{public_path}/*"],
            "name": route_id,
            "plugins": {
                "proxy-rewrite": {
                    "regex_uri": [
                        rf"^{re.escape(public_path)}(?:/(.*))?$",
                        "/$1",
                    ],
                },
            },
            "upstream": {
                "type": "roundrobin",
                "nodes": {
                    f"{upstream_host}:{upstream_port}": 1,
                },
            },
        }
        if dry_run:
            return {
                "route_id": route_id,
                "dry_run": True,
                "payload": payload,
                "response": None,
            }

        route_ref = quote(route_id, safe="")
        url = f"{self.config.admin_url}/apisix/admin/routes/{route_ref}"
        headers = {"X-API-KEY": self.config.admin_key}
        response = httpx.put(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return {
            "route_id": route_id,
            "dry_run": False,
            "payload": payload,
            "response": response.json(),
        }

    def describe(self) -> dict:
        return asdict(self.config)
