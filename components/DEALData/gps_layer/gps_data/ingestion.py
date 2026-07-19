"""Ingestion helpers for decoded DEALIoT GPS events."""

from __future__ import annotations

from rest_framework import status

from dealdata_common.ingestion import persist_idempotent_event

from .models import GPSFix
from .serializers import WildFiGPSIngestSerializer


def find_existing_gps_event(event: GPSFix) -> GPSFix | None:
    """Return an already-ingested event matching idempotency keys."""
    if event.event_id:
        existing = GPSFix.objects.filter(
            source=event.source,
            event_id=event.event_id,
        ).first()
        if existing:
            return existing
    if event.payload_hash:
        return GPSFix.objects.filter(
            source=event.source,
            payload_hash=event.payload_hash,
        ).first()
    return None


def serialize_gps_ingest_event(
    event: GPSFix,
    *,
    duplicate: bool,
) -> dict[str, object]:
    """Return the compact ingestion response for a GPS event."""
    return {
        "id": str(event.wildfi_gps_fix_id),
        "duplicate": duplicate,
        "device_id": event.wildfi_device_id,
        "event_id": event.event_id,
        "payload_hash": event.payload_hash,
        "topic": event.dealiot_topic,
        "timestamp": event.acquisition_time.isoformat(),
    }


def ingest_dealiot_gps_event(
    payload: dict[str, object],
) -> tuple[dict[str, object], int]:
    """Persist one decoded DEALIoT `raw.gps` event idempotently."""
    serializer = WildFiGPSIngestSerializer(data=payload)
    if not serializer.is_valid():
        return {"detail": serializer.errors}, status.HTTP_400_BAD_REQUEST

    try:
        event = GPSFix.from_dealiot_event(serializer.validated_data)
    except ValueError as exc:
        return {"detail": str(exc)}, status.HTTP_400_BAD_REQUEST
    return persist_idempotent_event(
        event,
        find_existing=find_existing_gps_event,
        serialize=lambda item, duplicate: serialize_gps_ingest_event(
            item,
            duplicate=duplicate,
        ),
    )
