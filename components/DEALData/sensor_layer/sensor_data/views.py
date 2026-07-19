"""Views module for the sensor data application."""

import logging

from django.db import IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
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
from .models import DecodedSensorEvent, Sensor
from .serializers import SensorSerializer, WildFiSensorBatchSerializer

LOGGER = logging.getLogger(__name__)


class SensorListCreateView(generics.ListCreateAPIView):
    """List sensor metadata or register a new sensor."""

    queryset = Sensor.objects.order_by("sensor_code")
    serializer_class = SensorSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "post", "head", "options"]


class SensorDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, partially update, or remove sensor metadata."""

    queryset = Sensor.objects.all()
    serializer_class = SensorSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        """Refuse a metadata deletion that would cascade into scientific data."""
        conflict = {
            "detail": (
                "This sensor still has measurements or observed-object links. "
                "Remove or migrate those records before deleting its metadata."
            ),
        }
        try:
            with transaction.atomic():
                queryset = self.filter_queryset(
                    self.get_queryset(),
                ).select_for_update()
                sensor = get_object_or_404(queryset, pk=kwargs["pk"])
                self.check_object_permissions(request, sensor)
                related_managers = (
                    sensor.sensor_observed_object_sensor,
                    sensor.sensor_data_sensor,
                    sensor.sensor_data_observed_object_sensor,
                )
                if any(manager.exists() for manager in related_managers):
                    return Response(conflict, status=status.HTTP_409_CONFLICT)
                self.perform_destroy(sensor)
        except (ProtectedError, IntegrityError):
            return Response(conflict, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
    return prometheus_metrics_response(
        [
            (
                "dealdata_sensor_service_info",
                "DEALData sensor service availability marker.",
                1,
            ),
        ],
    )


def _serialize_sensor_event(
    event: DecodedSensorEvent,
    *,
    summary: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(event.wildfi_decoded_sensor_event_id),
        "device_id": event.wildfi_device_id,
        "observed_object_id": (
            str(event.observed_object_id) if event.observed_object_id else None
        ),
        "timestamp": event.acquisition_time.isoformat(),
        "sensor_type": event.sensor_type,
    }
    if summary:
        return result
    result.update(
        {
            "event_id": event.event_id,
            "payload_hash": event.payload_hash,
            "topic": event.dealiot_topic,
            "source": event.source,
            "mqtt_topic": event.mqtt_topic,
            "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
            "payload": event.payload,
            "metadata": event.message_metadata,
        },
    )
    return result


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

    permission_classes = [IsAdminUser]

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

        queryset = DecodedSensorEvent.objects.order_by(
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
        summary = request.query_params.get("summary", "").casefold() == "true"
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": [
                    _serialize_sensor_event(row, summary=summary) for row in rows
                ],
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
