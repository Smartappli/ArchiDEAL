from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console import synthetic_publish  # noqa: E402


class _ChunkedConnection:
    def __init__(self, payload: bytes) -> None:
        self.payload = bytearray(payload)

    def recv(self, length: int) -> bytes:
        if not self.payload:
            return b""
        chunk_length = min(1, length, len(self.payload))
        chunk = bytes(self.payload[:chunk_length])
        del self.payload[:chunk_length]
        return chunk


class SyntheticPublishTests(unittest.TestCase):
    def test_connect_packet_uses_mqtt311_tls_credentials_without_leaking_them(self) -> None:
        packet = synthetic_publish.connect_packet("client-1", "smoke-user", "secret")

        self.assertEqual(packet[0], 0x10)
        self.assertIn(b"\x00\x04MQTT\x04\xc2", packet)
        self.assertTrue(packet.endswith(b"\x00\x06secret"))

    def test_qos_one_publish_packet_contains_topic_identifier_and_payload(self) -> None:
        packet = synthetic_publish.publish_packet(
            "devices/device-1/gps",
            b'{"message_id":"gps-1"}',
            42,
        )

        self.assertEqual(packet[0], 0x32)
        self.assertIn(b"devices/device-1/gps", packet)
        self.assertIn(struct.pack("!H", 42), packet)
        self.assertTrue(packet.endswith(b'{"message_id":"gps-1"}'))

    def test_frame_reader_handles_fragmented_puback(self) -> None:
        packet_type, payload = synthetic_publish.receive_frame(
            _ChunkedConnection(b"\x40\x02\x00\x2a")
        )

        self.assertEqual(packet_type, 0x40)
        self.assertEqual(payload, b"\x00\x2a")

    def test_payload_replay_has_stable_identity_and_distinct_sensor_identity(self) -> None:
        gps, sensor = synthetic_publish.synthetic_payloads("archideal-smoke-release-1")
        gps_payload = json.loads(gps)
        sensor_payload = json.loads(sensor)

        self.assertEqual(gps_payload["message_id"], "archideal-smoke-release-1-gps")
        self.assertEqual(
            sensor_payload["message_id"],
            "archideal-smoke-release-1-sensor",
        )
        self.assertEqual(gps_payload["timestamp"], sensor_payload["timestamp"])

    def test_publisher_explicitly_requires_tls_twelve_or_newer(self) -> None:
        context = MagicMock()
        connection = context.wrap_socket.return_value.__enter__.return_value
        acknowledgements = [
            (synthetic_publish.CONNACK_PACKET_TYPE, b"\x00\x00"),
            *[
                (
                    synthetic_publish.PUBACK_PACKET_TYPE,
                    struct.pack("!H", packet_id),
                )
                for packet_id in (1, 2, 3)
            ],
        ]
        config = synthetic_publish.PublisherConfig(
            host="mqtt.example.com",
            port=8883,
            username="smoke-user",
            password="secret",  # noqa: S106 - synthetic test credential.
            ca_file="/var/run/archideal-ca/mqtt-ca.crt",
            device_id="smoke-1",
        )

        with (
            patch.object(
                synthetic_publish.ssl,
                "create_default_context",
                return_value=context,
            ),
            patch.object(synthetic_publish.socket, "create_connection"),
            patch.object(
                synthetic_publish,
                "receive_frame",
                side_effect=acknowledgements,
            ),
        ):
            synthetic_publish.publish_synthetic(config)

        self.assertEqual(
            context.minimum_version,
            synthetic_publish.ssl.TLSVersion.TLSv1_2,
        )
        context.wrap_socket.assert_called_once_with(
            ANY,
            server_hostname="mqtt.example.com",
        )
        self.assertEqual(connection.sendall.call_count, 5)


if __name__ == "__main__":
    unittest.main()
