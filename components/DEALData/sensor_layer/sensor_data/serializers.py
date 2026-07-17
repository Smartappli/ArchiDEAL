"""Serializers for sensor ingestion contracts."""

from rest_framework import serializers

from dealdata_common.serializers import (
    MAX_INGEST_BATCH_SIZE,
    WildFiEventIngestSerializer,
    validate_payload_object,
)


class WildFiSensorIngestSerializer(WildFiEventIngestSerializer):
    """Validate the decoded DEALIoT `raw.sensor` ingestion payload."""

    sensor_type = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.JSONField()

    @staticmethod
    def validate_payload(value):
        """The decoded WildFi payload must stay queryable as an object."""
        return validate_payload_object(value, allow_empty=False)


class WildFiSensorBatchSerializer(serializers.Serializer):
    """Validate a batch of decoded DEALIoT `raw.sensor` events."""

    events = WildFiSensorIngestSerializer(
        many=True,
        max_length=MAX_INGEST_BATCH_SIZE,
    )
