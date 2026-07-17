from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from typing import Any, ClassVar

from test_bridge_unit import _load_bridge_module

REPO_ROOT = Path(__file__).resolve().parents[2]


class WildFiIngestionUnitTests(unittest.TestCase):
    bridge: ClassVar[Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.bridge = _load_bridge_module()

    def test_decoded_wildfi_gps_payload_routes_to_raw_gps(self) -> None:
        message = types.SimpleNamespace(
            topic="wildfi/tags/WF-001/gps",
            payload=json.dumps(
                {
                    "utcTimestamp": 1704067200000,
                    "latitude_deg": 47.695,
                    "longitude_deg": 9.132,
                    "altitude_m": 411.2,
                    "speed_m_s": 1.8,
                    "heading_deg": 84.5,
                    "fixType": 3,
                }
            ).encode(),
            qos=1,
            retain=False,
        )

        topic, key, event = self.bridge.build_event(message)

        self.assertEqual(topic, "raw.gps")
        self.assertEqual(key, b"WF-001")
        self.assertEqual(event["source"], "wildfi-mqtt")
        self.assertEqual(event["device_id"], "WF-001")
        self.assertEqual(event["timestamp"], "2024-01-01T00:00:00+00:00")
        self.assertEqual(event["latitude"], 47.695)
        self.assertEqual(event["longitude"], 9.132)
        self.assertEqual(event["altitude_m"], 411.2)
        self.assertEqual(event["speed_m_s"], 1.8)
        self.assertEqual(event["heading_deg"], 84.5)
        self.assertEqual(event["payload"]["fixType"], 3)
        self.assertEqual(self.bridge.route_event(message, topic, event), (topic, event))

    def test_decoded_wildfi_imu_payload_routes_to_raw_sensor(self) -> None:
        message = types.SimpleNamespace(
            topic="wildfi/tags/WF-002/imu",
            payload=json.dumps(
                {
                    "utc_timestamp": 1704067200,
                    "accX": -0.05,
                    "accY": 0.01,
                    "accZ": 0.98,
                    "temperatureInDegCel": 18.7,
                    "batteryVoltage": 3.91,
                }
            ).encode(),
            qos=1,
            retain=False,
        )

        topic, key, event = self.bridge.build_event(message)

        self.assertEqual(topic, "raw.sensor")
        self.assertEqual(key, b"WF-002")
        self.assertEqual(event["source"], "wildfi-mqtt")
        self.assertEqual(event["device_id"], "WF-002")
        self.assertEqual(event["timestamp"], "2024-01-01T00:00:00+00:00")
        self.assertEqual(event["payload"]["accZ"], 0.98)
        self.assertEqual(event["payload"]["temperatureInDegCel"], 18.7)
        self.assertEqual(event["payload"]["batteryVoltage"], 3.91)
        self.assertEqual(self.bridge.route_event(message, topic, event), (topic, event))

    def test_binary_wildfi_sensor_payload_is_preserved_as_base64(self) -> None:
        message = types.SimpleNamespace(
            topic="wildfi/tags/WF-003/decoded",
            payload=b"\xff\x00\x88",
            qos=1,
            retain=False,
        )

        topic, key, event = self.bridge.build_event(message)

        self.assertEqual(topic, "raw.sensor")
        self.assertEqual(key, b"WF-003")
        self.assertEqual(event["payload"], {"payload_b64": "/wCI"})
        self.assertEqual(event["source"], "wildfi-mqtt")

    def test_invalid_wildfi_gps_payload_routes_to_dlq(self) -> None:
        message = types.SimpleNamespace(
            topic="wildfi/tags/WF-004/gps",
            payload=json.dumps(
                {
                    "utcTimestamp": 1704067200,
                    "lat": "north",
                    "lon": "east",
                }
            ).encode(),
            qos=1,
            retain=False,
        )

        topic, _key, event = self.bridge.build_event(message)
        routed_topic, routed_event = self.bridge.route_event(message, topic, event)

        self.assertEqual(topic, "raw.gps")
        self.assertEqual(routed_topic, self.bridge.DLQ_TOPIC)
        self.assertEqual(routed_event["intended_topic"], "raw.gps")
        self.assertIn("latitude", "\n".join(routed_event["errors"]))
        self.assertIn("longitude", "\n".join(routed_event["errors"]))


class WildFiDecoderWrapperUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = (REPO_ROOT / "wildfi-decoder-runner" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        self.runner_main = (REPO_ROOT / "wildfi-decoder-runner" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )

    def test_raw_decoder_input_is_forwarded_to_standalone_jar(self) -> None:
        self.assertIn("WILDFI_DECODER_RAW_INPUT", self.runner)
        self.assertIn("unescape_raw_input", self.runner)
        self.assertIn('Command::new("java")', self.runner_main)
        self.assertIn('env_remove("JAVA_TOOL_OPTIONS")', self.runner_main)
        self.assertIn('env_remove("JDK_JAVA_OPTIONS")', self.runner_main)
        self.assertIn("WildFiDecoderStandalone.jar", self.runner)

    def test_batch_decode_modes_send_expected_interactive_answers(self) -> None:
        self.assertIn('"1" | "2"', self.runner)
        self.assertIn("WILDFI_DECODER_BURST_FORM", self.runner)
        self.assertIn("WILDFI_DECODER_FILE_INDEX", self.runner)
        self.assertIn("WILDFI_DECODER_TAG_SELECTION", self.runner)
        self.assertIn("WILDFI_IMU_FREQUENCY", self.runner)
        self.assertIn('"3" | "4" | "5" | "6" | "7" | "8"', self.runner)
        self.assertIn("99", self.runner)

    def test_invalid_decode_mode_fails_with_usage_error(self) -> None:
        self.assertIn("Unsupported WILDFI_DECODER_MODE", self.runner)
        self.assertIn("std::process::exit(64)", self.runner_main)


if __name__ == "__main__":
    unittest.main()
