from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

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
    route_allowed_upstream_hosts: tuple[str, ...] = ()
    route_allowed_upstream_suffixes: tuple[str, ...] = ()
    route_allowed_upstream_ports: tuple[int, ...] = ()
    route_allowed_upstreams: tuple[str, ...] = ()
    route_reserved_path_prefixes: tuple[str, ...] = ()


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


def get_int_csv_env(name: str, default: str = "") -> tuple[int, ...]:
    values = get_csv_env(name, default)
    try:
        parsed = tuple(int(value) for value in values)
    except ValueError as exc:
        raise RuntimeError(f"{name} must contain only integers") from exc
    if any(value < 1 or value > 65535 for value in parsed):
        raise RuntimeError(f"{name} values must be between 1 and 65535")
    return parsed


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
        route_allowed_upstream_hosts=get_csv_env(
            "APISIX_ROUTE_ALLOWED_UPSTREAM_HOSTS",
            "",
        ),
        route_allowed_upstream_suffixes=get_csv_env(
            "APISIX_ROUTE_ALLOWED_UPSTREAM_SUFFIXES",
            "",
        ),
        route_allowed_upstream_ports=get_int_csv_env(
            "APISIX_ROUTE_ALLOWED_UPSTREAM_PORTS",
        ),
        route_allowed_upstreams=get_csv_env(
            "APISIX_ROUTE_ALLOWED_UPSTREAMS",
            "",
        ),
        route_reserved_path_prefixes=get_csv_env(
            "APISIX_ROUTE_RESERVED_PATH_PREFIXES",
            "",
        ),
    )


def cache_config(*, require_tls: bool = False) -> CacheConfig:
    valkey_url = get_env("VALKEY_URL", "redis://valkey:6379/1").strip()
    if require_tls:
        try:
            parsed = urlsplit(valkey_url)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise RuntimeError("VALKEY_URL is not a valid URL.") from exc
        if (
            parsed.scheme.lower() != "rediss"
            or not hostname
            or port != 6380
            or not parsed.password
            or not parsed.path.startswith("/")
            or not parsed.path[1:].isdigit()
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in valkey_url)
        ):
            raise RuntimeError(
                "VALKEY_URL must use authenticated rediss:// on port 6380 with a numeric "
                "database and no query or fragment in production."
            )
    return CacheConfig(valkey_url=valkey_url)


def nats_config() -> NatsConfig:
    return NatsConfig(
        url=get_env("NATS_URL", "nats://nats:4222"),
        stream=get_env("NATS_STREAM", "dealhost"),
        subject_prefix=get_env("NATS_SUBJECT_PREFIX", "dealhost"),
        enabled=get_env("NATS_ENABLED", "false").lower() == "true",
    )


def database_config(
    base_dir: Path,
    *,
    require_postgres: bool = False,
) -> dict[str, object]:
    """Build the development SQLite or production PostgreSQL configuration."""
    engine = get_env("DEALHOST_DATABASE_ENGINE", "sqlite").strip().lower()
    if engine == "sqlite":
        if require_postgres:
            raise RuntimeError(
                "DEALHOST_DATABASE_ENGINE must be postgresql in production."
            )
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(
                get_env("DEALHOST_DB_PATH", str(base_dir / "db.sqlite3")),
            ),
        }

    if engine not in {"postgres", "postgresql"}:
        raise RuntimeError("DEALHOST_DATABASE_ENGINE must be sqlite or postgresql.")

    sslmode = get_env("DEALHOST_DATABASE_SSLMODE", "prefer").strip().lower()
    if require_postgres and sslmode != "verify-full":
        raise RuntimeError(
            "DEALHOST_DATABASE_SSLMODE must be verify-full in production."
        )
    options: dict[str, object] = {"sslmode": sslmode, "connect_timeout": 3}
    sslrootcert = get_env("DEALHOST_DATABASE_SSLROOTCERT", "").strip()
    if sslrootcert:
        options["sslrootcert"] = sslrootcert
    elif require_postgres:
        raise RuntimeError("DEALHOST_DATABASE_SSLROOTCERT is required in production.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_env("DEALHOST_DATABASE_NAME", "dealhost"),
        "USER": get_env("DEALHOST_DATABASE_USER", "dealhost"),
        "PASSWORD": get_secret_env(
            "DEALHOST_DATABASE_PASSWORD",
            "",
            allow_placeholder=not require_postgres,
        ),
        "HOST": get_env("DEALHOST_DATABASE_HOST", "localhost"),
        "PORT": get_env("DEALHOST_DATABASE_PORT", "5432"),
        "CONN_MAX_AGE": int(get_env("DEALHOST_DATABASE_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": options,
    }
