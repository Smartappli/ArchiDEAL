"""View helpers shared by DEALData ingestion APIs."""

from __future__ import annotations

from datetime import UTC
from secrets import compare_digest
from typing import Callable

from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response

INVALID_LIST_QUERY_PARAMETERS_DETAIL = "Invalid list query parameters."
IngestEvent = Callable[[dict], tuple[dict, int]]


class QueryParameterError(ValueError):
    """Raised when list query parameters fail validation."""


def ingestion_token_error(request) -> Response | None:
    """Return a forbidden response when the shared ingestion token is invalid."""
    token = getattr(settings, "DEALDATA_INGEST_TOKEN", "")
    if not token:
        return None
    supplied_token = request.headers.get("X-DEALDATA-INGEST-TOKEN", "")
    if compare_digest(supplied_token, token):
        return None
    return Response(
        {"detail": "Invalid ingestion token."},
        status=status.HTTP_403_FORBIDDEN,
    )


def parse_positive_int(
    value: str | None, field_name: str, default: int, maximum: int
) -> int:
    """Parse a non-negative integer query value and cap it at a maximum."""
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        message = f"Query parameter '{field_name}' must be a positive integer."
        raise QueryParameterError(message) from exc
    if parsed < 0:
        message = f"Query parameter '{field_name}' must be a positive integer."
        raise QueryParameterError(message)
    return min(parsed, maximum)


def parse_datetime_filter(value: str | None, field_name: str):
    """Parse an ISO datetime query value, defaulting naive values to UTC."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        message = f"Query parameter '{field_name}' must be an ISO datetime."
        raise QueryParameterError(message)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_list_params(query_params) -> tuple[int, int, object, object]:
    """Parse common pagination and time-window query parameters."""
    limit = parse_positive_int(
        query_params.get("limit"),
        "limit",
        default=100,
        maximum=1000,
    )
    offset = parse_positive_int(
        query_params.get("offset"),
        "offset",
        default=0,
        maximum=1_000_000,
    )
    started_at = parse_datetime_filter(query_params.get("from"), "from")
    ended_at = parse_datetime_filter(query_params.get("to"), "to")
    if started_at and ended_at and started_at > ended_at:
        message = "Query parameter 'from' must be earlier than or equal to 'to'."
        raise QueryParameterError(message)
    return limit, offset, started_at, ended_at


def apply_event_filters(queryset, query_params, started_at, ended_at):
    """Apply common device, source, topic and acquisition-time filters."""
    device_id = query_params.get("device_id")
    if device_id:
        queryset = queryset.filter(wildfi_device_id=device_id)
    source = query_params.get("source")
    if source:
        queryset = queryset.filter(source=source)
    topic = query_params.get("topic")
    if topic:
        queryset = queryset.filter(dealiot_topic=topic)
    if started_at:
        queryset = queryset.filter(acquisition_time__gte=started_at)
    if ended_at:
        queryset = queryset.filter(acquisition_time__lte=ended_at)
    return queryset


def batch_ingest_response(
    data, *, serializer_class, ingest_event: IngestEvent
) -> Response:
    """Validate and ingest a batch payload, reporting per-event outcomes."""
    if isinstance(data, list):
        data = {"events": data}
    if not isinstance(data, dict):
        return Response(
            {"detail": "Expected a JSON object or array."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        return Response(
            {"detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = []
    inserted = 0
    duplicates = 0
    errors = 0
    for index, event_payload in enumerate(serializer.validated_data["events"]):
        body, response_status = ingest_event(event_payload)
        result = {"index": index, "status": response_status, **body}
        results.append(result)
        if response_status == status.HTTP_201_CREATED:
            inserted += 1
        elif response_status == status.HTTP_200_OK and body.get("duplicate"):
            duplicates += 1
        else:
            errors += 1

    return Response(
        {
            "inserted": inserted,
            "duplicates": duplicates,
            "errors": errors,
            "results": results,
        },
        status=status.HTTP_200_OK if errors == 0 else status.HTTP_207_MULTI_STATUS,
    )
