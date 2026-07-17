"""Ingestion helpers for decoded DEALIoT sensor events."""

from __future__ import annotations

from rest_framework import status

from dealdata_common.ingestion import persist_idempotent_event

from .models import WildFiDecodedSensorEvent
from .serializers import WildFiSensorIngestSerializer


def find_existing_sensor_event(
    event: WildFiDecodedSensorEvent,
) -> WildFiDecodedSensorEvent | None:
    """Return an already-ingested event matching idempotency keys."""
    if event.event_id:
        existing = WildFiDecodedSensorEvent.objects.filter(
            source=event.source,
            event_id=event.event_id,
        ).first()
        if existing:
            return existing
    if event.payload_hash:
        return WildFiDecodedSensorEvent.objects.filter(
            source=event.source,
            payload_hash=event.payload_hash,
        ).first()
    return None


def serialize_sensor_ingest_event(
    event: WildFiDecodedSensorEvent,
    *,
    duplicate: bool,
) -> dict[str, object]:
    """Return the compact ingestion response for a sensor event."""
    return {
        "id": str(event.wildfi_decoded_sensor_event_id),
        "duplicate": duplicate,
        "device_id": event.wildfi_device_id,
        "event_id": event.event_id,
        "payload_hash": event.payload_hash,
        "topic": event.dealiot_topic,
        "timestamp": event.acquisition_time.isoformat(),
        "sensor_type": event.sensor_type,
    }


def ingest_dealiot_sensor_event(
    payload: dict[str, object],
) -> tuple[dict[str, object], int]:
    """Persist one decoded DEALIoT `raw.sensor` event idempotently."""
    serializer = WildFiSensorIngestSerializer(data=payload)
    if not serializer.is_valid():
        return {"detail": serializer.errors}, status.HTTP_400_BAD_REQUEST

    try:
        event = WildFiDecodedSensorEvent.from_dealiot_event(
            serializer.validated_data,
        )
    except ValueError as exc:
        return {"detail": str(exc)}, status.HTTP_400_BAD_REQUEST
    return persist_idempotent_event(
        event,
        find_existing=find_existing_sensor_event,
        serialize=lambda item, duplicate: serialize_sensor_ingest_event(
            item,
            duplicate=duplicate,
        ),
    )
