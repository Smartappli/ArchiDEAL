"""Views for the core_data application."""

import logging

from django.db import connections
from django.views.decorators.http import require_safe
from rest_framework import generics, mixins
from rest_framework.permissions import IsAdminUser

from dealdata_common.observability import (
    liveness_response,
    prometheus_metrics_response,
    readiness_response,
)

from .models import Experiment
from .serializers import ExperimentSerializer

LOGGER = logging.getLogger(__name__)


class ExperimentListCreateView(generics.ListCreateAPIView):
    """List experiments or create one as a staff user."""

    permission_classes = [IsAdminUser]
    serializer_class = ExperimentSerializer
    queryset = (
        Experiment.objects.select_related("experiment_project")
        .prefetch_related("experiment_observed_objects")
        .order_by("experiment_id")
    )


class ExperimentDetailView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    generics.GenericAPIView,
):
    """Retrieve, partially update, or delete a staff-managed experiment."""

    permission_classes = [IsAdminUser]
    serializer_class = ExperimentSerializer
    lookup_field = "experiment_id"
    queryset = Experiment.objects.select_related(
        "experiment_project",
    ).prefetch_related("experiment_observed_objects")

    def get(self, request, *args, **kwargs):
        """Return one experiment."""
        return self.retrieve(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        """Partially update one experiment."""
        return self.partial_update(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Delete one experiment."""
        return self.destroy(request, *args, **kwargs)


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
                "dealdata_core_service_info",
                "DEALData core service availability marker.",
                1,
            ),
        ],
    )
