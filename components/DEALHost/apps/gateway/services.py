from __future__ import annotations

import hashlib
import hmac
import ipaddress
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
from django.db import transaction


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _manifest_root() -> Path:
    return Path(settings.BASE_DIR) / "manifests"


def _load_module_manifests() -> dict[str, dict[str, Any]]:
    manifests_dir = _manifest_root() / "modules"
    if not manifests_dir.exists():
        return {}

    manifests: dict[str, dict[str, Any]] = {}
    for file_path in sorted(manifests_dir.glob("*.json")):
        with file_path.open(encoding="utf-8") as manifest_file:
            payload = json.load(manifest_file)
        if not isinstance(payload, dict):
            continue
        slug = str(payload.get("slug", "")).strip()
        if slug:
            manifests[slug] = payload
    return manifests


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


class RoutePublicationError(ValueError):
    """Expected operator-facing route publication failure."""

    code = "route_publication_invalid"


class DisabledModuleRouteError(RoutePublicationError):
    code = "module_disabled"


class UnknownModuleRouteError(RoutePublicationError):
    code = "module_unknown"


class RoutePreviewRequiredError(RoutePublicationError):
    code = "route_preview_required"


class InvalidRoutePreviewEtagError(RoutePublicationError):
    code = "route_preview_etag_invalid"


class StaleRoutePreviewError(RoutePublicationError):
    code = "route_preview_stale"


class UnsafeRoutePathError(RoutePublicationError):
    code = "route_path_unsafe"


class RoutePathConflictError(RoutePublicationError):
    code = "route_path_conflict"


class MissingRoutePolicyError(RoutePublicationError):
    code = "route_policy_missing"


class UnsafeUpstreamError(RoutePublicationError):
    code = "route_upstream_unsafe"


class ModuleNotProductionReadyError(RoutePublicationError):
    code = "module_not_production_ready"


_STRONG_ROUTE_ETAG_PATTERN = re.compile(r'^"sha256-[0-9a-f]{64}"$')
_DNS_LABEL_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",
)
_PUBLIC_PATH_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*")
_SYSTEM_RESERVED_PATH_PREFIXES = (
    "/oauth2",
    "/healthz",
    "/readyz",
    "/apisix",
    "/dealhost",
    "/dealiot",
    "/dealdata",
)
_OIDC_INTROSPECTING_UPSTREAM_HOSTS = frozenset(
    {
        "dealhost",
        "dealiot",
        "dealdata-core",
        "dealdata-gps",
        "dealdata-sensor",
    },
)


def _validated_public_path(value: object) -> str:
    public_path = str(value)
    if public_path != public_path.strip() or not public_path.startswith("/"):
        msg = "public_path must be an absolute path without surrounding whitespace"
        raise UnsafeRoutePathError(msg)
    if public_path != "/":
        public_path = public_path.rstrip("/")
    if public_path == "/":
        msg = "public_path cannot replace the root interface route"
        raise UnsafeRoutePathError(msg)
    if "//" in public_path or "\\" in public_path or "%" in public_path:
        msg = "public_path contains an ambiguous path encoding"
        raise UnsafeRoutePathError(msg)

    segments = public_path[1:].split("/")
    if any(
        segment in {".", ".."}
        or _PUBLIC_PATH_SEGMENT_PATTERN.fullmatch(segment) is None
        for segment in segments
    ):
        msg = "public_path contains an unsafe path segment"
        raise UnsafeRoutePathError(msg)
    return public_path


def _paths_overlap(first: str, second: str) -> bool:
    left = first.casefold()
    right = second.casefold()
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _path_is_within(path: str, prefix: str) -> bool:
    normalized_path = path.casefold()
    normalized_prefix = prefix.casefold()
    return normalized_path == normalized_prefix or normalized_path.startswith(
        f"{normalized_prefix}/",
    )


def _validated_dns_hostname(value: object, *, label: str) -> str:
    raw_host = str(value)
    host = raw_host.casefold()
    if raw_host != raw_host.strip() or not host or len(host) > 253:
        raise UnsafeUpstreamError(f"{label} must be a strict DNS hostname")
    if host.endswith(".") or host == "localhost" or host.endswith(".localhost"):
        raise UnsafeUpstreamError(f"{label} cannot target localhost")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeUpstreamError(f"{label} cannot be an IP address")
    if host.replace(".", "").isdigit():
        raise UnsafeUpstreamError(f"{label} cannot be a numeric IP representation")
    if any(_DNS_LABEL_PATTERN.fullmatch(part) is None for part in host.split(".")):
        raise UnsafeUpstreamError(f"{label} must be a strict DNS hostname")
    return host


