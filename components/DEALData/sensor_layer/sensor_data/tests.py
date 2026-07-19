"""Test module for the sensor data application."""

from datetime import date, time
from io import StringIO
import json
from secrets import token_urlsafe
import sys
import types
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError
from django.db.models.deletion import PROTECT, ProtectedError
from django.test import Client
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from sensor_data.models import (
    DecodedSensorEvent,
    Sensor,
    SensorData,
    SensorDataObservedObject,
    SensorObservedObject,
)
from dealdata_common.views import INVALID_LIST_QUERY_PARAMETERS_DETAIL

CHECK = TestCase()


def test_sensor_string_representation() -> None:
    """Sensors are represented by their code."""
    sensor = Sensor(
        sensor_vendor="Bosch",
        sensor_model="BMP680",
        sensor_code="SENSOR-001",
    )

    CHECK.assertEqual(str(sensor), "SENSOR-001")


def test_sensor_data_string_representation() -> None:
    """Sensor data values are rendered as strings."""
    sensor_data = SensorData(sensor_data_value={"temperature": 18.5})

    CHECK.assertEqual(str(sensor_data), "{'temperature': 18.5}")


@pytest.mark.django_db
def test_sensor_metadata_endpoints_require_admin_user() -> None:
    """Anonymous and non-admin users cannot operate on sensor metadata."""
    sensor = Sensor.objects.create(
        sensor_vendor="Bosch",
        sensor_model="BMP680",
        sensor_code="SENSOR-AUTH",
    )
    regular_user = get_user_model().objects.create_user(username="sensor-user")
    clients = [APIClient(), APIClient()]
    clients[1].force_authenticate(user=regular_user)
    requests = [
        ("get", "/api/sensors/", None),
        (
            "post",
            "/api/sensors/",
            {
                "vendor": "Vaisala",
                "model": "HMP110",
                "code": "SENSOR-DENIED",
            },
        ),
        ("get", f"/api/sensors/{sensor.sensor_id}/", None),
        (
            "patch",
            f"/api/sensors/{sensor.sensor_id}/",
            {"model": "BME680"},
        ),
        ("delete", f"/api/sensors/{sensor.sensor_id}/", None),
    ]

    for client in clients:
        for method, path, data in requests:
            response = getattr(client, method)(path, data, format="json")
            CHECK.assertEqual(response.status_code, 403)

    sensor.refresh_from_db()
    CHECK.assertEqual(sensor.sensor_model, "BMP680")
    CHECK.assertFalse(Sensor.objects.filter(sensor_code="SENSOR-DENIED").exists())


