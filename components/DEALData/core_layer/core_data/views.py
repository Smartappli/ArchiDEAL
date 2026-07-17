"""Views for the core_data application."""

import logging

from django.db import connections
from django.views.decorators.http import require_safe

from dealdata_common.observability import (
    liveness_response,
    prometheus_metrics_response,
    readiness_response,
)

from .models import Experiment, ObservedObject, Project

LOGGER = logging.getLogger(__name__)


@require_safe
def health_live(request):
    """Return a cheap liveness response."""
    del request
    return liveness_response("core")


@require_safe
def health_ready(request):
    """Return readiness after checking the default database connection."""
    del request
    return readiness_response(
        "core",
        database_connections=connections,
        logger=LOGGER,
    )


@require_safe
def metrics(request):
    """Return minimal Prometheus metrics for the core service."""
    del request
    return prometheus_metrics_response(
        [
            (
                "dealdata_core_projects_total",
                "Stored projects.",
                Project.objects.count(),
            ),
            (
                "dealdata_core_observed_objects_total",
                "Stored observed objects.",
                ObservedObject.objects.count(),
            ),
            (
                "dealdata_core_experiments_total",
                "Stored experiments.",
                Experiment.objects.count(),
            ),
        ],
    )
