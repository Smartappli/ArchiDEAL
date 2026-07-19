"""Serializers for GPS metadata and ingestion contracts."""

import math

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from dealdata_common.serializers import (
    MAX_INGEST_BATCH_SIZE,
    WildFiEventIngestSerializer,
    validate_payload_object,
)

from .models import GPSSensor


class GPSSensorSerializer(serializers.ModelSerializer):
    """Expose GPS sensor metadata through a stable public contract."""

    id = serializers.UUIDField(source="gps_sensors_id", read_only=True)
    code = serializers.CharField(
        source="gps_sensors_code",
        max_length=64,
        validators=[UniqueValidator(queryset=GPSSensor.objects.all())],
    )
    purchase_date = serializers.DateField(source="gps_sensor_purchase_date")
    frequency = serializers.FloatField(source="gps_sensor_frequency")
    vendor = serializers.CharField(
        source="gps_sensor_vendor",
        max_length=128,
        required=False,
        allow_blank=True,
    )
    model = serializers.CharField(
        source="gps_sensor_model",
        max_length=128,
        required=False,
        allow_blank=True,
    )
    sim_card = serializers.CharField(
        source="gps_sensor_sim_card",
        max_length=64,
        required=False,
        allow_blank=True,
    )
    active = serializers.BooleanField(
        source="gps_sensor_active",
        required=False,
    )
    created_at = serializers.DateTimeField(
        source="gps_sensor_created_at",
        read_only=True,
    )
    updated_at = serializers.DateTimeField(
        source="gps_sensor_updated_at",
        read_only=True,
    )

    class Meta:
        """Map the public field names to the legacy GPS model fields."""

        model = GPSSensor
        fields = (
            "id",
            "code",
            "purchase_date",
            "frequency",
            "vendor",
            "model",
            "sim_card",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    @staticmethod
    def validate_frequency(value: float) -> float:
        """Reject sampling rates that cannot describe a usable sensor."""
        if not math.isfinite(value) or value <= 0:
            raise serializers.ValidationError(
                "Ensure this value is a finite number greater than zero.",
            )
        return value


class WildFiGPSIngestSerializer(WildFiEventIngestSerializer):
    """Validate the decoded DEALIoT `raw.gps` ingestion payload."""

    latitude = serializers.FloatField(required=False)
    lat = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    lon = serializers.FloatField(required=False)
    lng = serializers.FloatField(required=False)
    altitude = serializers.FloatField(required=False, allow_null=True)
    alt = serializers.FloatField(required=False, allow_null=True)
    altitude_m = serializers.FloatField(required=False, allow_null=True)
    speed = serializers.FloatField(required=False, allow_null=True)
    speed_m_s = serializers.FloatField(required=False, allow_null=True)
    heading = serializers.FloatField(required=False, allow_null=True)
    course = serializers.FloatField(required=False, allow_null=True)
    heading_deg = serializers.FloatField(required=False, allow_null=True)
    payload = serializers.JSONField(required=False)

    @staticmethod
    def validate_payload(value):
        """The decoded WildFi payload must stay queryable as an object."""
        return validate_payload_object(value, allow_empty=True)

    def validate(self, attrs):
        """Require GPS coordinates either at top level or in payload."""
        _ = self.fields
        payload = attrs.get("payload") or {}
        has_latitude = any(
            key in attrs or key in payload for key in ("latitude", "lat")
        )
        has_longitude = any(
            key in attrs or key in payload for key in ("longitude", "lon", "lng")
        )
        if not has_latitude:
            raise serializers.ValidationError(
                {"latitude": "This field is required."},
            )
        if not has_longitude:
            raise serializers.ValidationError(
                {"longitude": "This field is required."},
            )
        return attrs


class WildFiGPSBatchSerializer(serializers.Serializer):
    """Validate a batch of decoded DEALIoT `raw.gps` events."""

    events = WildFiGPSIngestSerializer(
        many=True,
        max_length=MAX_INGEST_BATCH_SIZE,
    )