@pytest.mark.django_db
def test_admin_can_crud_sensor_metadata() -> None:
    """An admin can create, list, retrieve, patch, and delete sensors."""
    admin_user = get_user_model().objects.create_user(
        username="sensor-admin",
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)
    requested_id = uuid4()

    create_response = client.post(
        "/api/sensors/",
        {
            "id": str(requested_id),
            "vendor": "Bosch",
            "model": "BMP680",
            "code": "SENSOR-CRUD",
        },
        format="json",
    )

    CHECK.assertEqual(create_response.status_code, 201)
    sensor_id = create_response.data["id"]
    CHECK.assertNotEqual(sensor_id, str(requested_id))
    CHECK.assertEqual(create_response.data["vendor"], "Bosch")
    CHECK.assertIn("created_at", create_response.data)
    CHECK.assertIn("updated_at", create_response.data)

    list_response = client.get("/api/sensors/")
    detail_response = client.get(f"/api/sensors/{sensor_id}/")

    CHECK.assertEqual(list_response.status_code, 200)
    CHECK.assertEqual(len(list_response.data), 1)
    CHECK.assertEqual(list_response.data[0]["id"], sensor_id)
    CHECK.assertEqual(detail_response.status_code, 200)
    CHECK.assertEqual(detail_response.data["code"], "SENSOR-CRUD")

    replacement_id = uuid4()
    patch_response = client.patch(
        f"/api/sensors/{sensor_id}/",
        {
            "id": str(replacement_id),
            "model": "BME680",
        },
        format="json",
    )

    CHECK.assertEqual(patch_response.status_code, 200)
    CHECK.assertEqual(patch_response.data["id"], sensor_id)
    CHECK.assertEqual(patch_response.data["model"], "BME680")
    CHECK.assertFalse(Sensor.objects.filter(sensor_id=replacement_id).exists())

    delete_response = client.delete(f"/api/sensors/{sensor_id}/")

    CHECK.assertEqual(delete_response.status_code, 204)
    CHECK.assertFalse(Sensor.objects.filter(sensor_id=sensor_id).exists())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "relation_kind",
    ["observed-object-link", "sensor-data", "observed-object-data"],
)
def test_sensor_metadata_delete_refuses_every_scientific_relation(
    relation_kind: str,
) -> None:
    """Deleting metadata cannot remove any linked sensor scientific record."""
    admin_user = get_user_model().objects.create_user(
        username="sensor-delete-admin",
        is_staff=True,
    )
    sensor = Sensor.objects.create(
        sensor_vendor="Bosch",
        sensor_model="BMP680",
        sensor_code="SENSOR-LINKED",
    )
    if relation_kind == "observed-object-link":
        related = SensorObservedObject.objects.create(
            sensor_observed_object_object_id=uuid4(),
            sensor_observed_object_sensor=sensor,
            sensor_observed_object_start_time=time(8, 0),
            sensor_observed_object_end_time=time(9, 0),
            sensor_observed_object_notes="Protected test link",
        )
    elif relation_kind == "sensor-data":
        related = SensorData.objects.create(
            sensor_data_sensor=sensor,
            sensor_data_utc_date=date(2026, 7, 19),
            sensor_data_utc_time=time(8, 0),
            sensor_data_lmt_date=date(2026, 7, 19),
            sensor_data_lmt_time=time(10, 0),
            sensor_data_value={"temperature": 18.5},
        )
    else:
        related = SensorDataObservedObject.objects.create(
            sensor_data_observed_object_sensor=sensor,
            sensor_data_observed_object_object_id=uuid4(),
            sensor_data_observed_object_acquisition_time=timezone.now(),
            sensor_data_observed_object_value={"temperature": 18.5},
        )
    client = APIClient()
    client.force_authenticate(user=admin_user)

    response = client.delete(f"/api/sensors/{sensor.sensor_id}/")

    CHECK.assertEqual(response.status_code, 409)
    CHECK.assertEqual(
        response.data,
        {
            "detail": (
                "This sensor still has measurements or observed-object links. "
                "Remove or migrate those records before deleting its metadata."
            ),
        },
    )
    CHECK.assertTrue(Sensor.objects.filter(pk=sensor.pk).exists())
    CHECK.assertTrue(type(related).objects.filter(pk=related.pk).exists())


@pytest.mark.parametrize(
    ("model", "field_name"),
    [
        (SensorObservedObject, "sensor_observed_object_sensor"),
        (SensorData, "sensor_data_sensor"),
        (SensorDataObservedObject, "sensor_data_observed_object_sensor"),
    ],
)
def test_sensor_scientific_relations_protect_metadata(
    model,
    field_name: str,
) -> None:
    """Every scientific sensor foreign key protects its metadata parent."""
    field = model._meta.get_field(field_name)

    CHECK.assertIs(field.remote_field.on_delete, PROTECT)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "deletion_error",
    [
        pytest.param(
            ProtectedError("protected sensor relation", []),
            id="protected-error",
        ),
        pytest.param(
            IntegrityError("concurrent sensor relation"),
            id="integrity-error",
        ),
    ],
)
def test_sensor_delete_translates_database_conflicts(
    deletion_error: Exception,
) -> None:
    """Late database protection failures keep metadata and return a stable 409."""
    admin_user = get_user_model().objects.create_user(
        username=f"sensor-conflict-admin-{type(deletion_error).__name__}",
        is_staff=True,
    )
    sensor = Sensor.objects.create(
        sensor_vendor="Bosch",
        sensor_model="BMP680",
        sensor_code=f"SENSOR-CONFLICT-{type(deletion_error).__name__}",
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)

    with patch(
        "sensor_data.views.SensorDetailView.perform_destroy",
        side_effect=deletion_error,
    ):
        response = client.delete(f"/api/sensors/{sensor.pk}/")

    CHECK.assertEqual(response.status_code, 409)
    CHECK.assertTrue(Sensor.objects.filter(pk=sensor.pk).exists())


