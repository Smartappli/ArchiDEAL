"""Data models for the sensor layer."""

# pylint: disable=arguments-differ,import-error,missing-kwoa
# pylint: disable=no-member,no-name-in-module
# pylint: disable=signature-differs,unexpected-keyword-arg

from typing import Any

from django.db import models
from django.db.models import F, Q
from django.db.models.constraints import CheckConstraint, UniqueConstraint
from django.db.models.fields.json import JSONField
from django.db.models.indexes import Index

from dealdata_common.models import (
    OBSERVED_OBJECT_ID_HELP_TEXT,
    OBSERVED_OBJECT_ID_VERBOSE_NAME,
    WildFiEventBase,
    event_identity_payload,
    event_metadata as _event_metadata,
    parse_event_datetime as _parse_event_datetime,
    parse_optional_event_datetime as _parse_optional_event_datetime,
    payload_dict as _payload_dict,
    stable_event_hash as _stable_event_hash,
    uuid7_value,
)

IMU_PAYLOAD_KEYS = {
    "accx",
    "accy",
    "accz",
    "gyrox",
    "gyroy",
    "gyroz",
    "magx",
    "magy",
    "magz",
}
ENVIRONMENT_PAYLOAD_KEYS = {
    "batteryvoltage",
    "humidity",
    "pressure",
    "temperature",
    "temperatureindegcel",
}


def _sensor_type_from_mqtt_topic(mqtt_topic: Any) -> str:
    """Infer a stable sensor type from common DEALIoT/WildFi MQTT topics."""
    aliases = {
        "acc": "imu",
        "accelerometer": "imu",
        "bme": "environment",
        "decoded": "decoded",
        "environment": "environment",
        "gateway": "metadata",
        "imu": "imu",
        "mag": "imu",
        "metadata": "metadata",
        "move": "movement",
        "movement": "movement",
        "prox": "proximity",
        "proximity": "proximity",
        "sensor": "sensor",
        "telemetry": "telemetry",
    }
    topic = str(mqtt_topic or "")
    for part in reversed([item for item in topic.lower().split("/") if item]):
        inferred = aliases.get(part)
        if inferred:
            return inferred
    return ""


def _sensor_type_from_payload(payload: dict[str, Any]) -> str:
    """Infer sensor type from known decoded WildFi payload keys."""
    keys = {str(key) for key in payload}
    lowered = {key.lower() for key in keys}

    if lowered & IMU_PAYLOAD_KEYS:
        return "imu"
    if lowered & ENVIRONMENT_PAYLOAD_KEYS:
        return "environment"
    if lowered & {"proximity", "prox", "distance", "distance_mm"}:
        return "proximity"
    if lowered & {"movement", "activity", "odba"}:
        return "movement"
    return ""


def _infer_sensor_type(event: dict[str, Any], payload: dict[str, Any]) -> str:
    """Infer sensor type with explicit values taking precedence."""
    sensor_type = (
        event.get("sensor_type")
        or payload.get("sensor_type")
        or payload.get("type")
        or _sensor_type_from_mqtt_topic(event.get("mqtt_topic"))
        or _sensor_type_from_payload(payload)
    )
    return str(sensor_type or "")


class Sensor(models.Model):
    """Physical sensor metadata."""

    sensor_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    sensor_vendor = models.CharField(
        max_length=32,
        blank=False,
        null=False,
        verbose_name="Vendor",
        help_text="Bosch",
    )
    sensor_model = models.CharField(
        max_length=32,
        blank=False,
        null=False,
        verbose_name="Model",
        help_text="BMP 680",
    )
    sensor_code = models.CharField(
        max_length=32,
        blank=False,
        null=False,
        verbose_name="Sensor Code",
        help_text="Sensor n°1",
    )
    sensor_create_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    sensor_update_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )

    class Meta:
        """Model metadata for sensors."""

        constraints = [
            UniqueConstraint(
                fields=["sensor_code"],
                name="uq_sensor_code",
            ),
        ]

    def __str__(self) -> str:
        """Return the sensor code."""
        return self.sensor_code


class SensorObservedObject(models.Model):
    """Association between a sensor and an observed object."""

    sensor_observed_object_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    sensor_observed_object_object_id = models.UUIDField(
        verbose_name=OBSERVED_OBJECT_ID_VERBOSE_NAME,
        help_text=OBSERVED_OBJECT_ID_HELP_TEXT,
    )
    sensor_observed_object_sensor = models.ForeignKey(
        Sensor,
        on_delete=models.CASCADE,
        related_name="sensor_observed_object_sensor",
    )
    sensor_observed_object_start_time = models.TimeField()
    sensor_observed_object_end_time = models.TimeField()
    sensor_observed_object_notes = models.CharField(max_length=255)
    sensor_observed_object_create_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    sensor_observed_object_update_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )

    class Meta:
        """Model metadata for sensor-observed object links."""

        constraints = [
            CheckConstraint(
                condition=Q(
                    sensor_observed_object_end_time__gte=F(
                        "sensor_observed_object_start_time",
                    ),
                ),
                name="soo_end_time_gte_start_time",
            ),
        ]

    def __str__(self) -> str:
        """Return the linked sensor code."""
        return self.sensor_observed_object_sensor.sensor_code


