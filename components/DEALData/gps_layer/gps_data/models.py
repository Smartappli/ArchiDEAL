"""Data models for the GPS layer."""

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
    event_float as _event_float,
    event_identity_payload,
    event_metadata as _event_metadata,
    parse_event_datetime as _parse_event_datetime,
    parse_optional_event_datetime as _parse_optional_event_datetime,
    payload_dict as _payload_dict,
    stable_event_hash as _stable_event_hash,
    uuid7_value,
)


class GPSSensor(models.Model):
    """GPS sensor metadata and configuration."""

    gps_sensors_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    gps_sensors_code = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="GPS Sensors Code of Identification",
        help_text="e.g.: Ulg GPS 12",
    )
    gps_sensor_purchase_date = models.DateField(
        verbose_name="GPS Sensor Purchase Date",
        help_text="e.g.: 2020-07-07",
    )
    gps_sensor_frequency = models.FloatField(
        verbose_name="GPS Sensor Sampling Rate (Hz)",
        help_text="e.g.: 60",
    )
    gps_sensor_vendor = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="GPS Sensor Vendor Name",
        help_text="e.g.: Globaltek",
    )
    gps_sensor_model = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="GPS Sensor Model",
        help_text="e.g.: FT203",
    )
    gps_sensor_sim_card = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="IEMI Card Number",
        help_text="e.g.: 123454564654651654",
    )
    gps_sensor_active = models.BooleanField(
        default=True,
        verbose_name="GPS Sensor Status",
        help_text="GPS Sensor Status",
    )
    gps_sensor_created_at = models.DateTimeField(auto_now_add=True)
    gps_sensor_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        """Return the sensor code."""
        return self.gps_sensors_code


class ObservedObjectGPSSensor(models.Model):
    """Link an observed object to a GPS sensor over a time interval."""

    observed_object_gps_sensors_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    observed_object_gps_sensor_observed_object_id = models.UUIDField(
        verbose_name=OBSERVED_OBJECT_ID_VERBOSE_NAME,
        help_text=OBSERVED_OBJECT_ID_HELP_TEXT,
    )
    observed_object_gps_sensor_gps_sensor = models.ForeignKey(
        GPSSensor,
        on_delete=models.CASCADE,
        related_name="gps_sensor_link",
    )
    observed_object_start_time = models.DateTimeField()
    observed_object_end_time = models.DateTimeField()
    observed_object_notes = JSONField(
        default=dict,
        verbose_name="GPS Sensor Notes",
        help_text='e.g.: {"type_of_data": "GPS Data Imported from file"}',
    )

    class Meta:
        """Model metadata for observed object and GPS sensor links."""

        constraints = [
            CheckConstraint(
                condition=Q(
                    observed_object_start_time__lte=F(
                        "observed_object_end_time",
                    ),
                ),
                name="ck_timestamp_start_before_end",
            ),
            UniqueConstraint(
                fields=[
                    "observed_object_gps_sensor_observed_object_id",
                    "observed_object_gps_sensor_gps_sensor",
                    "observed_object_start_time",
                ],
                name="uq_obj_sensor_start",
            ),
        ]


