"""Tests for the gps_data application."""

from argparse import ArgumentTypeError
from io import StringIO
import json
import os
from secrets import token_urlsafe
import sys
import types
from unittest import TestCase
from unittest.mock import patch

from django.core.checks import Tags, run_checks
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import Client, override_settings
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from gps_data.models import GPSSensor, ProcessedGPSDataObservedObject, WildFiGPSFix
from dealdata_common.kafka import (
    DealIotKafkaCommand,
    boolean_env,
    kafka_security_options,
    non_negative_int,
    positive_int,
)
from dealdata_common.views import INVALID_LIST_QUERY_PARAMETERS_DETAIL

CHECK = TestCase()
EMPTY_INGEST_TOKEN = str()
TEST_INGEST_TOKEN = token_urlsafe(32)


@pytest.mark.parametrize(
    ("parser", "value", "expected"),
    [(non_negative_int, "0", 0), (positive_int, "1", 1)],
)
def test_kafka_integer_option_parsers_accept_supported_values(
    parser,
    value: str,
    expected: int,
) -> None:
    """Kafka worker options accept their documented integer ranges."""
    CHECK.assertEqual(parser(value), expected)


@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (non_negative_int, "-1"),
        (non_negative_int, "not-an-integer"),
        (positive_int, "0"),
    ],
)
def test_kafka_integer_option_parsers_reject_invalid_values(parser, value: str) -> None:
    """Kafka worker options reject invalid values before connecting to a broker."""
    with pytest.raises(ArgumentTypeError):
        parser(value)


def test_kafka_security_defaults_to_plaintext() -> None:
    """Kafka consumers remain compatible with unsecured development brokers."""
    with patch.dict(os.environ, {}, clear=True):
        options = kafka_security_options()

    CHECK.assertEqual(options, {"security_protocol": "PLAINTEXT"})


def test_kafka_security_supports_sasl_ssl_and_mutual_tls() -> None:
    """Kafka security settings map to the kafka-python consumer arguments."""
    environment = {
        "DEALDATA_KAFKA_SECURITY_PROTOCOL": "sasl_ssl",
        "DEALDATA_KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
        "DEALDATA_KAFKA_SASL_USERNAME": "dealdata",
        "DEALDATA_KAFKA_SASL_PASSWORD": "unit-secret",
        "DEALDATA_KAFKA_SSL_CAFILE": "/run/secrets/kafka/ca.pem",
        "DEALDATA_KAFKA_SSL_CERTFILE": "/run/secrets/kafka/client.pem",
        "DEALDATA_KAFKA_SSL_KEYFILE": "/run/secrets/kafka/client.key",
        "DEALDATA_KAFKA_SSL_CHECK_HOSTNAME": "false",
    }

    with patch.dict(os.environ, environment, clear=True):
        options = kafka_security_options()

    CHECK.assertEqual(
        options,
        {
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": "SCRAM-SHA-512",
            "sasl_plain_username": "dealdata",
            "sasl_plain_password": "unit-secret",
            "ssl_cafile": "/run/secrets/kafka/ca.pem",
            "ssl_certfile": "/run/secrets/kafka/client.pem",
            "ssl_keyfile": "/run/secrets/kafka/client.key",
            "ssl_check_hostname": False,
        },
    )


def test_kafka_security_accepts_shared_dealiot_variable_names() -> None:
    """The consumer can reuse the generic Kafka settings used by DEALIoT."""
    environment = {
        "KAFKA_SECURITY_PROTOCOL": "SSL",
        "KAFKA_SSL_CAFILE": "/run/secrets/kafka/ca.pem",
        "KAFKA_SSL_CHECK_HOSTNAME": "true",
    }

    with patch.dict(os.environ, environment, clear=True):
        options = kafka_security_options()

    CHECK.assertEqual(
        options,
        {
            "security_protocol": "SSL",
            "ssl_cafile": "/run/secrets/kafka/ca.pem",
            "ssl_check_hostname": True,
        },
    )


