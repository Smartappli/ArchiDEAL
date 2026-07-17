"""Views module for the sensor data application."""

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

from .ingestion import ingest_dealiot_sensor_event
from .models import WildFiDecodedSensorEvent
from .serializers import WildFiSensorBatchSerializer

LOGGER = logging.getLogger(__name__)


@require_safe
def health_live(request):
    """Return a cheap liveness response."""
    del request
    return liveness_response("sensor")


@require_safe
def health_ready(request):
    """Return readiness after checking the default database connection."""
    del request
    return readiness_response(
        "sensor",
        database_connections=connections,
        logger=LOGGER,
    )


@require_safe
def metrics(request):
    """Return minimal Prometheus metrics for the sensor service."""
    del request
    total_events = WildFiDecodedSensorEvent.objects.count()
    total_devices = (
        WildFiDecodedSensorEvent.objects.values("wildfi_device_id").distinct().count()
    )
    return prometheus_metrics_response(
        [
            (
                "dealdata_sensor_wildfi_events_total",
                "Stored WildFi sensor events.",
                total_events,
            ),
            (
                "dealdata_sensor_wildfi_devices_total",
                "WildFi sensor devices.",
                total_devices,
            ),
        ],
    )


def _serialize_sensor_event(event: WildFiDecodedSensorEvent) -> dict[str, object]:
    return {
        "id": str(event.wildfi_decoded_sensor_event_id),
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
        "sensor_type": event.sensor_type,
        "payload": event.payload,
        "metadata": event.message_metadata,
    }


class WildFiSensorIngestView(APIView):
    """Receive decoded WildFi sensor events from DEALIoT."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request) -> Response:
        """Persist one decoded DEALIoT `raw.sensor` event idempotently."""
        _ = self.__class__
        token_error = ingestion_token_error(request)
        if token_error:
            return token_error

        if not isinstance(request.data, dict):
            return Response(
                {"detail": "Expected a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body, response_status = ingest_dealiot_sensor_event(request.data)
        return Response(body, status=response_status)


class WildFiSensorListView(APIView):
    """List stored WildFi sensor events."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request) -> Response:
        """Return sensor events filtered by device, type, source, topic and time."""
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

        queryset = WildFiDecodedSensorEvent.objects.order_by(
            "-acquisition_time",
            "-created_at",
        )
        queryset = apply_event_filters(
            queryset,
            request.query_params,
            started_at,
            ended_at,
        )
        sensor_type = request.query_params.get("sensor_type")
        if sensor_type:
            queryset = queryset.filter(sensor_type=sensor_type)

        total = queryset.count()
        rows = queryset[offset : offset + limit]
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": [_serialize_sensor_event(row) for row in rows],
            },
        )


class WildFiSensorBatchIngestView(APIView):
    """Receive a batch of decoded WildFi sensor events from DEALIoT."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request) -> Response:
        """Persist decoded DEALIoT `raw.sensor` events idempotently."""
        _ = self.__class__
        token_error = ingestion_token_error(request)
        if token_error:
            return token_error

        return batch_ingest_response(
            request.data,
            serializer_class=WildFiSensorBatchSerializer,
            ingest_event=ingest_dealiot_sensor_event,
        )
