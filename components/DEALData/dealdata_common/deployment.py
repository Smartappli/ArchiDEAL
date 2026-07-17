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
    return errors