@pytest.mark.parametrize("value", ["invalid", "2", "enabled"])
def test_kafka_ssl_hostname_check_rejects_invalid_booleans(value: str) -> None:
    """Hostname verification cannot be silently disabled by a typo."""
    with (
        patch.dict(os.environ, {"KAFKA_SSL_CHECK_HOSTNAME": value}, clear=True),
        pytest.raises(CommandError, match="must be one of"),
    ):
        boolean_env("KAFKA_SSL_CHECK_HOSTNAME", default=True)


@pytest.mark.parametrize(
    "environment",
    [
        {
            "DEALDATA_KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
            "DEALDATA_KAFKA_SASL_USERNAME": "dealdata",
        },
        {
            "DEALDATA_KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
            "DEALDATA_KAFKA_SASL_PASSWORD": "unit-secret",
        },
    ],
)
def test_kafka_sasl_requires_username_and_password(environment: dict[str, str]) -> None:
    """Partial SASL credentials fail before a broker connection is attempted."""
    with (
        patch.dict(os.environ, environment, clear=True),
        pytest.raises(CommandError, match="must both be set"),
    ):
        kafka_security_options()


def test_kafka_mutual_tls_requires_certificate_and_key() -> None:
    """A partial mutual-TLS identity fails with a configuration error."""
    environment = {
        "DEALDATA_KAFKA_SECURITY_PROTOCOL": "SSL",
        "DEALDATA_KAFKA_SSL_CERTFILE": "/run/secrets/kafka/client.pem",
    }

    with (
        patch.dict(os.environ, environment, clear=True),
        pytest.raises(CommandError, match="must both be set"),
    ):
        kafka_security_options()


def test_kafka_security_rejects_unknown_protocol() -> None:
    """Unsupported kafka-python security protocol names fail clearly."""
    environment = {"DEALDATA_KAFKA_SECURITY_PROTOCOL": "HTTPS"}

    with (
        patch.dict(os.environ, environment, clear=True),
        pytest.raises(CommandError, match="must be one of"),
    ):
        kafka_security_options()


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (
            {"bootstrap_servers": "unit:9092", "topic": " ", "group_id": "group"},
            "Kafka topic",
        ),
        (
            {"bootstrap_servers": "unit:9092", "topic": "raw.gps", "group_id": " "},
            "Kafka group ID",
        ),
    ],
)
def test_kafka_consumer_requires_topic_and_group_id(options, message: str) -> None:
    """Kafka workers fail clearly when a topic or group ID is blank."""
    with pytest.raises(CommandError, match=message):
        DealIotKafkaCommand._build_consumer(options)


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    SECURE_HSTS_SECONDS=0,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=False,
    DEALDATA_REQUIRE_INGEST_TOKEN=True,
    DEALDATA_INGEST_TOKEN=EMPTY_INGEST_TOKEN,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}},
)
def test_deployment_checks_reject_insecure_ingestion_configuration() -> None:
    """Production checks reject missing HTTPS, HSTS, and ingestion-token settings."""
    error_ids = {
        message.id
        for message in run_checks(
            tags=[Tags.security],
            include_deployment_checks=True,
        )
    }

    CHECK.assertTrue(
        {
            "dealdata.E001",
            "dealdata.E002",
            "dealdata.E003",
            "dealdata.E004",
            "dealdata.E005",
            "dealdata.E006",
            "dealdata.E007",
            "dealdata.E008",
        }
        <= error_ids,
    )


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
    DEALDATA_REQUIRE_INGEST_TOKEN=True,
    DEALDATA_INGEST_TOKEN=TEST_INGEST_TOKEN,
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "PASSWORD": "database-secret",  # nosec B106 - test fixture.
            "OPTIONS": {
                "sslmode": "verify-full",
                "sslrootcert": "/run/secrets/postgres/ca.crt",
            },
        },
    },
)
def test_deployment_checks_accept_hardened_ingestion_configuration() -> None:
    """Production checks accept the supported HTTPS and ingestion settings."""
    error_ids = {
        message.id
        for message in run_checks(
            tags=[Tags.security],
            include_deployment_checks=True,
        )
    }

    CHECK.assertFalse(
        {error_id for error_id in error_ids if error_id.startswith("dealdata.")},
    )


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    DEALDATA_REQUIRE_INGEST_TOKEN=False,
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "PASSWORD": "database-secret",  # nosec B106 - test fixture.
            "OPTIONS": None,
        },
    },
)
def test_deployment_checks_handle_null_database_options() -> None:
    """A null OPTIONS mapping reports TLS errors instead of crashing checks."""
    error_ids = {
        message.id
        for message in run_checks(
            tags=[Tags.security],
            include_deployment_checks=True,
        )
    }

    CHECK.assertTrue({"dealdata.E007", "dealdata.E008"} <= error_ids)