def _validated_upstream_port(value: object) -> int:
    if isinstance(value, bool):
        raise UnsafeUpstreamError("upstream_port must be an integer")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise UnsafeUpstreamError("upstream_port must be an integer") from exc
    if port < 1 or port > 65535:
        raise UnsafeUpstreamError("upstream_port must be between 1 and 65535")
    return port


def _validated_route_preview_etag(value: str | None) -> str:
    if value is None or not value.strip():
        msg = "A route preview ETag is required"
        raise RoutePreviewRequiredError(msg)

    etag = value.strip()
    if _STRONG_ROUTE_ETAG_PATTERN.fullmatch(etag) is None:
        msg = "If-Match must contain exactly one strong route preview ETag"
        raise InvalidRoutePreviewEtagError(msg)
    return etag


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
        self.module_manifests = _load_module_manifests()

    def _trusted_development_upstreams(self) -> tuple[set[str], set[int]]:
        hosts = {
            _validated_dns_hostname(
                self.config.upstream_host,
                label="APISIX_UPSTREAM_HOST",
            ),
        }
        ports = {_validated_upstream_port(self.config.upstream_port)}
        for route in self.route_defaults.values():
            hosts.add(
                _validated_dns_hostname(
                    route.get("upstream_host", ""),
                    label="manifest upstream_host",
                ),
            )
            ports.add(_validated_upstream_port(route.get("upstream_port")))
        return hosts, ports

    def _upstream_policy(
        self,
    ) -> tuple[set[str], set[str], set[int], set[tuple[str, int]]]:
        configured_hosts = tuple(
            getattr(self.config, "route_allowed_upstream_hosts", ()),
        )
        configured_suffixes = tuple(
            getattr(self.config, "route_allowed_upstream_suffixes", ()),
        )
        configured_ports = tuple(
            getattr(self.config, "route_allowed_upstream_ports", ()),
        )
        configured_upstreams = tuple(
            getattr(self.config, "route_allowed_upstreams", ()),
        )

        if not settings.DEBUG and (
            not (configured_hosts or configured_suffixes)
            or not configured_ports
            or not configured_upstreams
        ):
            msg = (
                "Production route publication requires explicit host/suffix, port "
                "and exact host:port allowlists"
            )
            raise MissingRoutePolicyError(msg)

        if settings.DEBUG and not (configured_hosts or configured_suffixes):
            allowed_hosts, development_ports = self._trusted_development_upstreams()
        else:
            allowed_hosts = {
                _validated_dns_hostname(host, label="allowed upstream host")
                for host in configured_hosts
            }
            development_ports = set()

        allowed_suffixes: set[str] = set()
        for suffix in configured_suffixes:
            normalized_suffix = str(suffix).removeprefix(".")
            allowed_suffixes.add(
                _validated_dns_hostname(
                    normalized_suffix,
                    label="allowed upstream suffix",
                ),
            )

        if settings.DEBUG and not configured_ports:
            if not development_ports:
                _, development_ports = self._trusted_development_upstreams()
            allowed_ports = development_ports
        else:
            allowed_ports = {
                _validated_upstream_port(port) for port in configured_ports
            }

        allowed_upstreams: set[tuple[str, int]] = set()
        for upstream in configured_upstreams:
            raw_upstream = str(upstream)
            host_value, separator, port_value = raw_upstream.rpartition(":")
            if (
                not separator
                or not host_value
                or not port_value
                or raw_upstream != raw_upstream.strip()
            ):
                raise UnsafeUpstreamError(
                    "allowed upstream must use canonical host:port syntax",
                )
            pair = (
                _validated_dns_hostname(
                    host_value,
                    label="allowed upstream host",
                ),
                _validated_upstream_port(port_value),
            )
            if f"{pair[0]}:{pair[1]}" != raw_upstream:
                raise UnsafeUpstreamError(
                    "allowed upstream must use canonical host:port syntax",
                )
            if pair in allowed_upstreams:
                raise UnsafeUpstreamError(
                    "allowed upstreams must not contain duplicates"
                )
            allowed_upstreams.add(pair)

        return allowed_hosts, allowed_suffixes, allowed_ports, allowed_upstreams

    def _validate_upstream(
        self, upstream_host: object, upstream_port: object
    ) -> tuple[str, int]:
        host = _validated_dns_hostname(upstream_host, label="upstream_host")
        port = _validated_upstream_port(upstream_port)
        (
            allowed_hosts,
            allowed_suffixes,
            allowed_ports,
            allowed_upstreams,
        ) = self._upstream_policy()
        host_is_allowed = host in allowed_hosts or any(
            host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes
        )
        if not host_is_allowed:
            raise UnsafeUpstreamError("upstream_host is not in the route allowlist")
        if port not in allowed_ports:
            raise UnsafeUpstreamError("upstream_port is not in the route allowlist")
        if allowed_upstreams and (host, port) not in allowed_upstreams:
            raise UnsafeUpstreamError(
                "upstream host:port pair is not in the exact route allowlist",
            )
        return host, port

    def _reserved_path_prefixes(self) -> tuple[str, ...]:
        configured_prefixes = tuple(
            getattr(self.config, "route_reserved_path_prefixes", ()),
        )
        configured_script_name = str(getattr(settings, "FORCE_SCRIPT_NAME", "") or "")
        prefixes = [*_SYSTEM_RESERVED_PATH_PREFIXES, *configured_prefixes]
        if configured_script_name:
            prefixes.append(configured_script_name)
        return tuple(
            dict.fromkeys(_validated_public_path(prefix) for prefix in prefixes)
        )

    def _validate_route_path(
        self,
        *,
        module_slug: str,
        public_path: object,
        modules: list[Any],
    ) -> str:
        path = _validated_public_path(public_path)

        protected_paths: list[tuple[str, str]] = []
        for slug, route in self.route_defaults.items():
            source = (
                "the module's bootstrap route"
                if slug == module_slug
                else f"bootstrap route for {slug}"
            )
            protected_paths.append(
                (_validated_public_path(route["public_path"]), source),
            )

        for other_module in modules:
            if (
                not other_module.enabled
                or other_module.slug == module_slug
                or not other_module.public_path
            ):
                continue
            protected_paths.append(
                (
                    _validated_public_path(other_module.public_path),
                    f"enabled module {other_module.slug}",
                ),
            )

        seen_paths: set[str] = set()
        for protected_path, source in protected_paths:
            key = protected_path.casefold()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            if _paths_overlap(path, protected_path):
                msg = f"public_path overlaps {source}: {protected_path}"
                raise RoutePathConflictError(msg)

        for prefix in self._reserved_path_prefixes():
            if _path_is_within(path, prefix):
                msg = f"public_path is under reserved prefix: {prefix}"
                raise UnsafeRoutePathError(msg)
        return path

    def _validate_production_readiness(self, module_slug: str) -> None:
        if settings.DEBUG:
            return
        manifest = self.module_manifests.get(module_slug)
        if manifest is None or manifest.get("production_ready") is not True:
            raise ModuleNotProductionReadyError(
                "Dynamic route publication requires a reviewed module manifest "
                f"with production_ready=true: {module_slug}",
            )

    def _skip_without_public_upstream(
        self,
        route_id: str,
    ) -> dict:
        return {
            "route_id": route_id,
            "skipped": True,
            "reason": "module has no public upstream",
            "payload": None,
        }

    @staticmethod
    def _route_plan_etag(plan: dict[str, Any]) -> str:
        # Hash only the immutable publication inputs. JSON canonicalization makes
        # the value deterministic across workers and prevents dictionary order
        # from changing the precondition token.
        canonical_plan = {
            "payload": plan.get("payload"),
            "route_id": plan["route_id"],
            "skipped": bool(plan.get("skipped", False)),
        }
        canonical_bytes = json.dumps(
            canonical_plan,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        return f'"sha256-{digest}"'

    def _build_route_plan(self, module_slug: str) -> dict[str, Any]:
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

        # A deterministic catalogue-wide lock serializes route planning. Locking
        # just the candidate and then its peers can deadlock when two modules are
        # published concurrently in opposite order.
        modules = list(
            Module.objects.select_for_update().order_by("pk"),
        )
        module = next(
            (candidate for candidate in modules if candidate.slug == module_slug),
            None,
        )
        if module is not None:
            if not module.enabled:
                msg = f"Cannot publish a route for disabled module: {module_slug}"
                raise DisabledModuleRouteError(msg)
            if (
                not module.public_path
                or not module.upstream_host
                or module.upstream_port is None
            ):
                return self._skip_without_public_upstream(route_id)
            public_path = module.public_path or public_path
            upstream_host = module.upstream_host or upstream_host
            upstream_port = module.upstream_port or upstream_port
        elif module_slug in self.known_module_slugs and default_route is None:
            return self._skip_without_public_upstream(route_id)
        elif default_route is None:
            msg = f"Unknown module: {module_slug}"
            raise UnknownModuleRouteError(msg)

        public_path = self._validate_route_path(
            module_slug=module_slug,
            public_path=public_path,
            modules=modules,
        )
        self._validate_production_readiness(module_slug)
        upstream_host, upstream_port = self._validate_upstream(
            upstream_host,
            upstream_port,
        )
        proxy_rewrite: dict[str, Any] = {
            "regex_uri": [
                rf"^{re.escape(public_path)}(?:/(.*))?$",
                "/$1",
            ],
            "host": upstream_host,
        }
        plugins: dict[str, Any] = {"proxy-rewrite": proxy_rewrite}
        if not settings.DEBUG:
            # Production traffic reaches APISIX only through oauth2-proxy. Keep
            # dynamically published routes on the same trusted-edge and
            # observability contract as the production bootstrap routes. The
            # development stack has no oauth2-proxy or OTLP metadata, so it must
            # preserve the caller's existing Authorization header instead.
            header_policy: dict[str, Any] = {
                "set": {
                    "X-Forwarded-Proto": "$http_x_forwarded_proto",
                },
                "remove": ["Authorization", "X-Forwarded-Access-Token"],
            }
            if upstream_host in _OIDC_INTROSPECTING_UPSTREAM_HOSTS:
                header_policy["set"]["Authorization"] = (
                    "Bearer $http_x_forwarded_access_token"
                )
                header_policy["remove"] = ["X-Forwarded-Access-Token"]
            proxy_rewrite["headers"] = header_policy
            plugins = {
                "prometheus": {},
                "opentelemetry": {"sampler": {"name": "always_on"}},
                **plugins,
            }
        payload = {
            "uris": [public_path, f"{public_path}/*"],
            "name": route_id,
            "priority": 100,
            "plugins": plugins,
            "upstream": {
                "type": "roundrobin",
                "pass_host": "node",
                "nodes": {
                    f"{upstream_host}:{upstream_port}": 1,
                },
            },
        }
        return {
            "route_id": route_id,
            "skipped": False,
            "payload": payload,
        }

    def publish_route(
        self,
        module_slug: str,
        dry_run: bool = False,
        *,
        expected_etag: str | None = None,
        require_preview: bool = False,
    ) -> dict:
        # Validate the header before resolving any route data. The operator API
        # opts into this condition, while trusted automation must call the
        # explicitly named unpreviewed method below.
        preview_etag = (
            _validated_route_preview_etag(expected_etag)
            if require_preview and not dry_run
            else None
        )
        # Keep the effective catalogue inputs locked through the APISIX PUT.
        # Module lifecycle mutations take the same row lock, so a concurrent
        # disable/retarget cannot leave the published route detached from the
        # row that authorised it.
        with transaction.atomic():
            return self._publish_route_locked(
                module_slug,
                dry_run=dry_run,
                preview_etag=preview_etag,
            )

    def _publish_route_locked(
        self,
        module_slug: str,
        *,
        dry_run: bool,
        preview_etag: str | None,
    ) -> dict:
        plan = self._build_route_plan(module_slug)
        effective_etag = self._route_plan_etag(plan)
        if preview_etag is not None and not hmac.compare_digest(
            preview_etag,
            effective_etag,
        ):
            msg = "The effective APISIX route no longer matches the preview"
            raise StaleRoutePreviewError(msg)

        result = {
            **plan,
            "dry_run": dry_run,
            "etag": effective_etag,
            "response": None,
        }
        if dry_run:
            return result

        if plan.get("skipped", False):
            return result

        route_ref = quote(plan["route_id"], safe="")
        url = f"{self.config.admin_url}/apisix/admin/routes/{route_ref}"
        headers = {"X-API-KEY": self.config.admin_key}
        # Send the exact object whose canonical digest was checked above. Do not
        # rebuild the route between the precondition comparison and this call.
        response = httpx.put(url, headers=headers, json=plan["payload"], timeout=15)
        response.raise_for_status()
        result["response"] = response.json()
        return result

    def publish_route_unconditionally(self, module_slug: str) -> dict:
        """Publish for a trusted internal trigger that has no operator preview."""
        return self.publish_route(
            module_slug,
            dry_run=False,
            require_preview=False,
        )

    def describe(self) -> dict:
        return asdict(self.config)
