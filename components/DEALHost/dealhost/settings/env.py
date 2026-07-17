from __future__ import annotations

import os
from dataclasses import dataclass

PLACEHOLDER_VALUES = {
    "",
    "replace-me",
    "<apisix_admin_key>",
    "<admin_api_token>",
    "<django_secret_key>",
    "<github_personal_access_token>",
    "<github_webhook_secret>",
    "<service_api_token>",
}


@dataclass(frozen=True)
class GitHubConfig:
    owner: str
    repository: str
    token: str
    webhook_secret: str
    allowed_repositories: tuple[str, ...]


@dataclass(frozen=True)
class ApisixConfig:
    admin_url: str
    admin_key: str
    upstream_host: str
    upstream_port: int


@dataclass(frozen=True)
class CacheConfig:
    valkey_url: str


@dataclass(frozen=True)
class NatsConfig:
    url: str
    stream: str
    subject_prefix: str
    enabled: bool


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip() for item in get_env(name, default).split(",") if item.strip()
    )


def get_required_csv_env(name: str) -> tuple[str, ...]:
    values = get_csv_env(name, "")
    if not values:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return values


def get_secret_csv_env(
    name: str,
    default: str = "",
    *,
    allow_placeholder: bool = True,
) -> tuple[str, ...]:
    values = get_csv_env(name, default)
    if not allow_placeholder and any(_is_placeholder(value) for value in values):
        raise RuntimeError(
            f"Invalid placeholder secret in environment variable: {name}"
        )
    return values


def get_secret_env(
    name: str,
    default: str | None = None,
    *,
    allow_placeholder: bool = True,
) -> str:
    value = get_env(name, default).strip()
    if not allow_placeholder and _is_placeholder(value):
        raise RuntimeError(f"Missing required secret environment variable: {name}")
    return value


def _is_placeholder(value: str) -> bool:
    normalized = value.strip()
    return normalized in PLACEHOLDER_VALUES or (
        normalized.startswith("<") and normalized.endswith(">")
    )


def github_config(*, require_secrets: bool = False) -> GitHubConfig:
    return GitHubConfig(
        owner=get_env("GITHUB_OWNER", "Smartappli"),
        repository=get_env("GITHUB_REPOSITORY", "DEALIoT"),
        token=get_secret_env(
            "GITHUB_TOKEN",
            "replace-me",
            allow_placeholder=not require_secrets,
        ),
        webhook_secret=get_secret_env(
            "GITHUB_WEBHOOK_SECRET",
            "replace-me",
            allow_placeholder=not require_secrets,
        ),
        allowed_repositories=get_csv_env(
            "GITHUB_ALLOWED_REPOSITORIES",
            "Smartappli/DEALIoT,Smartappli/DEALData",
        ),
    )


def apisix_config(*, require_secrets: bool = False) -> ApisixConfig:
    return ApisixConfig(
        admin_url=get_env("APISIX_ADMIN_URL", "http://apisix:9180"),
        admin_key=get_secret_env(
            "APISIX_ADMIN_KEY",
            "replace-me",
            allow_placeholder=not require_secrets,
        ),
        upstream_host=get_env("APISIX_UPSTREAM_HOST", "django-app"),
        upstream_port=int(get_env("APISIX_UPSTREAM_PORT", "8000")),
    )


def cache_config() -> CacheConfig:
    return CacheConfig(
        valkey_url=get_env("VALKEY_URL", "redis://valkey:6379/1"),
    )


def nats_config() -> NatsConfig:
    return NatsConfig(
        url=get_env("NATS_URL", "nats://nats:4222"),
        stream=get_env("NATS_STREAM", "dealhost"),
        subject_prefix=get_env("NATS_SUBJECT_PREFIX", "dealhost"),
        enabled=get_env("NATS_ENABLED", "false").lower() == "true",
    )