class SensorData(models.Model):
    """Raw sensor measurements."""

    sensor_data_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    sensor_data_sensor = models.ForeignKey(
        Sensor,
        on_delete=models.CASCADE,
        related_name="sensor_data_sensor",
    )
    sensor_data_utc_date = models.DateField()
    sensor_data_utc_time = models.TimeField()
    sensor_data_lmt_date = models.DateField()
    sensor_data_lmt_time = models.TimeField()
    sensor_data_value = JSONField(default=dict)
    sensor_data_create_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    sensor_data_update_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )

    def __str__(self) -> str:
        """Return the sensor data value as a string."""
        return str(self.sensor_data_value)


class DecodedSensorEvent(WildFiEventBase):
    """Decoded WildFi sensor event received from DEALIoT."""

    wildfi_decoded_sensor_event_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    dealiot_topic = models.CharField(
        max_length=64,
        default="raw.sensor",
        db_index=True,
    )
    sensor_type = models.CharField(max_length=64, blank=True)

    class Meta:
        """Model metadata for decoded WildFi sensor events."""

        db_table = "sensor_event"

        indexes = [
            Index(fields=["wildfi_device_id", "acquisition_time"]),
            Index(fields=["dealiot_topic", "acquisition_time"]),
            Index(fields=["sensor_type", "acquisition_time"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["source", "event_id"],
                condition=~Q(event_id=""),
                name="uq_wildfi_sensor_source_event_id",
            ),
            UniqueConstraint(
                fields=["source", "payload_hash"],
                condition=~Q(payload_hash=""),
                name="uq_wildfi_sensor_source_payload_hash",
            ),
        ]

    @classmethod
    def from_dealiot_event(
        cls,
        event: dict[str, Any],
        *,
        topic: str = "raw.sensor",
    ) -> "DecodedSensorEvent":
        """Build a sensor event from the decoded DEALIoT contract."""
        payload = _payload_dict(event.get("payload"))
        device_id = event.get("device_id") or payload.get("device_id")
        if not device_id:
            message = "DEALIoT sensor event must contain 'device_id'."
            raise ValueError(message)

        sensor_type = _infer_sensor_type(event, payload)

        return cls(
            wildfi_device_id=str(device_id),
            event_id=str(event.get("event_id") or event.get("id") or ""),
            message_key=str(event.get("key") or ""),
            payload_hash=_stable_event_hash(event),
            observed_object_id=event.get("observed_object_id"),
            dealiot_topic=str(event.get("topic") or topic),
            source=str(event.get("source") or "wildfi-mqtt"),
            mqtt_topic=str(event.get("mqtt_topic") or ""),
            acquisition_time=_parse_event_datetime(
                event.get("timestamp"),
                "timestamp",
            ),
            ingested_at=_parse_optional_event_datetime(
                event.get("ingested_at"),
                "ingested_at",
            ),
            sensor_type=str(sensor_type),
            payload=payload,
            message_metadata=_event_metadata(event),
        )

    def save(
        self,
        *args,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        """Ensure directly-created events still have an idempotency hash."""
        if not getattr(self, "payload_hash", ""):
            payload = event_identity_payload(
                self,
                sensor_type=self.sensor_type,
            )
            self.payload_hash = _stable_event_hash(payload)
        super().save(
            *args,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def __str__(self) -> str:
        """Return a readable device and timestamp pair."""
        return f"{self.wildfi_device_id} @ {self.acquisition_time.isoformat()}"


class SensorDataObservedObject(models.Model):
    """Sensor data attached to a specific observed object."""

    sensor_data_observed_object_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    sensor_data_observed_object_sensor = models.ForeignKey(
        Sensor,
        on_delete=models.CASCADE,
        related_name="sensor_data_observed_object_sensor",
    )
    sensor_data_observed_object_object_id = models.UUIDField(
        verbose_name=OBSERVED_OBJECT_ID_VERBOSE_NAME,
        help_text=OBSERVED_OBJECT_ID_HELP_TEXT,
    )
    sensor_data_observed_object_acquisition_time = models.DateTimeField()
    sensor_data_observed_object_value = JSONField(
        default=dict,
    )
    sensor_data_observed_object_create_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    sensor_data_observed_object_update_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )

    def __str__(self) -> str:
        """Return the observed-object sensor data value as a string."""
        return str(self.sensor_data_observed_object_value)
