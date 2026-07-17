"""Serializers for GPS ingestion contracts."""

from rest_framework import serializers

from dealdata_common.serializers import (
    MAX_INGEST_BATCH_SIZE,
    WildFiEventIngestSerializer,
    validate_payload_object,
)


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
