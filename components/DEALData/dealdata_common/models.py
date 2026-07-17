"""Model helpers shared by DEALData services."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import math
from typing import Any
from uuid import UUID, uuid7

from django.db import models
from django.utils.dateparse import parse_datetime


OBSERVED_OBJECT_ID_VERBOSE_NAME = "Observed Object ID"
OBSERVED_OBJECT_ID_HELP_TEXT = "UUID of the observed object managed by the core layer."


def uuid7_value() -> UUID:
    """Return a UUIDv7 value compatible with Django UUIDField."""
    return uuid7()


def parse_event_datetime(value: Any, field_name: str) -> datetime:
    """Parse an ISO datetime from a DEALIoT event."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = parse_datetime(value)
    else:
        parsed = None

    if parsed is None:
        message = f"DEALIoT event field '{field_name}' must be an ISO datetime."
        raise ValueError(message)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_optional_event_datetime(
    value: Any,
    field_name: str,
) -> datetime | None:
    """Parse an optional ISO datetime from a DEALIoT event."""
    if value is None or value == "":
        return None
    return parse_event_datetime(value, field_name)


def payload_dict(value: Any) -> dict[str, Any]:
    """Keep decoded payloads queryable while preserving scalar values."""
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    return {"value": value}


def event_float(
    event: dict[str, Any],
    payload: dict[str, Any],
    *field_names: str,
    required: bool = False,
) -> float | None:
    """Extract a float from top-level DEALIoT fields or decoded payload."""
    for field_name in field_names:
        value = event.get(field_name)
        if value is None or value == "":
            value = payload.get(field_name)
        if value is not None and value != "":
            try:
                parsed = float(value)
            except (TypeError, ValueError) as exc:
                message = f"DEALIoT event field '{field_name}' must be a number."
                raise ValueError(message) from exc
            if not math.isfinite(parsed):
                message = f"DEALIoT event field '{field_name}' must be finite."
                raise ValueError(message)
            return parsed
    if required:
        names = ", ".join(field_names)
        message = f"DEALIoT event must contain one of: {names}."
        raise ValueError(message)
    return None


def event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    """Keep transport metadata from MQTT/Kafka without shaping it too early."""
    metadata_fields = ("qos", "retain", "partition", "offset", "key")
    return {field: event[field] for field in metadata_fields if field in event}


def stable_event_hash(event: dict[str, Any]) -> str:
    """Build a stable idempotency hash for a decoded DEALIoT event."""
    serialized = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def event_identity_payload(event: Any, **extra: Any) -> dict[str, Any]:
    """Return common event fields used to build direct-save hashes."""
    payload = {
        "device_id": event.wildfi_device_id,
        "timestamp": event.acquisition_time,
        "topic": event.dealiot_topic,
        "source": event.source,
        "mqtt_topic": event.mqtt_topic,
        "payload": event.payload,
    }
    payload.update(extra)
    return payload


class WildFiEventBase(models.Model):
    """Common fields for decoded WildFi events."""

    wildfi_device_id = models.CharField(max_length=128, db_index=True)
    event_id = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text="Optional upstream DEALIoT/Kafka event identifier.",
    )
    message_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional Kafka or MQTT key used by DEALIoT.",
    )
    payload_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Stable SHA-256 hash used for idempotent ingestion.",
    )
    observed_object_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name=OBSERVED_OBJECT_ID_VERBOSE_NAME,
        help_text=OBSERVED_OBJECT_ID_HELP_TEXT,
    )
    source = models.CharField(max_length=64, default="wildfi-mqtt")
    mqtt_topic = models.CharField(max_length=255, blank=True)
    acquisition_time = models.DateTimeField(db_index=True)
    ingested_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    message_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
