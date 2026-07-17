"""Shared Django settings for DEALData service projects."""

from __future__ import annotations

from importlib import import_module
import math
import os
from pathlib import Path
from typing import Any, MutableMapping

from django.core.management.utils import get_random_secret_key


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default=None) -> list[str]:
    """Read a comma-separated list from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    """Read a bounded integer from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        message = f"{name} must be an integer."
        raise RuntimeError(message) from exc
    if minimum is not None and parsed < minimum:
        message = f"{name} must be greater than or equal to {minimum}."
        raise RuntimeError(message)
    return parsed


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Read a bounded finite float from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        message = f"{name} must be a number."
        raise RuntimeError(message) from exc
    if not math.isfinite(parsed):
        message = f"{name} must be finite."
        raise RuntimeError(message)
    if minimum is not None and parsed < minimum:
        message = f"{name} must be greater than or equal to {minimum}."
        raise RuntimeError(message)
    if maximum is not None and parsed > maximum:
        message = f"{name} must be less than or equal to {maximum}."
        raise RuntimeError(message)
    return parsed


def database_config(base_dir: Path, default_name: str) -> dict[str, object]:
    """Return a SQLite development DB or PostgreSQL production DB."""
    if env_bool("DATABASE_USE_POSTGRES") or os.environ.get("DATABASE_HOST"):
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DATABASE_NAME", default_name),
            "USER": os.environ.get("DATABASE_USER", "dealdata"),
            "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
            "HOST": os.environ.get("DATABASE_HOST", "localhost"),
            "PORT": os.environ.get("DATABASE_PORT", "5432"),
            "CONN_MAX_AGE": env_int(
                "DATABASE_CONN_MAX_AGE",
                default=60,
                minimum=0,
            ),
        }
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": base_dir / "db.sqlite3",
    }


def _secret_key(debug: bool) -> str:
    secret_key = os.environ.get("DJANGO_SECRET_KEY")
    if secret_key:
        return secret_key
    if debug:
        return get_random_secret_key()
    message = "DJANGO_SECRET_KEY is required when DJANGO_DEBUG is false."
    raise RuntimeError(message)


def _allowed_hosts(debug: bool) -> list[str]:
    hosts = env_list(
        "DJANGO_ALLOWED_HOSTS",
        ["localhost", "127.0.0.1", "testserver"] if debug else [],
    )
    if debug or hosts:
        return hosts
    message = "DJANGO_ALLOWED_HOSTS is required when DJANGO_DEBUG is false."
    raise RuntimeError(message)


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": ("django.contrib.auth.password_validation.MinimumLengthValidator"),
    },
    {
        "NAME": ("django.contrib.auth.password_validation.CommonPasswordValidator"),
    },
    {
        "NAME": ("django.contrib.auth.password_validation.NumericPasswordValidator"),
    },
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}


def configure_service_settings(
    namespace: MutableMapping[str, Any],
    *,
    base_dir: Path,
    project_module: str,
    app_config: str,
    database_name: str,
    include_wsgi: bool = True,
    require_ingest_token: bool = False,
) -> None:
    """Populate the standard settings shared by all DEALData services."""
    import_module("dealdata_common.deployment")
    debug = env_bool("DJANGO_DEBUG", default=True)
    namespace.update(
        BASE_DIR=base_dir,
        DEBUG=debug,
        SECRET_KEY=_secret_key(debug),
        ALLOWED_HOSTS=_allowed_hosts(debug),
        CSRF_TRUSTED_ORIGINS=env_list("DJANGO_CSRF_TRUSTED_ORIGINS"),
        DEALDATA_INGEST_TOKEN=os.environ.get("DEALDATA_INGEST_TOKEN", ""),
        DEALDATA_REQUIRE_INGEST_TOKEN=require_ingest_token,
        INSTALLED_APPS=[*DJANGO_APPS, "rest_framework", app_config],
        MIDDLEWARE=MIDDLEWARE,
        ROOT_URLCONF=f"{project_module}.urls",
        TEMPLATES=TEMPLATES,
        ASGI_APPLICATION=f"{project_module}.asgi.application",
        DATABASES={"default": database_config(base_dir, database_name)},
        AUTH_PASSWORD_VALIDATORS=AUTH_PASSWORD_VALIDATORS,
        PASSWORD_HASHERS=PASSWORD_HASHERS,
        LANGUAGE_CODE="en-us",
        TIME_ZONE="UTC",
        USE_I18N=True,
        USE_TZ=True,
        STATIC_URL="static/",
        STATIC_ROOT=base_dir / "staticfiles",
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        SESSION_COOKIE_SECURE=not debug,
        CSRF_COOKIE_SECURE=not debug,
        SECURE_SSL_REDIRECT=env_bool(
            "DJANGO_SECURE_SSL_REDIRECT",
            default=False,
        ),
        SECURE_HSTS_SECONDS=env_int(
            "DJANGO_SECURE_HSTS_SECONDS",
            default=0,
            minimum=0,
        ),
        SECURE_HSTS_INCLUDE_SUBDOMAINS=env_bool(
            "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
        ),
        SECURE_HSTS_PRELOAD=env_bool("DJANGO_SECURE_HSTS_PRELOAD"),
        X_FRAME_OPTIONS="DENY",
        REST_FRAMEWORK=REST_FRAMEWORK,
    )
    if include_wsgi:
        namespace["WSGI_APPLICATION"] = f"{project_module}.wsgi.application"

    sentry_dsn = os.environ.get("SENTRY_DSN", "")
    namespace["SENTRY_DSN"] = sentry_dsn
    if sentry_dsn:
        sentry_sdk = import_module("sentry_sdk")

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=env_float(
                "SENTRY_TRACES_SAMPLE_RATE",
                default=0.0,
                minimum=0.0,
                maximum=1.0,
            ),
            send_default_pii=env_bool("SENTRY_SEND_DEFAULT_PII"),
        )
