"""Views for the gps_data application."""

import logging

from django.db import connections
from django.views.decorators.http import require_safe
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from dealdata_common.observability import (
    liveness_response,
    prometheus_metrics_response,
    readiness_response,
)
from dealdata_common.views import (
    INVALID_LIST_QUERY_PARAMETERS_DETAIL,
    QueryParameterError,
    apply_event_filters,
    batch_ingest_response,
    ingestion_token_error,
    parse_list_params,
)

from .ingestion import ingest_dealiot_gps_event
from .models import GPSFix
from .serializers import WildFiGPSBatchSerializer

LOGGER = logging.getLogger(__name__)


@require_safe
def health_live(request):
    """Return a cheap liveness response."""
    del request
    return liveness_response("gps")


@require_safe
def health_ready(request):
    """Return readiness after checking the default database connection."""
    del request
    return readiness_response(
        "gps",
        database_connections=connections,
        logger=LOGGER,
    )


@require_safe
def metrics(request):
    """Return minimal Prometheus metrics for the GPS service."""
    del request
    return prometheus_metrics_response(
        [
            (
                "dealdata_gps_service_info",
                "DEALData GPS service availability marker.",
                1,
            ),
        ],
    )


def _serialize_gps_fix(event: GPSFix) -> dict[str, object]:
    return {
        "id": str(event.wildfi_gps_fix_id),
        "device_id": event.wildfi_device_id,
        "observed_object_id": (
            str(event.observed_object_id) if event.observed_object_id else None
        ),
        "event_id": event.event_id,
        "payload_hash": event.payload_hash,
        "topic": event.dealiot_topic,
        "source": event.source,
        "mqtt_topic": event.mqtt_topic,
        "timestamp": event.acquisition_time.isoformat(),
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "altitude": event.altitude,
        "speed": event.speed,
        "heading": event.heading,
        "geojson": event.as_geojson(),
        "payload": event.payload,
        "metadata": event.message_metadata,
    }


class WildFiGPSIngestView(APIView):
    """Receive decoded WildFi GPS events from DEALIoT."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request) -> Response:
        """Persist one decoded DEALIoT `raw.gps` event idempotently."""
        _ = self.__class__
        token_error = ingestion_token_error(request)
        if token_error:
            return token_error

        if not isinstance(request.data, dict):
            return Response(
                {"detail": "Expected a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body, response_status = ingest_dealiot_gps_event(request.data)
        return Response(body, status=response_status)


class WildFiGPSListView(APIView):
    """List stored WildFi GPS fixes."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request) -> Response:
        """Return GPS fixes filtered by device, source, topic and time window."""
        _ = self.__class__
        try:
            limit, offset, started_at, ended_at = parse_list_params(
                request.query_params,
            )
        except QueryParameterError:
            return Response(
                {"detail": INVALID_LIST_QUERY_PARAMETERS_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = GPSFix.objects.order_by("-acquisition_time", "-created_at")
        queryset = apply_event_filters(
            queryset,
            request.query_params,
            started_at,
            ended_at,
        )

        total = queryset.count()
        rows = queryset[offset : offset + limit]
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": [_serialize_gps_fix(row) for row in rows],
            },
        )


class WildFiGPSBatchIngestView(APIView):
    """Receive a batch of decoded WildFi GPS events from DEALIoT."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request) -> Response:
        """Persist decoded DEALIoT `raw.gps` events idempotently."""
        _ = self.__class__
        token_error = ingestion_token_error(request)
        if token_error:
            return token_error

        return batch_ingest_response(
            request.data,
            serializer_class=WildFiGPSBatchSerializer,
            ingest_event=ingest_dealiot_gps_event,
        )
