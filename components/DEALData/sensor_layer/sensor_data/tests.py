"""Test module for the sensor data application."""

from io import StringIO
import json
from secrets import token_urlsafe
import sys
import types
from unittest import TestCase
from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client
import pytest
from rest_framework.test import APIClient

from sensor_data.models import Sensor, SensorData, WildFiDecodedSensorEvent
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

    sensor_event = WildFiDecodedSensorEvent.from_dealiot_event(event)

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
    CHECK.assertEqual(WildFiDecodedSensorEvent.objects.count(), 1)


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
    CHECK.assertEqual(WildFiDecodedSensorEvent.objects.count(), 3)


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

    sensor_event = WildFiDecodedSensorEvent.objects.get(
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

    sensor_event = WildFiDecodedSensorEvent.objects.get(
        event_id="sensor-event-kafka",
    )
    CHECK.assertEqual(http_response.status_code, 201)
    CHECK.assertEqual(
        http_response.data["id"],
        str(sensor_event.wildfi_decoded_sensor_event_id),
    )
    CHECK.assertEqual(http_response.data["payload_hash"], sensor_event.payload_hash)
    CHECK.assertEqual(sensor_event.sensor_type, "environment")
    CHECK.assertEqual(WildFiDecodedSensorEvent.objects.count(), 1)
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
    CHECK.assertEqual(WildFiDecodedSensorEvent.objects.count(), 1)


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
    CHECK.assertEqual(WildFiDecodedSensorEvent.objects.count(), 0)


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


def test_wildfi_sensor_list_rejects_invalid_datetime() -> None:
    """Sensor list endpoint validates date filters."""
    response = APIClient().get("/api/wildfi/sensor/", {"from": "not-a-date"})

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(response.data["detail"], INVALID_LIST_QUERY_PARAMETERS_DETAIL)


def test_wildfi_sensor_list_rejects_reversed_time_window() -> None:
    """Sensor list validation rejects time windows with an inverted range."""
    response = APIClient().get(
        "/api/wildfi/sensor/",
        {"from": "2026-05-24T13:00:00Z", "to": "2026-05-24T12:00:00Z"},
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(response.data["detail"], INVALID_LIST_QUERY_PARAMETERS_DETAIL)


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
    event = WildFiDecodedSensorEvent.from_dealiot_event(
        {
            "device_id": "wildfi-17",
            "timestamp": "2026-05-24T12:30:00Z",
            "payload": {"sensor_type": "temperature", "value": 18.5},
        },
    )
    event.payload_hash = ""

    event.save()

    CHECK.assertTrue(event.payload_hash)
