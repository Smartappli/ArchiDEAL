"""Shared persistence workflow for idempotent DEALIoT event ingestion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import status


class PersistableEvent(Protocol):
    """Minimal interface required by the idempotent persistence workflow."""

    def full_clean(self) -> None:
        """Validate the event before it is stored."""

    def save(self) -> None:
        """Persist the event."""


Event = TypeVar("Event", bound=PersistableEvent)


def persist_idempotent_event(
    event: Event,
    *,
    find_existing: Callable[[Event], Event | None],
    serialize: Callable[[Event, bool], dict[str, object]],
) -> tuple[dict[str, object], int]:
    """Store an event once, returning the original event on retries.

    The lookup before saving avoids unnecessary integrity errors. The lookup in
    the ``IntegrityError`` handler closes the race between concurrent workers
    attempting to persist the same event.
    """
    existing = find_existing(event)
    if existing:
        return serialize(existing, True), status.HTTP_200_OK

    try:
        with transaction.atomic():
            event.full_clean()
            event.save()
    except DjangoValidationError as exc:
        return {"detail": exc.message_dict}, status.HTTP_400_BAD_REQUEST
    except IntegrityError:
        existing = find_existing(event)
        if existing:
            return serialize(existing, True), status.HTTP_200_OK
        raise

    return serialize(event, False), status.HTTP_201_CREATED