@pytest.mark.django_db
def test_sensor_delete_rolls_back_before_returning_conflict() -> None:
    """A late integrity failure cannot commit a partially completed deletion."""
    admin_user = get_user_model().objects.create_user(
        username="sensor-rollback-admin",
        is_staff=True,
    )
    sensor = Sensor.objects.create(
        sensor_vendor="Bosch",
        sensor_model="BMP680",
        sensor_code="SENSOR-ROLLBACK",
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)

    def delete_then_fail(instance: Sensor) -> None:
        instance.delete()
        raise IntegrityError("late sensor conflict")

    with patch(
        "sensor_data.views.SensorDetailView.perform_destroy",
        side_effect=delete_then_fail,
    ):
        response = client.delete(f"/api/sensors/{sensor.pk}/")

    CHECK.assertEqual(response.status_code, 409)
    CHECK.assertTrue(Sensor.objects.filter(pk=sensor.pk).exists())


@pytest.mark.django_db
def test_sensor_metadata_validation_rejects_invalid_values() -> None:
    """Required, length, and unique constraints are exposed as API errors."""
    admin_user = get_user_model().objects.create_user(
        username="sensor-validation-admin",
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)
    valid_payload = {
        "vendor": "Bosch",
        "model": "BMP680",
        "code": "SENSOR-VALIDATION",
    }
    first_response = client.post("/api/sensors/", valid_payload, format="json")

    missing_response = client.post(
        "/api/sensors/",
        {"model": "BMP680", "code": "SENSOR-MISSING"},
        format="json",
    )
    duplicate_response = client.post(
        "/api/sensors/",
        valid_payload,
        format="json",
    )
    too_long_response = client.post(
        "/api/sensors/",
        {**valid_payload, "code": "S" * 33},
        format="json",
    )

    CHECK.assertEqual(first_response.status_code, 201)
    CHECK.assertEqual(missing_response.status_code, 400)
    CHECK.assertIn("vendor", missing_response.data)
    CHECK.assertEqual(duplicate_response.status_code, 400)
    CHECK.assertIn("code", duplicate_response.data)
    CHECK.assertEqual(too_long_response.status_code, 400)
    CHECK.assertIn("code", too_long_response.data)


@pytest.mark.django_db
def test_sensor_detail_rejects_full_replacement() -> None:
    """The detail contract supports PATCH but not PUT."""
    admin_user = get_user_model().objects.create_user(
        username="sensor-method-admin",
        is_staff=True,
    )
    sensor = Sensor.objects.create(
        sensor_vendor="Bosch",
        sensor_model="BMP680",
        sensor_code="SENSOR-METHOD",
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)

    response = client.put(
        f"/api/sensors/{sensor.sensor_id}/",
        {
            "vendor": "Vaisala",
            "model": "HMP110",
            "code": "SENSOR-METHOD-UPDATED",
        },
        format="json",
    )

    CHECK.assertEqual(response.status_code, 405)


def test_wildfi_sensor_event_from_dealiot_event() -> None:
    """WildFi sensor events keep the DEALIoT envelope and decoded payload."""
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "ingested_at": "2026-05-24T12:30:03Z",
        "source": "wildfi-mqtt",
        "mqtt_topic": "wildfi/wildfi-17/sensor",
        "payload": {
            "sensor_type": "temperature",
            "value": 18.5,
            "unit": "C",
        },
        "qos": 1,
        "retain": False,
    }

    sensor_event = DecodedSensorEvent.from_dealiot_event(event)

    CHECK.assertEqual(sensor_event.wildfi_device_id, "wildfi-17")
    CHECK.assertEqual(sensor_event.dealiot_topic, "raw.sensor")
    CHECK.assertEqual(sensor_event.sensor_type, "temperature")
    CHECK.assertEqual(sensor_event.payload["value"], 18.5)
    CHECK.assertEqual(sensor_event.message_metadata, {"qos": 1, "retain": False})
    CHECK.assertTrue(sensor_event.payload_hash)


@pytest.mark.django_db
def test_wildfi_sensor_ingest_is_idempotent() -> None:
    """Posting the same DEALIoT sensor event twice does not duplicate it."""
    client = APIClient()
    event = {
        "event_id": "sensor-event-1",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {
            "sensor_type": "temperature",
            "value": 18.5,
            "unit": "C",
        },
    }

    first_response = client.post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
    )
    second_response = client.post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
    )

    CHECK.assertEqual(first_response.status_code, 201)
    CHECK.assertEqual(second_response.status_code, 200)
    CHECK.assertIs(second_response.data["duplicate"], True)
    CHECK.assertEqual(DecodedSensorEvent.objects.count(), 1)