def test_gps_sensor_string_representation() -> None:
    """GPS sensors are represented by their code."""
    gps_sensor = GPSSensor(gps_sensors_code="GPS-001")

    CHECK.assertEqual(str(gps_sensor), "GPS-001")


def test_wildfi_gps_fix_from_dealiot_event() -> None:
    """WildFi GPS events keep the DEALIoT envelope and decoded coordinates."""
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "ingested_at": "2026-05-24T12:30:03Z",
        "source": "wildfi-mqtt",
        "mqtt_topic": "wildfi/wildfi-17/gps",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "altitude": 121.5,
        "payload": {"fix": 3, "hdop": 0.9},
        "qos": 1,
        "retain": False,
    }

    gps_fix = WildFiGPSFix.from_dealiot_event(event)

    CHECK.assertEqual(gps_fix.wildfi_device_id, "wildfi-17")
    CHECK.assertEqual(gps_fix.dealiot_topic, "raw.gps")
    CHECK.assertEqual(gps_fix.latitude, 50.6333)
    CHECK.assertEqual(gps_fix.longitude, 5.5667)
    CHECK.assertEqual(gps_fix.payload, {"fix": 3, "hdop": 0.9})
    CHECK.assertEqual(gps_fix.message_metadata, {"qos": 1, "retain": False})
    CHECK.assertEqual(
        gps_fix.as_geojson(),
        {
            "type": "Point",
            "coordinates": [5.5667, 50.6333],
        },
    )
    CHECK.assertTrue(gps_fix.payload_hash)


@pytest.mark.django_db
def test_wildfi_gps_ingest_is_idempotent() -> None:
    """Posting the same DEALIoT GPS event twice does not duplicate it."""
    client = APIClient()
    event = {
        "event_id": "gps-event-1",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }

    first_response = client.post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
    )
    second_response = client.post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
    )

    CHECK.assertEqual(first_response.status_code, 201)
    CHECK.assertEqual(second_response.status_code, 200)
    CHECK.assertIs(second_response.data["duplicate"], True)
    CHECK.assertEqual(WildFiGPSFix.objects.count(), 1)


@pytest.mark.django_db
def test_wildfi_gps_ingest_accepts_dealiot_metric_aliases() -> None:
    """GPS ingestion normalizes DEALIoT metric field names."""
    client = APIClient()
    event = {
        "event_id": "gps-event-dealiot-aliases",
        "device_id": "WF-001",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "source": "wildfi-mqtt",
        "mqtt_topic": "wildfi/tags/WF-001/gps",
        "latitude": 47.695,
        "longitude": 9.132,
        "altitude_m": 411.2,
        "speed_m_s": 1.8,
        "heading_deg": 84.5,
        "payload": {"fixType": 3},
    }

    response = client.post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
    )

    gps_fix = WildFiGPSFix.objects.get(event_id="gps-event-dealiot-aliases")
    CHECK.assertEqual(response.status_code, 201)
    CHECK.assertEqual(gps_fix.altitude, 411.2)
    CHECK.assertEqual(gps_fix.speed, 1.8)
    CHECK.assertEqual(gps_fix.heading, 84.5)


@pytest.mark.django_db
def test_dealiot_kafka_consumer_matches_http_gps_ingestion() -> None:
    """Kafka retries keep the event first persisted through the HTTP API."""
    event = {
        "event_id": "gps-event-kafka",
        "device_id": "WF-004",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "latitude": 47.695,
        "longitude": 9.132,
        "altitude_m": 411.2,
    }
    http_response = APIClient().post(
        "/api/ingest/wildfi/gps/",
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
                topic="raw.gps",
                partition=0,
                offset=10,
            )
            return {"raw.gps-0": [message]}

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

    gps_fix = WildFiGPSFix.objects.get(event_id="gps-event-kafka")
    CHECK.assertEqual(http_response.status_code, 201)
    CHECK.assertEqual(http_response.data["id"], str(gps_fix.wildfi_gps_fix_id))
    CHECK.assertEqual(http_response.data["payload_hash"], gps_fix.payload_hash)
    CHECK.assertEqual(gps_fix.altitude, 411.2)
    CHECK.assertEqual(WildFiGPSFix.objects.count(), 1)
    CHECK.assertIn("duplicates=1", stdout.getvalue())
    CHECK.assertEqual(
        FakeKafkaConsumer.instances[0].kwargs["security_protocol"],
        "PLAINTEXT",
    )
    CHECK.assertIs(FakeKafkaConsumer.instances[0].committed, True)
    CHECK.assertIs(FakeKafkaConsumer.instances[0].closed, True)


@pytest.mark.django_db
def test_wildfi_gps_batch_ingest_accepts_duplicates() -> None:
    """Batch ingestion reports inserts and duplicates without failing."""
    client = APIClient()
    event = {
        "event_id": "gps-event-2",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }

    response = client.post(
        "/api/ingest/wildfi/gps/batch/",
        {"events": [event, event]},
        format="json",
    )

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.data["inserted"], 1)
    CHECK.assertEqual(response.data["duplicates"], 1)
    CHECK.assertEqual(response.data["errors"], 0)
    CHECK.assertEqual(WildFiGPSFix.objects.count(), 1)


def test_wildfi_gps_ingest_rejects_missing_longitude() -> None:
    """GPS validation rejects events without a longitude."""
    client = APIClient()
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "payload": {"fix": 3},
    }

    response = client.post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertIn("longitude", str(response.data["detail"]))


def test_wildfi_gps_ingest_rejects_non_finite_payload_coordinate() -> None:
    """GPS ingestion rejects non-finite coordinate values from decoded payloads."""
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "payload": {"lat": "NaN", "lon": 5.5667},
    }

    response = APIClient().post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertIn("finite", str(response.data["detail"]))


@pytest.mark.django_db
def test_wildfi_gps_ingest_rejects_out_of_range_coordinates() -> None:
    """GPS ingestion returns validation errors instead of persisting bad points."""
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 91,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }

    response = APIClient().post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(WildFiGPSFix.objects.count(), 0)


@pytest.mark.django_db
def test_wildfi_gps_ingest_rejects_invalid_token(settings) -> None:
    """Ingestion rejects requests with a wrong shared token."""
    settings.DEALDATA_INGEST_TOKEN = token_urlsafe(32)
    client = APIClient()
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }

    response = client.post(
        "/api/ingest/wildfi/gps/",
        event,
        format="json",
        HTTP_X_DEALDATA_INGEST_TOKEN=f"wrong-{settings.DEALDATA_INGEST_TOKEN}",
    )

    CHECK.assertEqual(response.status_code, 403)
    CHECK.assertEqual(WildFiGPSFix.objects.count(), 0)


@pytest.mark.django_db
def test_wildfi_gps_batch_ingest_accepts_array_body() -> None:
    """Batch ingestion accepts a bare JSON array from DEALIoT."""
    client = APIClient()
    event = {
        "event_id": "gps-event-array",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }

    response = client.post(
        "/api/ingest/wildfi/gps/batch/",
        [event],
        format="json",
    )

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.data["inserted"], 1)


