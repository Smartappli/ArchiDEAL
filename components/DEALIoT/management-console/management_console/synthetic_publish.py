"""Publish the bounded production synthetic through MQTT using only the stdlib."""

from __future__ import annotations

import json
import os
import socket
import ssl
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MAX_MQTT_REMAINING_LENGTH = 268_435_455
MAX_UINT16 = 65_535
CONNACK_PACKET_TYPE = 0x20
PUBACK_PACKET_TYPE = 0x40


@dataclass(frozen=True)
class PublisherConfig:
    host: str
    port: int
    username: str
    password: str
    ca_file: str
    device_id: str


def mqtt_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > MAX_UINT16:
        raise ValueError("MQTT strings must contain between 1 and 65535 UTF-8 bytes")
    return struct.pack("!H", len(encoded)) + encoded


def remaining_length(value: int) -> bytes:
    if not 0 <= value <= MAX_MQTT_REMAINING_LENGTH:
        raise ValueError("invalid MQTT remaining length")
    encoded = bytearray()
    while True:
        byte = value % 128
        value //= 128
        if value:
            byte |= 0x80
        encoded.append(byte)
        if not value:
            return bytes(encoded)


def connect_packet(client_id: str, username: str, password: str) -> bytes:
    variable_header = mqtt_string("MQTT") + bytes((4, 0xC2)) + struct.pack("!H", 30)
    payload = mqtt_string(client_id) + mqtt_string(username) + mqtt_string(password)
    body = variable_header + payload
    return bytes((0x10,)) + remaining_length(len(body)) + body


def publish_packet(topic: str, payload: bytes, packet_id: int) -> bytes:
    if not payload:
        raise ValueError("synthetic MQTT payload must not be empty")
    if not 1 <= packet_id <= MAX_UINT16:
        raise ValueError("MQTT packet identifier must be between 1 and 65535")
    body = mqtt_string(topic) + struct.pack("!H", packet_id) + payload
    return bytes((0x32,)) + remaining_length(len(body)) + body


def _receive_exact(connection: ssl.SSLSocket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = connection.recv(length - len(chunks))
        if not chunk:
            raise ConnectionError("MQTT broker closed the TLS connection")
        chunks.extend(chunk)
    return bytes(chunks)


def receive_frame(connection: ssl.SSLSocket) -> tuple[int, bytes]:
    packet_type = _receive_exact(connection, 1)[0]
    multiplier = 1
    length = 0
    for _ in range(4):
        byte = _receive_exact(connection, 1)[0]
        length += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            return packet_type, _receive_exact(connection, length)
        multiplier *= 128
    raise ValueError("malformed MQTT remaining length")


def synthetic_payloads(device_id: str) -> tuple[bytes, bytes]:
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    gps = {
        "message_id": f"{device_id}-gps",
        "timestamp": timestamp,
        "latitude": 50.8503,
        "longitude": 4.3517,
    }
    sensor = {
        "message_id": f"{device_id}-sensor",
        "timestamp": timestamp,
        "sensor_type": "temperature",
        "value": 21.5,
        "unit": "celsius",
    }
    return (
        json.dumps(gps, separators=(",", ":")).encode(),
        json.dumps(sensor, separators=(",", ":")).encode(),
    )


def publish_synthetic(config: PublisherConfig) -> None:
    context = ssl.create_default_context(cafile=config.ca_file)
    client_id = f"archideal-production-smoke-{config.device_id}"[-120:]
    raw_socket = socket.create_connection((config.host, config.port), timeout=10)
    with context.wrap_socket(raw_socket, server_hostname=config.host) as connection:
        connection.settimeout(10)
        connection.sendall(
            connect_packet(client_id, config.username, config.password),
        )
        packet_type, body = receive_frame(connection)
        if packet_type != CONNACK_PACKET_TYPE or body != b"\x00\x00":
            raise RuntimeError("MQTT broker rejected the production synthetic client")

        gps, sensor = synthetic_payloads(config.device_id)
        messages = (
            (f"devices/{config.device_id}/gps", gps, 1),
            (f"devices/{config.device_id}/sensor", sensor, 2),
            (f"devices/{config.device_id}/gps", gps, 3),
        )
        for topic, payload, packet_id in messages:
            connection.sendall(publish_packet(topic, payload, packet_id))
            ack_type, ack_body = receive_frame(connection)
            if ack_type != PUBACK_PACKET_TYPE or ack_body != struct.pack("!H", packet_id):
                raise RuntimeError("MQTT broker did not acknowledge the synthetic publish")
        connection.sendall(b"\xe0\x00")


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        message = f"{name} is required"
        raise RuntimeError(message)
    return value


def main() -> int:
    host = required_environment("MQTT_HOST")
    username = required_environment("MQTT_USERNAME")
    password = required_environment("MQTT_PASSWORD")
    ca_file = required_environment("MQTT_CA_FILE")
    device_id = required_environment("SMOKE_DEVICE_ID")
    port = int(os.environ.get("MQTT_PORT", "8883"))
    if not 1 <= port <= MAX_UINT16:
        raise RuntimeError("MQTT_PORT must be between 1 and 65535")
    if not Path(ca_file).is_file():
        raise RuntimeError("MQTT_CA_FILE must be an existing regular file")
    publish_synthetic(
        PublisherConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            ca_file=ca_file,
            device_id=device_id,
        ),
    )
    print(f"published production MQTT synthetic for {device_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