@pytest.mark.django_db
def test_repeated_measurements_are_kept_while_source_redelivery_is_deduplicated() -> None:
    """Equal values at different times are events; one stable source ID is a retry."""
    client = APIClient()
    measurement = {
        "device_id": "wildfi-17",
        "payload": {
            "sensor_type": "temperature",
            "value": 20,
            "unit": "C",
        },
    }

    first = client.post(
        "/api/ingest/wildfi/sensor/",
        {**measurement, "timestamp": "2026-05-24T12:30:00Z"},
        format="json",
    )
    second = client.post(
        "/api/ingest/wildfi/sensor/",
        {**measurement, "timestamp": "2026-05-24T12:31:00Z"},
        format="json",
    )
    source_delivery = {
        **measurement,
        "event_id": "a" * 64,
        "timestamp": "2026-05-24T12:32:00Z",
    }
    first_delivery = client.post(
        "/api/ingest/wildfi/sensor/",
        source_delivery,
        format="json",
    )
    redelivery = client.post(
        "/api/ingest/wildfi/sensor/",
        {**source_delivery, "ingested_at": "2026-05-24T12:32:05Z"},
        format="json",
    )

    CHECK.assertEqual((first.status_code, second.status_code), (201, 201))
    CHECK.assertEqual(first_delivery.status_code, 201)
    CHECK.assertEqual(redelivery.status_code, 200)
    CHECK.assertIs(redelivery.data["duplicate"], True)
    CHECK.assertEqual(DecodedSensorEvent.objects.count(), 3)


@pytest.mark.django_db
def test_wildfi_sensor_type_is_inferred_from_dealiot_mqtt_topic() -> None:
    """Sensor ingestion infers a stable type when DEALIoT omits sensor_type."""
    client = APIClient()
    event = {
        "event_id": "sensor-event-imu-topic",
        "device_id": "WF-002",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "source": "wildfi-mqtt",
        "mqtt_topic": "wildfi/tags/WF-002/imu",
        "payload": {
            "accX": -0.05,
            "accY": 0.01,
            "accZ": 0.98,
            "temperatureInDegCel": 18.7,
        },
    }

    response = client.post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
    )

    sensor_event = DecodedSensorEvent.objects.get(
        event_id="sensor-event-imu-topic",
    )
    CHECK.assertEqual(response.status_code, 201)
    CHECK.assertEqual(response.data["sensor_type"], "imu")
    CHECK.assertEqual(sensor_event.sensor_type, "imu")


@pytest.mark.django_db
def test_wildfi_sensor_type_prefers_explicit_payload_value() -> None:
    """Explicit DEALIoT sensor_type values override topic inference."""
    client = APIClient()
    event = {
        "event_id": "sensor-event-explicit-type",
        "device_id": "WF-003",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "mqtt_topic": "wildfi/tags/WF-003/imu",
        "payload": {"sensor_type": "temperature", "value": 18.5},
    }

    response = client.post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
    )

    CHECK.assertEqual(response.status_code, 201)
    CHECK.assertEqual(response.data["sensor_type"], "temperature")


@pytest.mark.django_db
def test_dealiot_kafka_consumer_matches_http_sensor_ingestion() -> None:
    """Kafka retries keep the event first persisted through the HTTP API."""
    event = {
        "event_id": "sensor-event-kafka",
        "device_id": "WF-004",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "mqtt_topic": "wildfi/tags/WF-004/environment",
        "payload": {"temperatureInDegCel": 18.7},
    }
    http_response = APIClient().post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
    )

    class FakeKafkaConsumer:
        """Minimal kafka-python consumer test double."""

        instances = []

        def __init__(self, *args, **kwargs):
            """Record initialization parameters and default state."""
            self.args = args
            self.kwargs = kwargs
            self.polls = 0
            self.committed = False
            self.closed = False
            self.instances.append(self)

        def poll(self, timeout_ms, max_records):
            """Return one batch, then no further records."""
            del timeout_ms, max_records
            if self.polls:
                return {}
            self.polls += 1
            message = types.SimpleNamespace(
                value=json.dumps(event).encode("utf-8"),
                topic="raw.sensor",
                partition=0,
                offset=11,
            )
            return {"raw.sensor-0": [message]}

        def commit(self):
            """Mark the fake consumer as committed."""
            self.committed = True

        def close(self):
            """Mark the fake consumer as closed."""
            self.closed = True

    fake_kafka = types.SimpleNamespace(KafkaConsumer=FakeKafkaConsumer)
    stdout = StringIO()

    with patch.dict(sys.modules, {"kafka": fake_kafka}):
        call_command(
            "consume_dealiot_kafka",
            "--once",
            "--bootstrap-servers",
            "unit:9092",
            stdout=stdout,
            stderr=StringIO(),
        )

    sensor_event = DecodedSensorEvent.objects.get(
        event_id="sensor-event-kafka",
    )
    CHECK.assertEqual(http_response.status_code, 201)
    CHECK.assertEqual(
        http_response.data["id"],
        str(sensor_event.wildfi_decoded_sensor_event_id),
    )
    CHECK.assertEqual(http_response.data["payload_hash"], sensor_event.payload_hash)
    CHECK.assertEqual(sensor_event.sensor_type, "environment")
    CHECK.assertEqual(DecodedSensorEvent.objects.count(), 1)
    CHECK.assertIn("duplicates=1", stdout.getvalue())
    CHECK.assertIs(FakeKafkaConsumer.instances[0].committed, True)
    CHECK.assertIs(FakeKafkaConsumer.instances[0].closed, True)


