from __future__ import annotations

from django.conf import settings

from .nats_client import publish
from .schemas import EventEnvelope


def publish_event(
    *,
    event_type: str,
    data: dict,
    producer: str = "dealhost.api",
    meta: dict | None = None,
) -> None:
    envelope = EventEnvelope(
        event_type=event_type,
        data=data,
        producer=producer,
        meta=meta or {},
    ).to_dict()
    suffix = event_type.replace("_", "-")
    subject = f"{settings.NATS['SUBJECT_PREFIX']}.{suffix}"
    publish(subject=subject, payload=envelope)
