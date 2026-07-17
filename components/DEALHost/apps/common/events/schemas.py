from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class EventEnvelope:
    event_type: str
    data: dict[str, Any]
    producer: str = "dealhost.api"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(uuid4()),
            "event_type": self.event_type,
            "occurred_at": datetime.now(tz=UTC).isoformat(),
            "producer": self.producer,
            "data": self.data,
            "meta": self.meta,
        }