@pytest.mark.django_db
def test_wildfi_sensor_batch_ingest_accepts_duplicates() -> None:
    """Batch ingestion reports inserts and duplicates without failing."""
    client = APIClient()
    event = {
        "event_id": "sensor-event-2",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {
            "sensor_type": "temperature",
            "value": 18.5,
            "unit": "C",
        },
    }

    response = client.post(
        "/api/ingest/wildfi/sensor/batch/",
        {"events": [event, event]},
        format="json",
    )

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.data["inserted"], 1)
    CHECK.assertEqual(response.data["duplicates"], 1)
    CHECK.assertEqual(response.data["errors"], 0)
    CHECK.assertEqual(DecodedSensorEvent.objects.count(), 1)


def test_wildfi_sensor_ingest_rejects_scalar_payload() -> None:
    """Sensor validation rejects non-object decoded payloads."""
    client = APIClient()
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": 18.5,
    }

    response = client.post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertIn("payload", str(response.data["detail"]))


@pytest.mark.django_db
def test_wildfi_sensor_ingest_rejects_invalid_token(settings) -> None:
    """Ingestion rejects requests with a wrong shared token."""
    settings.DEALDATA_INGEST_TOKEN = token_urlsafe(32)
    client = APIClient()
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {"sensor_type": "temperature", "value": 18.5},
    }

    response = client.post(
        "/api/ingest/wildfi/sensor/",
        event,
        format="json",
        HTTP_X_DEALDATA_INGEST_TOKEN=f"wrong-{settings.DEALDATA_INGEST_TOKEN}",
    )

    CHECK.assertEqual(response.status_code, 403)
    CHECK.assertEqual(DecodedSensorEvent.objects.count(), 0)


@pytest.mark.django_db
def test_wildfi_sensor_batch_ingest_accepts_array_body() -> None:
    """Batch ingestion accepts a bare JSON array from DEALIoT."""
    client = APIClient()
    event = {
        "event_id": "sensor-event-array",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {"sensor_type": "temperature", "value": 18.5},
    }

    response = client.post(
        "/api/ingest/wildfi/sensor/batch/",
        [event],
        format="json",
    )

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.data["inserted"], 1)


def test_wildfi_sensor_batch_ingest_rejects_oversized_batch() -> None:
    """Sensor batch ingestion bounds one request to a safe event count."""
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {"sensor_type": "temperature", "value": 18.5},
    }

    response = APIClient().post(
        "/api/ingest/wildfi/sensor/batch/",
        {"events": [event] * 1001},
        format="json",
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertIn("1000", str(response.data["detail"]))


@pytest.mark.django_db
def test_wildfi_sensor_list_filters_by_device_type_and_time() -> None:
    """Sensor list endpoint filters and paginates stored events."""
    client = APIClient()
    client.force_authenticate(
        user=types.SimpleNamespace(is_authenticated=True, is_staff=True),
    )
    first = {
        "event_id": "sensor-list-1",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {"sensor_type": "temperature", "value": 18.5},
    }
    second = {
        "event_id": "sensor-list-2",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T13:30:00Z",
        "payload": {"sensor_type": "humidity", "value": 62},
    }
    client.post("/api/ingest/wildfi/sensor/", first, format="json")
    client.post("/api/ingest/wildfi/sensor/", second, format="json")

    response = client.get(
        "/api/wildfi/sensor/",
        {
            "device_id": "wildfi-17",
            "sensor_type": "temperature",
            "from": "2026-05-24T12:00:00Z",
            "to": "2026-05-24T13:00:00Z",
            "limit": "10",
        },
    )

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.data["count"], 1)
    CHECK.assertEqual(response.data["results"][0]["sensor_type"], "temperature")
    CHECK.assertEqual(response.data["results"][0]["payload"]["value"], 18.5)
    for historical_field in ("payload", "metadata", "payload_hash", "topic"):
        CHECK.assertIn(historical_field, response.data["results"][0])

    summary_response = client.get(
        "/api/wildfi/sensor/",
        {"device_id": "wildfi-17", "sensor_type": "temperature", "summary": "true"},
    )

    CHECK.assertEqual(summary_response.status_code, 200)
    CHECK.assertEqual(
        set(summary_response.data["results"][0]),
        {
            "id",
            "device_id",
            "observed_object_id",
            "timestamp",
            "sensor_type",
        },
    )
    for sensitive_field in ("payload", "metadata", "payload_hash", "topic"):
        CHECK.assertNotIn(sensitive_field, summary_response.data["results"][0])