def test_wildfi_gps_batch_ingest_rejects_oversized_batch() -> None:
    """GPS batch ingestion bounds one request to a safe event count."""
    event = {
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }

    response = APIClient().post(
        "/api/ingest/wildfi/gps/batch/",
        {"events": [event] * 1001},
        format="json",
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertIn("1000", str(response.data["detail"]))


@pytest.mark.django_db
def test_wildfi_gps_list_filters_by_device_and_time() -> None:
    """GPS list endpoint filters and paginates stored events."""
    client = APIClient()
    first = {
        "event_id": "gps-list-1",
        "device_id": "wildfi-17",
        "timestamp": "2026-05-24T12:30:00Z",
        "latitude": 50.6333,
        "longitude": 5.5667,
        "payload": {"fix": 3},
    }
    second = {
        "event_id": "gps-list-2",
        "device_id": "wildfi-18",
        "timestamp": "2026-05-24T13:30:00Z",
        "latitude": 51.0,
        "longitude": 5.0,
        "payload": {"fix": 3},
    }
    client.post("/api/ingest/wildfi/gps/", first, format="json")
    client.post("/api/ingest/wildfi/gps/", second, format="json")

    response = client.get(
        "/api/wildfi/gps/",
        {
            "device_id": "wildfi-17",
            "from": "2026-05-24T12:00:00Z",
            "to": "2026-05-24T13:00:00Z",
            "limit": "10",
        },
    )

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.data["count"], 1)
    CHECK.assertEqual(response.data["results"][0]["device_id"], "wildfi-17")
    CHECK.assertEqual(
        response.data["results"][0]["geojson"],
        {
            "type": "Point",
            "coordinates": [5.5667, 50.6333],
        },
    )


def test_wildfi_gps_list_rejects_invalid_datetime() -> None:
    """GPS list endpoint validates date filters."""
    response = APIClient().get("/api/wildfi/gps/", {"from": "not-a-date"})

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(response.data["detail"], INVALID_LIST_QUERY_PARAMETERS_DETAIL)


def test_wildfi_gps_list_rejects_reversed_time_window() -> None:
    """GPS list validation rejects time windows with an inverted range."""
    response = APIClient().get(
        "/api/wildfi/gps/",
        {"from": "2026-05-24T13:00:00Z", "to": "2026-05-24T12:00:00Z"},
    )

    CHECK.assertEqual(response.status_code, 400)
    CHECK.assertEqual(response.data["detail"], INVALID_LIST_QUERY_PARAMETERS_DETAIL)


def test_gps_metrics_exposes_prometheus_counts() -> None:
    """Metrics endpoint exposes a cheap service marker without inventory scans."""
    response = Client().get("/metrics/")

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertIn("dealdata_gps_service_info 1", response.content.decode())


@pytest.mark.django_db
def test_health_ready_reports_database_available() -> None:
    """Readiness checks database access."""
    response = Client().get("/health/ready/")

    CHECK.assertEqual(response.status_code, 200)
    CHECK.assertEqual(response.json()["database"], "available")


def test_health_ready_reports_generic_database_failure() -> None:
    """Readiness failures do not expose database exception details."""
    with patch("gps_data.views.connections") as mocked_connections:
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
def test_processed_gps_data_populates_geojson() -> None:
    """Processed GPS data mirrors lon/lat into GeoJSON."""
    gps_sensor = GPSSensor.objects.create(
        gps_sensors_code="GPS-GEOJSON",
        gps_sensor_purchase_date="2026-05-24",
        gps_sensor_frequency=60,
    )
    processed = ProcessedGPSDataObservedObject.objects.create(
        processed_gps_data_sensors=gps_sensor,
        processed_gps_data_observed_object_uuid="00000000-0000-0000-0000-000000000001",
        processed_gps_data_observed_object_acquisition_time=timezone.now(),
        processed_gps_data_observed_object_longitude=5.5667,
        processed_gps_data_observed_object_latitude=50.6333,
        processed_gps_data_observed_object_insert_timestamp=timezone.now(),
    )

    CHECK.assertEqual(
        processed.processed_gps_data_observed_object_geom,
        {
            "type": "Point",
            "coordinates": [5.5667, 50.6333],
        },
    )
