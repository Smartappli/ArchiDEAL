"""Shared HTTP responses for DEALData observability endpoints."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse


PrometheusMetric = tuple[str, str, int | float]


def liveness_response(service: str) -> JsonResponse:
    """Return the standard cheap liveness response for a service."""
    return JsonResponse({"status": "ok", "service": service})


def readiness_response(
    service: str,
    *,
    database_connections: Any,
    logger: logging.Logger,
) -> JsonResponse:
    """Return readiness after checking the default database connection."""
    try:
        with database_connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.warning("%s database readiness check failed.", service.capitalize())
        return JsonResponse(
            {
                "status": "error",
                "service": service,
                "database": "unavailable",
                "detail": "Database connection check failed.",
            },
            status=503,
        )
    return JsonResponse(
        {"status": "ok", "service": service, "database": "available"},
    )


def prometheus_metrics_response(metrics: Iterable[PrometheusMetric]) -> HttpResponse:
    """Render a collection of gauge values in Prometheus text format."""
    lines: list[str] = []
    for name, description, value in metrics:
        lines.extend(
            [
                f"# HELP {name} {description}",
                f"# TYPE {name} gauge",
                f"{name} {value}",
            ],
        )
    lines.append("")
    return HttpResponse(
        "\n".join(lines),
        content_type="text/plain; version=0.0.4",
    )