class GPSRawData(models.Model):
    """Raw GPS data points imported from acquisition files."""

    gps_raw_data_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    gps_raw_data_sensors_code = models.CharField(max_length=64)
    gps_raw_data_line_no = models.IntegerField()
    gps_raw_data_utc_date = models.DateField()
    gps_raw_data_utc_time = models.TimeField()
    gps_raw_data_lmt_date = models.DateField()
    gps_raw_data_lmt_time = models.TimeField()
    gps_raw_data_ecef_x = models.IntegerField()
    gps_raw_data_ecef_y = models.IntegerField()
    gps_raw_data_ecef_z = models.IntegerField()
    gps_raw_data_latitude = models.FloatField()
    gps_raw_data_longitude = models.FloatField()
    gps_raw_data_height = models.FloatField()
    gps_raw_data_dop = models.FloatField()
    gps_raw_data_nav = models.CharField(max_length=2)
    gps_raw_data_validated = models.CharField(max_length=3)
    gps_raw_data_sats_used = models.IntegerField()
    gps_raw_data_ch01_sat_id = models.IntegerField()
    gps_raw_data_ch01_sat_cnr = models.IntegerField()
    gps_raw_data_ch02_sat_id = models.IntegerField()
    gps_raw_data_ch02_sat_cnr = models.IntegerField()
    gps_raw_data_ch03_sat_id = models.IntegerField()
    gps_raw_data_ch03_sat_cnr = models.IntegerField()
    gps_raw_data_ch04_sat_id = models.IntegerField()
    gps_raw_data_ch04_sat_cnr = models.IntegerField()
    gps_raw_data_ch05_sat_id = models.IntegerField()
    gps_raw_data_ch05_sat_cnr = models.IntegerField()
    gps_raw_data_ch06_sat_id = models.IntegerField()
    gps_raw_data_ch06_sat_cnr = models.IntegerField()
    gps_raw_data_ch07_sat_id = models.IntegerField()
    gps_raw_data_ch07_sat_cnr = models.IntegerField()
    gps_raw_data_ch08_sat_id = models.IntegerField()
    gps_raw_data_ch08_sat_cnr = models.IntegerField()
    gps_raw_data_ch09_sat_id = models.IntegerField()
    gps_raw_data_ch09_sat_cnr = models.IntegerField()
    gps_raw_data_ch10_sat_id = models.IntegerField()
    gps_raw_data_ch10_sat_cnr = models.IntegerField()
    gps_raw_data_ch11_sat_id = models.IntegerField()
    gps_raw_data_ch11_sat_cnr = models.IntegerField()
    gps_raw_data_ch12_sat_id = models.IntegerField()
    gps_raw_data_ch12_sat_cnr = models.IntegerField()
    gps_raw_data_main_vol = models.FloatField()
    gps_raw_data_bu_vol = models.FloatField()
    gps_raw_data_temp = models.FloatField()
    gps_raw_data_easting = models.IntegerField()
    gps_raw_data_northing = models.IntegerField()
    gps_raw_data_remarks = models.TextField()
    gps_raw_data_created_at = models.DateTimeField(auto_now_add=True)
    gps_raw_data_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata for raw GPS data."""

        db_table = "gps_raw_data"


class GPSFix(WildFiEventBase):
    """Decoded WildFi GPS event received from DEALIoT."""

    wildfi_gps_fix_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    dealiot_topic = models.CharField(
        max_length=64,
        default="raw.gps",
        db_index=True,
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)

    class Meta:
        """Model metadata for decoded WildFi GPS fixes."""

        db_table = "gps_fix"

        constraints = [
            CheckConstraint(
                condition=(Q(latitude__gte=-90.0) & Q(latitude__lte=90.0)),
                name="ck_wildfi_gps_latitude_range",
            ),
            CheckConstraint(
                condition=(Q(longitude__gte=-180.0) & Q(longitude__lte=180.0)),
                name="ck_wildfi_gps_longitude_range",
            ),
            UniqueConstraint(
                fields=["source", "event_id"],
                condition=~Q(event_id=""),
                name="uq_wildfi_gps_source_event_id",
            ),
            UniqueConstraint(
                fields=["source", "payload_hash"],
                condition=~Q(payload_hash=""),
                name="uq_wildfi_gps_source_payload_hash",
            ),
        ]
        indexes = [
            Index(fields=["wildfi_device_id", "acquisition_time"]),
            Index(fields=["dealiot_topic", "acquisition_time"]),
        ]

    @classmethod
    def from_dealiot_event(
        cls,
        event: dict[str, Any],
        *,
        topic: str = "raw.gps",
    ) -> "GPSFix":
        """Build a GPS fix from the decoded DEALIoT `raw.gps` contract."""
        payload = _payload_dict(event.get("payload"))
        device_id = event.get("device_id") or payload.get("device_id")
        if not device_id:
            message = "DEALIoT GPS event must contain 'device_id'."
            raise ValueError(message)

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
            latitude=_event_float(
                event,
                payload,
                "latitude",
                "lat",
                required=True,
            ),
            longitude=_event_float(
                event,
                payload,
                "longitude",
                "lon",
                "lng",
                required=True,
            ),
            altitude=_event_float(
                event,
                payload,
                "altitude",
                "alt",
                "altitude_m",
            ),
            speed=_event_float(event, payload, "speed", "speed_m_s"),
            heading=_event_float(
                event,
                payload,
                "heading",
                "course",
                "heading_deg",
            ),
            payload=payload,
            message_metadata=_event_metadata(event),
        )

    def as_geojson(self) -> dict[str, Any]:
        """Return the GPS fix as a GeoJSON point."""
        return {
            "type": "Point",
            "coordinates": [self.longitude, self.latitude],
        }

    def save(
        self,
        *args,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        """Ensure directly-created events still have an idempotency hash."""
        if not self.payload_hash:
            payload = event_identity_payload(
                self,
                latitude=self.latitude,
                longitude=self.longitude,
                altitude=self.altitude,
                speed=self.speed,
                heading=self.heading,
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


class ProcessedGPSDataObservedObject(models.Model):
    """Processed GPS positions associated with an observed object."""

    processed_gps_data_observed_object_id = models.UUIDField(
        primary_key=True,
        default=uuid7_value,
        editable=False,
    )
    processed_gps_data_sensors = models.ForeignKey(
        GPSSensor,
        on_delete=models.CASCADE,
        related_name="gps_sensor_link2",
    )
    processed_gps_data_observed_object_uuid = models.UUIDField(
        verbose_name=OBSERVED_OBJECT_ID_VERBOSE_NAME,
        help_text=OBSERVED_OBJECT_ID_HELP_TEXT,
    )
    processed_gps_data_observed_object_acquisition_time = models.DateTimeField()
    processed_gps_data_observed_object_longitude = models.FloatField()
    processed_gps_data_observed_object_latitude = models.FloatField()
    processed_gps_data_observed_object_geom = JSONField(
        default=dict,
        blank=True,
        verbose_name="Processed GPS Geometry",
        help_text="GeoJSON point in EPSG:4326.",
    )
    processed_gps_data_observed_object_insert_timestamp = models.DateTimeField()

    def save(
        self,
        *args,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        """Populate the geometry from longitude and latitude before saving."""
        lon = self.processed_gps_data_observed_object_longitude
        lat = self.processed_gps_data_observed_object_latitude
        if lon is not None and lat is not None:
            self.processed_gps_data_observed_object_geom = {
                "type": "Point",
                "coordinates": [lon, lat],
            }
        super().save(
            *args,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )
