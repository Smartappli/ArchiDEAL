"""Serializer helpers shared by DEALData ingestion APIs."""

from rest_framework import serializers

MAX_INGEST_BATCH_SIZE = 1000


class WildFiEventIngestSerializer(serializers.Serializer):
    """Common DEALIoT event envelope fields."""

    event_id = serializers.CharField(required=False, allow_blank=True)
    id = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField()
    timestamp = serializers.DateTimeField()
    ingested_at = serializers.DateTimeField(required=False, allow_null=True)
    topic = serializers.CharField(required=False, allow_blank=True)
    source = serializers.CharField(required=False, allow_blank=True)
    mqtt_topic = serializers.CharField(required=False, allow_blank=True)
    key = serializers.CharField(required=False, allow_blank=True)
    qos = serializers.IntegerField(required=False)
    retain = serializers.BooleanField(required=False)
    partition = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)
    observed_object_id = serializers.UUIDField(required=False, allow_null=True)


def validate_payload_object(value, *, allow_empty: bool) -> dict:
    """Validate decoded WildFi payloads as JSON objects."""
    if allow_empty and value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Expected a JSON object.")
    return value