def test_wildfi_sensor_list_rejects_invalid_datetime() -> None:
    """Sensor list endpoint validates date filters."""
    client = APIClient()
    client.force_authenticate(
        user=types.SimpleNamespace(is_authenticated=True, is_staff=True),
    )

    response = client.get("/api/wildfi/sensor/", {"from": "not-a-date"})

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(response.data["detail"], INVALID_LIST_QUERY_PARAMETERS_DETAIL)


def test_wildfi_sensor_list_rejects_reversed_time_window() -> None:
    """Sensor list validation rejects time windows with an inverted range."""
    client = APIClient()
    client.force_authenticate(
        user=types.SimpleNamespace(is_authenticated=True, is_staff=True),
    )

    response = client.get(
        "/api/wildfi/sensor/",
        {"from": "2026-05-24T13:00:00Z", "to": "2026-05-24T12:00:00Z"},
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(response.data["detail"], INVALID_LIST_QUERY_PARAMETERS_DETAIL)


def test_wildfi_sensor_list_rejects_anonymous_requests() -> None:
    """Stored sensor events are not exposed without authentication."""
    response = APIClient().get("/api/wildfi/sensor/")

    CHECK.assertIn(response.status_code, {401, 403})


def test_wildfi_sensor_list_rejects_authenticated_non_staff() -> None:
    """A regular authenticated principal cannot read sensitive sensor events."""
    client = APIClient()
    client.force_authenticate(
        user=types.SimpleNamespace(is_authenticated=True, is_staff=False),
    )

    response = client.get("/api/wildfi/sensor/")

    CHECK.assertEqual(response.status_code, 403)


def test_sensor_metrics_exposes_prometheus_counts() -> None:
    """Metrics endpoint exposes a cheap service marker without inventory scans."""
    response = Client().get("/metrics/")

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertIn("dealdata_sensor_service_info 1", response.content.decode())


@pytest.mark.django_db
def test_health_ready_reports_database_available() -> None:
    """Readiness checks database access."""
    response = Client().get("/health/ready/")

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.json()["database"], "available")


def test_health_ready_reports_generic_database_failure() -> None:
    """Readiness failures do not expose database exception details."""
    with patch("sensor_data.views.connections") as mocked_connections:
        mocked_connections.__getitem__.side_effect = DatabaseError(
            "database password leaked",
        )
        response = Client().get("/health/ready/")

    body = response.json()
    CHECK.assertEqual(response.status_code, 503)
    CHECK.assertEqual(body["database"], "unavailable")
    CHECK.assertEqual(body["detail"], "Database connection check failed.")
    CHECK.assertNotIn("password", str(body))


@pytest.mark.parametrize(
    "path",
    ["/health/live/", "/health/ready/", "/metrics/"],
)
def test_observability_endpoints_reject_unsafe_methods(path: str) -> None:
    """Read-only observability endpoints reject unsafe HTTP methods."""
    response = Client().post(path)

    CHECK.assertEqual(response.status_code, 405)
    CHECK.assertEqual(response.headers["Allow"], "GET, HEAD")


@pytest.mark.django_db
def test_sensor_event_direct_save_populates_payload_hash() -> None:
    """Directly-created sensor events still receive an idempotency hash."""
    event = DecodedSensorEvent.from_dealiot_event(
        {
            "device_id": "wildfi-17",
            "timestamp": "2026-05-24T12:30:00Z",
            "payload": {"sensor_type": "temperature", "value": 18.5},
        },
    )
    event.payload_hash = ""

    event.save()

    CHECK.assertTrue(event.payload_hash)
