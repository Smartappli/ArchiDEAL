"""Django deployment checks shared by all DEALData services."""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def check_deployment_security(app_configs, **kwargs):
    """Require the security settings that protect public deployments."""
    del app_configs, kwargs
    if settings.DEBUG:
        return []

    errors = []
    if not settings.SECURE_SSL_REDIRECT:
        errors.append(
            Error(
                "DJANGO_SECURE_SSL_REDIRECT must be enabled in production.",
                hint="Set DJANGO_SECURE_SSL_REDIRECT=true.",
                id="dealdata.E001",
            ),
        )
    if settings.SECURE_HSTS_SECONDS <= 0:
        errors.append(
            Error(
                "DJANGO_SECURE_HSTS_SECONDS must be positive in production.",
                hint="Set DJANGO_SECURE_HSTS_SECONDS=31536000.",
                id="dealdata.E002",
            ),
        )
    if not settings.SECURE_HSTS_INCLUDE_SUBDOMAINS:
        errors.append(
            Error(
                "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS must be enabled in production.",
                hint="Set DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true.",
                id="dealdata.E003",
            ),
        )
    if (
        getattr(settings, "DEALDATA_REQUIRE_INGEST_TOKEN", False)
        and not settings.DEALDATA_INGEST_TOKEN
    ):
        errors.append(
            Error(
                "DEALDATA_INGEST_TOKEN is required for production ingestion services.",
                hint="Set a non-empty DEALDATA_INGEST_TOKEN from the secret manager.",
                id="dealdata.E004",
            ),
        )
    database = settings.DATABASES["default"]
    if database.get("ENGINE") != "django.db.backends.postgresql":
        errors.append(
            Error(
                "PostgreSQL is required in production.",
                hint="Set DATABASE_USE_POSTGRES=true and DATABASE_HOST.",
                id="dealdata.E005",
            ),
        )
    if not database.get("PASSWORD"):
        errors.append(
            Error(
                "A PostgreSQL password is required in production.",
                hint="Load DATABASE_PASSWORD from the secret manager.",
                id="dealdata.E006",
            ),
        )
    database_options = database.get("OPTIONS") or {}
    if database_options.get("sslmode") != "verify-full":
        errors.append(
            Error(
                "PostgreSQL certificate and hostname verification are required.",
                hint="Set DATABASE_SSLMODE=verify-full.",
                id="dealdata.E007",
            ),
        )
    if not database_options.get("sslrootcert"):
        errors.append(
            Error(
                "The PostgreSQL CA certificate is required in production.",
                hint="Set DATABASE_SSLROOTCERT to the mounted CA path.",
                id="dealdata.E008",
            ),
        )
    return errors
