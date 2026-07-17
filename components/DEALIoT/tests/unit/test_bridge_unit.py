from __future__ import annotations

import base64
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any, ClassVar, cast
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = REPO_ROOT / "mqtt-kafka-bridge" / "bridge.py"


class _FakeKafkaProducer:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.sent: list[tuple[str, bytes, dict]] = []

    def send(self, topic, key, value):
        self.sent.append((topic, key, value))

        future = Mock()
        future.add_callback = Mock()
        future.add_errback = Mock()
        return future

    def flush(self, timeout=None):
        return timeout


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.username = None
        self.password = None
        self.on_connect = None
        self.on_message = None
        self.subscriptions: list[tuple[str, int]] = []
        self.tls_config = None
        self.tls_insecure = None

    def username_pw_set(self, username, password):
        self.username = username
        self.password = password

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))

    def tls_set(self, **kwargs):
        self.tls_config = kwargs

    def tls_insecure_set(self, value):
        self.tls_insecure = value


class _FakeCallbackApiVersion:
    VERSION2 = object()


def _load_bridge_module():
    fake_kafka_mod = types.ModuleType("kafka")
    cast("Any", fake_kafka_mod).KafkaProducer = _FakeKafkaProducer

    fake_kafka_errors = types.ModuleType("kafka.errors")
    cast("Any", fake_kafka_errors).KafkaError = Exception

    fake_mqtt_client_mod = types.ModuleType("paho.mqtt.client")
    cast("Any", fake_mqtt_client_mod).Client = _FakeClient
    cast("Any", fake_mqtt_client_mod).CallbackAPIVersion = _FakeCallbackApiVersion

    fake_paho_mqtt_mod = types.ModuleType("paho.mqtt")
    cast("Any", fake_paho_mqtt_mod).client = fake_mqtt_client_mod

    fake_paho_mod = types.ModuleType("paho")
    cast("Any", fake_paho_mod).mqtt = fake_paho_mqtt_mod

    with patch.dict(
        sys.modules,
        {
            "kafka": fake_kafka_mod,
            "kafka.errors": fake_kafka_errors,
            "paho": fake_paho_mod,
            "paho.mqtt": fake_paho_mqtt_mod,
            "paho.mqtt.client": fake_mqtt_client_mod,
        },
    ):
        spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
        if spec is None:
            raise RuntimeError("Unable to load module spec for bridge.py")
        if spec.loader is None:
            raise RuntimeError("Unable to load bridge.py module loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class BridgeUnitTests(unittest.TestCase):
    bridge: ClassVar[Any]

    @classmethod
    def setUpClass(cls):
        cls.bridge = _load_bridge_module()

    def test_decode_payload_valid_json(self):
        payload = b'{"temperature": 21.5}'
        decoded = self.bridge.decode_payload(payload)
        self.assertEqual(decoded["temperature"], 21.5)

    def test_decode_payload_invalid_bytes_returns_base64(self):
        payload = b"\xff\x00\x88"
        decoded = self.bridge.decode_payload(payload)
        self.assertEqual(decoded["payload_b64"], base64.b64encode(payload).decode("ascii"))

    def test_pick_kafka_topic_and_device_id_helpers(self):
        self.assertEqual(self.bridge.pick_kafka_topic("devices/a1/gnss/fix"), "raw.gps")
        self.assertEqual(self.bridge.pick_kafka_topic("wildfi/tags/WF-001/rawgps"), "raw.gps")
        self.assertEqual(self.bridge.pick_kafka_topic("wildfi/tags/WF-001/imu"), "raw.sensor")
        self.assertEqual(
            self.bridge.pick_kafka_topic("devices/a1/lidar/frame"),
            "raw.image3d.meta",
        )
        self.assertEqual(
            self.bridge.pick_kafka_topic("devices/a1/unknown"),
            self.bridge.DEFAULT_KAFKA_TOPIC,
        )
        self.assertEqual(self.bridge.derive_device_id("/tenant/devices/cam-07/video"), "cam-07")
        self.assertEqual(self.bridge.derive_device_id("wildfi/tags/WF-001/gps"), "WF-001")
        self.assertEqual(self.bridge.derive_device_id("wildfi/WF-002/environment"), "WF-002")
        self.assertEqual(self.bridge.derive_device_id("orphan-topic"), "orphan-topic")
        self.assertEqual(self.bridge.derive_device_id("/"), "unknown")
        self.assertEqual(self.bridge.pick_key("/tenant/devices/cam-07/video"), b"cam-07")

    def test_timestamp_helpers_cover_fallback_string_seconds_and_milliseconds(self):
        fallback = "2026-01-01T00:00:00+00:00"

        self.assertEqual(self.bridge.normalized_timestamp(None, fallback), fallback)
        self.assertEqual(self.bridge.normalized_timestamp("", fallback), fallback)
        self.assertEqual(
            self.bridge.normalized_timestamp(1_704_067_200, fallback),
            "2024-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            self.bridge.normalized_timestamp(1_704_067_200_000, fallback),
            "2024-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            self.bridge.normalized_timestamp("already-normalized", fallback),
            "already-normalized",
        )
        self.assertEqual(self.bridge.pick_event_timestamp(["not", "a", "dict"], fallback), fallback)
        self.assertEqual(
            self.bridge.pick_event_timestamp({"time": "2026-02-01T00:00:00+00:00"}, fallback),
            "2026-02-01T00:00:00+00:00",
        )

    def test_csv_env_or_default_ignores_empty_items(self):
        with patch.dict(
            self.bridge.os.environ,
            {"UNIT_TOPICS": " devices/#, , wildfi/# "},
            clear=False,
        ):
            self.assertEqual(
                self.bridge.csv_env_or_default("UNIT_TOPICS", "fallback/#"),
                ("devices/#", "wildfi/#"),
            )

    def test_csv_env_or_default_falls_back_when_configured_value_is_empty(self):
        with patch.dict(self.bridge.os.environ, {"UNIT_TOPICS": " , "}, clear=False):
            self.assertEqual(
                self.bridge.csv_env_or_default("UNIT_TOPICS", " devices/#, wildfi/# "),
                ("devices/#", "wildfi/#"),
            )

    def test_bool_env_parses_truthy_values(self):
        with patch.dict(self.bridge.os.environ, {"UNIT_BOOL": "yes"}, clear=False):
            self.assertTrue(self.bridge.bool_env("UNIT_BOOL"))
        with patch.dict(self.bridge.os.environ, {"UNIT_BOOL": "0"}, clear=False):
            self.assertFalse(self.bridge.bool_env("UNIT_BOOL", default=True))

    def test_allowed_secret_directories_reads_configured_directories(self):
        first = REPO_ROOT / "secrets"
        second = REPO_ROOT / "tmp-secrets"
        with patch.dict(
            self.bridge.os.environ,
            {"DEALIOT_SECRET_DIRECTORIES": f"{first}{self.bridge.os.pathsep}{second}"},
            clear=False,
        ):
            self.assertEqual(
                self.bridge.allowed_secret_directories(),
                (first.resolve(strict=False), second.resolve(strict=False)),
            )

    def test_kafka_security_config_supports_sasl_ssl(self):
        with patch.dict(
            self.bridge.os.environ,
            {
                "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
                "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
                "KAFKA_SASL_USERNAME": "bridge",
                "KAFKA_SASL_PASSWORD": "secret",
                "KAFKA_SSL_CAFILE": "/etc/ssl/kafka/ca.pem",
            },
            clear=False,
        ):
            config = self.bridge.kafka_security_config()

        self.assertEqual(config["security_protocol"], "SASL_SSL")
        self.assertEqual(config["sasl_mechanism"], "SCRAM-SHA-512")
        self.assertEqual(config["sasl_plain_username"], "bridge")
        self.assertEqual(config["sasl_plain_password"], "secret")
        self.assertEqual(config["ssl_cafile"], "/etc/ssl/kafka/ca.pem")
        self.assertTrue(config["ssl_check_hostname"])

    def test_kafka_security_config_rejects_missing_sasl_credentials(self):
        with (
            patch.dict(
                self.bridge.os.environ,
                {"KAFKA_SECURITY_PROTOCOL": "SASL_SSL"},
                clear=True,
            ),
            self.assertRaisesRegex(
                ValueError,
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD must both be set",
            ),
        ):
            self.bridge.kafka_security_config()

    def test_kafka_security_config_includes_ssl_client_material(self):
        with patch.dict(
            self.bridge.os.environ,
            {
                "KAFKA_SECURITY_PROTOCOL": "SSL",
                "KAFKA_SSL_CERTFILE": "/etc/ssl/kafka/client.pem",
                "KAFKA_SSL_KEYFILE": "/etc/ssl/kafka/client.key",
                "KAFKA_SSL_CHECK_HOSTNAME": "false",
            },
            clear=True,
        ):
            config = self.bridge.kafka_security_config()

        self.assertEqual(config["ssl_certfile"], "/etc/ssl/kafka/client.pem")
        self.assertEqual(config["ssl_keyfile"], "/etc/ssl/kafka/client.key")
        self.assertFalse(config["ssl_check_hostname"])

    def test_env_or_secret_file_prefers_environment_value(self):
        with patch.dict(
            self.bridge.os.environ,
            {
                "UNIT_SECRET": "from-env",
                "UNIT_SECRET_FILE": "missing-file",
            },
            clear=False,
        ):
            self.assertEqual(self.bridge.env_or_secret_file("UNIT_SECRET"), "from-env")

    def test_env_or_secret_file_reads_file_value(self):
        secret_path = REPO_ROOT / "secrets" / "unit_bridge_secret.txt"
        secret_path.parent.mkdir(exist_ok=True)
        secret_path.write_text("from-file\n", encoding="utf-8")
        try:
            with patch.dict(
                self.bridge.os.environ,
                {"UNIT_SECRET_FILE": str(secret_path)},
                clear=False,
            ):
                self.assertEqual(self.bridge.env_or_secret_file("UNIT_SECRET"), "from-file")
        finally:
            secret_path.unlink(missing_ok=True)

    def test_env_or_secret_file_returns_none_when_unset(self):
        with patch.dict(self.bridge.os.environ, {}, clear=True):
            self.assertIsNone(self.bridge.env_or_secret_file("UNIT_SECRET"))

    def test_env_or_secret_file_rejects_untrusted_file_path(self):
        untrusted_secret = REPO_ROOT / "unit_bridge_untrusted_secret.txt"
        untrusted_secret.write_text("from-file\n", encoding="utf-8")
        try:
            with (
                patch.dict(
                    self.bridge.os.environ,
                    {"UNIT_SECRET_FILE": str(untrusted_secret)},
                    clear=False,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "UNIT_SECRET_FILE must point to an allowed secret directory",
                ),
            ):
                self.bridge.env_or_secret_file("UNIT_SECRET")
        finally:
            untrusted_secret.unlink(missing_ok=True)

    def test_build_event_sensor_and_gps_and_media(self):
        sensor_msg = types.SimpleNamespace(
            topic="tenant/devices/sensor-1/sensor",
            payload=json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "v": 4}).encode(),
            qos=1,
            retain=False,
        )
        topic, key, event = self.bridge.build_event(sensor_msg)
        self.assertEqual(topic, "raw.sensor")
        self.assertEqual(key, b"sensor-1")
        self.assertEqual(event["payload"]["v"], 4)

        gps_msg = types.SimpleNamespace(
            topic="tenant/devices/veh-1/gnss/fix",
            payload=json.dumps({"lat": 1.1, "lon": 2.2, "speed": 9.9}).encode(),
            qos=0,
            retain=False,
        )
        topic, _key, event = self.bridge.build_event(gps_msg)
        self.assertEqual(topic, "raw.gps")
        self.assertEqual(event["latitude"], 1.1)
        self.assertEqual(event["longitude"], 2.2)
        self.assertEqual(event["speed_m_s"], 9.9)

        wildfi_gps_msg = types.SimpleNamespace(
            topic="wildfi/tags/WF-001/gps",
            payload=json.dumps(
                {
                    "utcTimestamp": 1704067200,
                    "lat": 47.695,
                    "lon": 9.132,
                    "hdop": 1.4,
                }
            ).encode(),
            qos=1,
            retain=False,
        )
        topic, key, event = self.bridge.build_event(wildfi_gps_msg)
        self.assertEqual(topic, "raw.gps")
        self.assertEqual(key, b"WF-001")
        self.assertEqual(event["device_id"], "WF-001")
        self.assertEqual(event["timestamp"], "2024-01-01T00:00:00+00:00")
        self.assertEqual(event["latitude"], 47.695)
        self.assertEqual(event["longitude"], 9.132)
        self.assertEqual(event["source"], "wildfi-mqtt")

        wildfi_sensor_msg = types.SimpleNamespace(
            topic="wildfi/tags/WF-001/environment",
            payload=json.dumps(
                {"utc_timestamp": 1704067200000, "temperatureInDegCel": 18.7}
            ).encode(),
            qos=1,
            retain=False,
        )
        topic, key, event = self.bridge.build_event(wildfi_sensor_msg)
        self.assertEqual(topic, "raw.sensor")
        self.assertEqual(key, b"WF-001")
        self.assertEqual(event["timestamp"], "2024-01-01T00:00:00+00:00")
        self.assertEqual(event["payload"]["temperatureInDegCel"], 18.7)
        self.assertEqual(event["source"], "wildfi-mqtt")

        media_msg = types.SimpleNamespace(
            topic="tenant/devices/cam-1/video2d",
            payload=json.dumps({"frame": 12}).encode(),
            qos=1,
            retain=True,
        )
        with patch.object(self.bridge, "now_iso", return_value="2026-01-01T00:00:00+00:00"):
            topic, _key, event = self.bridge.build_event(media_msg)
        self.assertEqual(topic, "raw.video2d.meta")
        self.assertEqual(event["device_id"], "cam-1")
        self.assertEqual(event["frame"], 12)

    def test_route_event_sends_invalid_media_metadata_to_dlq(self):
        msg = types.SimpleNamespace(topic="tenant/devices/cam-1/video2d")
        event = {
            "device_id": "cam-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "frame": 12,
        }

        topic, routed = self.bridge.route_event(msg, "raw.video2d.meta", event)

        self.assertEqual(topic, self.bridge.DLQ_TOPIC)
        self.assertEqual(routed["intended_topic"], "raw.video2d.meta")
        self.assertIn("missing required field: bucket", routed["errors"])
        self.assertIn("field not allowed by raw.video2d.meta: frame", routed["errors"])

    def test_route_event_keeps_valid_media_metadata_on_raw_topic(self):
        msg = types.SimpleNamespace(topic="tenant/devices/cam-1/video2d")
        event = {
            "device_id": "cam-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ingested_at": "2026-01-01T00:00:01+00:00",
            "bucket": "media-raw-2d-videos",
            "object_key": "cam-1/file.mp4",
            "object_uri": "s3://media-raw-2d-videos/cam-1/file.mp4",
            "format": "mp4",
            "source": "mqtt-bridge",
            "mqtt_topic": msg.topic,
            "qos": 1,
            "retain": False,
        }

        topic, routed = self.bridge.route_event(msg, "raw.video2d.meta", event)

        self.assertEqual(topic, "raw.video2d.meta")
        self.assertEqual(routed, event)

    def test_on_connect_subscribes_on_success(self):
        client = _FakeClient()
        with patch.object(
            self.bridge,
            "MQTT_TOPICS",
            ("$share/ingestors/devices/#", "$share/ingestors/wildfi/#"),
        ):
            self.bridge.on_connect(client, None, None, 0)

        self.assertIn((self.bridge.MQTT_TOPIC, 1), client.subscriptions)
        self.assertIn(("$share/ingestors/wildfi/#", 1), client.subscriptions)

    def test_on_connect_failure_does_not_subscribe(self):
        client = _FakeClient()
        self.bridge.on_connect(client, None, None, 2)
        self.assertEqual(client.subscriptions, [])

    def test_on_message_sends_and_registers_callbacks(self):
        future = Mock()
        fake_producer = Mock()
        fake_producer.send.return_value = future
        msg = types.SimpleNamespace(
            topic="tenant/devices/sensor-1/sensor",
            payload=b'{"value": 5}',
            qos=0,
            retain=False,
        )

        with patch.object(self.bridge, "producer", fake_producer):
            self.bridge.on_message(None, None, msg)

        fake_producer.send.assert_called_once()
        sent_topic = fake_producer.send.call_args.args[0]
        self.assertEqual(sent_topic, "raw.sensor")
        future.add_callback.assert_called_once_with(self.bridge.on_send_success)
        future.add_errback.assert_called_once_with(self.bridge.on_send_error)

    def test_run_bridge_retries_after_oserror(self):
        client = Mock()
        client.connect.side_effect = [OSError("offline"), KeyboardInterrupt()]

        with (
            patch.object(self.bridge.time, "sleep") as mock_sleep,
            self.assertRaises(KeyboardInterrupt),
        ):
            self.bridge.run_bridge(client)

        mock_sleep.assert_called_once_with(5)
        client.loop_forever.assert_not_called()

    def test_run_bridge_enters_mqtt_loop_after_connect(self):
        client = Mock()
        client.loop_forever.side_effect = KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.bridge.run_bridge(client)

        client.connect.assert_called_once_with(
            self.bridge.MQTT_HOST,
            self.bridge.MQTT_PORT,
            keepalive=30,
        )
        client.loop_forever.assert_called_once_with()

    def test_start_health_server_uses_configured_loopback_bind(self):
        fake_server = Mock()
        fake_thread = Mock()

        with (
            patch.object(self.bridge, "BRIDGE_HEALTH_BIND", "127.0.0.1"),
            patch.object(
                self.bridge,
                "ThreadingHTTPServer",
                return_value=fake_server,
            ) as server_ctor,
            patch.object(self.bridge.threading, "Thread", return_value=fake_thread) as thread_ctor,
        ):
            self.bridge.start_health_server()

        server_ctor.assert_called_once_with(
            ("127.0.0.1", self.bridge.BRIDGE_HEALTH_PORT),
            self.bridge.HealthHandler,
        )
        thread_ctor.assert_called_once_with(
            target=fake_server.serve_forever,
            name="bridge-health",
            daemon=True,
        )
        fake_thread.start.assert_called_once_with()

    def test_main_sets_credentials_and_runs_bridge(self):
        client = _FakeClient()
        with (
            patch.object(self.bridge, "MQTT_USERNAME", "user"),
            patch.object(self.bridge, "MQTT_PASSWORD", "pass"),
            patch.object(self.bridge, "MQTT_TLS_ENABLED", new=False),
            patch.object(self.bridge.mqtt_client, "Client", return_value=client),
            patch.object(self.bridge, "start_health_server") as mock_health,
            patch.object(self.bridge, "run_bridge") as mock_run,
        ):
            self.bridge.main()

        self.assertEqual(client.username, "user")
        self.assertEqual(client.password, "pass")
        self.assertEqual(client.on_connect, self.bridge.on_connect)
        self.assertEqual(client.on_message, self.bridge.on_message)
        mock_health.assert_called_once_with()
        mock_run.assert_called_once_with(client)

    def test_main_configures_mqtt_tls_when_enabled(self):
        client = _FakeClient()
        with (
            patch.object(self.bridge, "MQTT_USERNAME", "user"),
            patch.object(self.bridge, "MQTT_PASSWORD", "pass"),
            patch.object(self.bridge, "MQTT_TLS_ENABLED", new=True),
            patch.object(self.bridge, "MQTT_TLS_CA_FILE", "/etc/ssl/mqtt/ca.pem"),
            patch.object(self.bridge, "MQTT_TLS_CERT_FILE", "/etc/ssl/mqtt/client.pem"),
            patch.object(self.bridge, "MQTT_TLS_KEY_FILE", "/etc/ssl/mqtt/client.key"),
            patch.object(self.bridge, "MQTT_TLS_INSECURE_SKIP_VERIFY", new=False),
            patch.object(self.bridge.mqtt_client, "Client", return_value=client),
            patch.object(self.bridge, "start_health_server"),
            patch.object(self.bridge, "run_bridge"),
        ):
            self.bridge.main()

        tls_config = client.tls_config
        self.assertIsNotNone(tls_config)
        assert tls_config is not None
        self.assertEqual(tls_config["ca_certs"], "/etc/ssl/mqtt/ca.pem")
        self.assertEqual(tls_config["certfile"], "/etc/ssl/mqtt/client.pem")
        self.assertEqual(tls_config["keyfile"], "/etc/ssl/mqtt/client.key")
        self.assertEqual(tls_config["cert_reqs"], self.bridge.ssl.CERT_REQUIRED)
        self.assertIsNone(client.tls_insecure)

    def test_main_configures_mqtt_tls_insecure_skip_verify(self):
        client = _FakeClient()
        with (
            patch.object(self.bridge, "MQTT_USERNAME", None),
            patch.object(self.bridge, "MQTT_PASSWORD", None),
            patch.object(self.bridge, "MQTT_TLS_ENABLED", new=True),
            patch.object(self.bridge, "MQTT_TLS_CA_FILE", None),
            patch.object(self.bridge, "MQTT_TLS_CERT_FILE", None),
            patch.object(self.bridge, "MQTT_TLS_KEY_FILE", None),
            patch.object(self.bridge, "MQTT_TLS_INSECURE_SKIP_VERIFY", new=True),
            patch.object(self.bridge.mqtt_client, "Client", return_value=client),
            patch.object(self.bridge, "start_health_server"),
            patch.object(self.bridge, "run_bridge"),
        ):
            self.bridge.main()

        tls_config = client.tls_config
        self.assertIsNotNone(tls_config)
        assert tls_config is not None
        self.assertEqual(tls_config["cert_reqs"], self.bridge.ssl.CERT_NONE)
        self.assertTrue(client.tls_insecure)

    def test_main_raises_when_mqtt_credentials_are_partial(self):
        with (
            patch.object(self.bridge, "MQTT_USERNAME", "user"),
            patch.object(self.bridge, "MQTT_PASSWORD", None),
            self.assertRaisesRegex(
                ValueError,
                "MQTT_USERNAME and MQTT_PASSWORD must both be set when MQTT auth is enabled",
            ),
        ):
            self.bridge.main()


if __name__ == "__main__":
    unittest.main()
