"""Serializers for sensor metadata and ingestion contracts."""

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from dealdata_common.serializers import (
    MAX_INGEST_BATCH_SIZE,
    WildFiEventIngestSerializer,
    validate_payload_object,
)

from .models import Sensor


class SensorSerializer(serializers.ModelSerializer):
    """Serialize the metadata managed for a physical sensor."""

    id = serializers.UUIDField(source="sensor_id", read_only=True)
    vendor = serializers.CharField(source="sensor_vendor", max_length=32)
    model = serializers.CharField(source="sensor_model", max_length=32)
    code = serializers.CharField(
        source="sensor_code",
        max_length=32,
        validators=[UniqueValidator(queryset=Sensor.objects.all())],
    )
    created_at = serializers.DateTimeField(
        source="sensor_create_at",
        read_only=True,
    )
    updated_at = serializers.DateTimeField(
        source="sensor_update_at",
        read_only=True,
    )

    class Meta:
        """Expose sensor metadata while keeping generated fields immutable."""

        model = Sensor
        fields = [
            "id",
            "vendor",
            "model",
            "code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
