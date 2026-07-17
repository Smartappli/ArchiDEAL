from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pyflink.common import Row, Types
from pyflink.common.serialization import SerializationSchema, SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream import (
    CheckpointingMode,
    RuntimeExecutionMode,
    StreamExecutionEnvironment,
)
from pyflink.datastream.connectors.base import DeliveryGuarantee
from pyflink.datastream.connectors.kafka import (
    KafkaOffsetResetStrategy,
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)
from pyflink.datastream.functions import (
    FlatMapFunction,
    KeyedProcessFunction,
    RuntimeContext,
)
from pyflink.datastream.state import ValueStateDescriptor

if TYPE_CHECKING:
    from collections.abc import Iterable

EVENT_FIELDS = (
    "entity_id",
    "source_event_id",
    "event_ts",
    "source_topic",
    "mqtt_topic",
    "event_kind",
    "payload_b64",
    "qos",
    "retain",
    "raw_json",
)

EVENT_TYPE = Types.ROW_NAMED(
    list(EVENT_FIELDS),
    [
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.STRING(),
        Types.INT(),
        Types.BOOLEAN(),
        Types.STRING(),
    ],
)

DEFAULT_SOURCE_TOPICS = (
    "raw.sensor,raw.gps,raw.image2d.meta,raw.image3d.meta,raw.video2d.meta,raw.video3d.meta"
)
DLQ_TOPIC = "dlq.events"
TRUTHY_VALUES = {"1", "true", "yes", "on"}

SOURCE_TOPIC_EVENT_KINDS = {
    "raw.sensor": "sensor",
    "raw.gps": "gps",
    "raw.image2d.meta": "image2d",
    "raw.image3d.meta": "image3d",
    "raw.video2d.meta": "video2d",
    "raw.video3d.meta": "video3d",
}

MQTT_EVENT_KIND_PATTERNS = (
    ("gps", ("gps", "/gnss/")),
    ("video3d", ("video3d", "/stereo-video/", "/volumetric-video/")),
    ("video2d", ("video2d", "/video/", "/camera-stream/")),
    ("image3d", ("image3d", "/lidar/", "/pointcloud/")),
    ("image2d", ("image2d", "/camera/", "/image/")),
)

WILDFI_TOPIC_MARKERS = {"wildfi", "wild-fi"}
WILDFI_TAG_MARKERS = {"devices", "tag", "tags"}
WILDFI_SENSOR_MARKERS = {
    "acc",
    "accelerometer",
    "bme",
    "decoded",
    "environment",
    "gateway",
    "imu",
    "mag",
    "metadata",
    "move",
    "movement",
    "prox",
    "proximity",
    "sensor",
    "telemetry",
}


def env_or_default(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY_VALUES


def parse_kafka_client_properties(value: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for item in value.replace("\n", ",").split(","):
        if not item.strip():
            continue
        key, separator, prop_value = item.partition("=")
        if not separator or not key.strip():
            raise ValueError("KAFKA_CLIENT_PROPERTIES entries must use key=value syntax")
        properties[key.strip()] = prop_value.strip()
    return properties


def kafka_client_properties() -> dict[str, str]:
    security_protocol = env_or_default("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    properties = {"security.protocol": security_protocol}

    if security_protocol.startswith("SASL_"):
        mechanism = env_or_default("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
        username = os.getenv("KAFKA_SASL_USERNAME")
        password = os.getenv("KAFKA_SASL_PASSWORD")
        if not username or not password:
            raise ValueError(
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD must both be set when "
                "Kafka SASL is enabled",
            )
        properties["sasl.mechanism"] = mechanism
        properties["sasl.jaas.config"] = (
            "org.apache.kafka.common.security.scram.ScramLoginModule required "
            f'username="{username}" password="{password}";'
        )

    if "SSL" in security_protocol:
        for env_name, property_name in (
            ("KAFKA_SSL_TRUSTSTORE_LOCATION", "ssl.truststore.location"),
            ("KAFKA_SSL_TRUSTSTORE_PASSWORD", "ssl.truststore.password"),
            ("KAFKA_SSL_KEYSTORE_LOCATION", "ssl.keystore.location"),
            ("KAFKA_SSL_KEYSTORE_PASSWORD", "ssl.keystore.password"),
            ("KAFKA_SSL_KEY_PASSWORD", "ssl.key.password"),
        ):
            value = os.getenv(env_name)
            if value:
                properties[property_name] = value
        if not bool_env("KAFKA_SSL_CHECK_HOSTNAME", default=True):
            properties["ssl.endpoint.identification.algorithm"] = ""

    properties.update(parse_kafka_client_properties(os.getenv("KAFKA_CLIENT_PROPERTIES", "")))
    return properties


def apply_kafka_properties(builder, properties: dict[str, str]):
    for key, value in sorted(properties.items()):
        builder.set_property(key, value)
    return builder


def kafka_delivery_guarantee():
    value = env_or_default("FLINK_KAFKA_DELIVERY_GUARANTEE", "AT_LEAST_ONCE").upper()
    if value == "NONE":
        return DeliveryGuarantee.NONE
    if value == "AT_LEAST_ONCE":
        return DeliveryGuarantee.AT_LEAST_ONCE
    raise ValueError("FLINK_KAFKA_DELIVERY_GUARANTEE must be NONE or AT_LEAST_ONCE")


def kafka_offset_reset_strategy(value: str):
    reset_strategy = value.strip().lower()
    if reset_strategy == "earliest":
        return KafkaOffsetResetStrategy.EARLIEST
    if reset_strategy == "latest":
        return KafkaOffsetResetStrategy.LATEST
    if reset_strategy == "none":
        return KafkaOffsetResetStrategy.NONE

    raise ValueError("KAFKA_AUTO_OFFSET_RESET must be one of: earliest, latest, none")


def _parts(topic: str) -> tuple[list[str], list[str]]:
    parts = [part for part in topic.split("/") if part]
    return parts, [part.lower() for part in parts]


def _part_after_marker(
    parts: list[str],
    lowered_parts: list[str],
    markers: set[str],
) -> str | None:
    for marker in markers:
        if marker in lowered_parts:
            idx = lowered_parts.index(marker)
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return None


def _part_after_wildfi_marker(parts: list[str], lowered_parts: list[str]) -> str | None:
    for marker in WILDFI_TOPIC_MARKERS:
        if marker not in lowered_parts:
            continue

        idx = lowered_parts.index(marker)
        next_idx = idx + 1
        if next_idx < len(parts) and lowered_parts[next_idx] not in WILDFI_SENSOR_MARKERS:
            return parts[next_idx]
        if next_idx + 1 < len(parts):
            return parts[next_idx + 1]

    return None


def infer_entity_id(mqtt_topic: str) -> str:
    parts, lowered_parts = _parts(mqtt_topic)
    marked_id = _part_after_marker(parts, lowered_parts, WILDFI_TAG_MARKERS)
    if marked_id is not None:
        return marked_id

    wildfi_id = _part_after_wildfi_marker(parts, lowered_parts)
    if wildfi_id is not None:
        return wildfi_id

    if parts:
        return parts[-1]

    return "unknown"


def infer_event_kind(source_topic: str, mqtt_topic: str) -> str:
    source_event_kind = SOURCE_TOPIC_EVENT_KINDS.get(source_topic.lower())
    if source_event_kind is not None:
        return source_event_kind

    lowered_mqtt = mqtt_topic.lower()

    for event_kind, patterns in MQTT_EVENT_KIND_PATTERNS:
        if any(pattern in lowered_mqtt for pattern in patterns):
            return event_kind

    return "unknown"


class NormalizeEvent(FlatMapFunction):
    def flat_map(self, value) -> Iterable[Row]:
        source_topic, raw_value = value

        record = parse_json_record(raw_value)
        if record is None:
            return []

        mqtt_topic = str(record.get("mqtt_topic", ""))
        entity_id = str(record.get("device_id") or infer_entity_id(mqtt_topic))
        event_ts = str(record.get("timestamp") or record.get("ingested_at") or "")
        event_kind = infer_event_kind(source_topic, mqtt_topic)

        payload_b64 = str(record.get("payload_b64", ""))
        qos = int(record.get("qos", 0) or 0)
        retain = bool(record.get("retain", False))

        return [
            Row(
                entity_id,
                str(record.get("event_id", "")),
                event_ts,
                source_topic,
                mqtt_topic,
                event_kind,
                payload_b64,
                qos,
                retain,
                raw_value,
            )
        ]


def parse_json_record(raw_value: str) -> dict[str, object] | None:
    try:
        record = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def invalid_event_to_dlq_json(value: tuple[str, str]) -> str:
    source_topic, raw_value = value
    return json.dumps(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "flink-streaming-minimal",
            "intended_topic": source_topic,
            "source_topic": source_topic,
            "device_id": "unknown",
            "errors": ["record must be a JSON object"],
            "raw_event": {"raw_payload": raw_value},
        },
        separators=(",", ":"),
    )


class LatestByEntity(KeyedProcessFunction):
    def open(self, runtime_context: RuntimeContext):
        self.latest_ts_state = runtime_context.get_state(
            ValueStateDescriptor("latest_event_ts", Types.STRING())
        )

    def process_element(self, value, ctx):
        current = self.latest_ts_state.value()
        incoming_ts = value[2]

        if current is None or incoming_ts >= current:
            self.latest_ts_state.update(incoming_ts)
            yield value


def build_topic_stream(
    env: StreamExecutionEnvironment,
    bootstrap_servers: str,
    group_id: str,
    topic_name: str,
    kafka_properties: dict[str, str] | None = None,
):
    source_builder = (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_topics(topic_name)
        .set_group_id(group_id)
        .set_starting_offsets(
            KafkaOffsetsInitializer.committed_offsets(
                kafka_offset_reset_strategy(env_or_default("KAFKA_AUTO_OFFSET_RESET", "earliest"))
            )
        )
        .set_value_only_deserializer(SimpleStringSchema())
        .set_property("enable.auto.commit", "false")
        .set_property("commit.offsets.on.checkpoint", "true")
    )
    source = apply_kafka_properties(
        source_builder, kafka_properties or kafka_client_properties()
    ).build()

    return env.from_source(
        source,
        WatermarkStrategy.no_watermarks(),
        f"Kafka Source {topic_name}",
    ).map(
        lambda raw: (topic_name, raw),
        output_type=Types.TUPLE([Types.STRING(), Types.STRING()]),
    )


def event_to_json(row) -> str:
    return json.dumps(
        {field_name: row[index] for index, field_name in enumerate(EVENT_FIELDS)},
        separators=(",", ":"),
    )


class EventValueSerializationSchema(SerializationSchema):
    def serialize(self, row) -> bytes:
        return event_to_json(row).encode("utf-8")


class EntityKeySerializationSchema(SerializationSchema):
    def serialize(self, row) -> bytes:
        return str(row[0]).encode("utf-8")


def build_kafka_sink(
    bootstrap_servers: str,
    topic_name: str,
    *,
    include_key: bool = False,
    kafka_properties: dict[str, str] | None = None,
):
    serializer_builder = (
        KafkaRecordSerializationSchema.builder()
        .set_topic(topic_name)
        .set_value_serialization_schema(EventValueSerializationSchema())
    )
    if include_key:
        serializer_builder.set_key_serialization_schema(EntityKeySerializationSchema())

    sink_builder = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(serializer_builder.build())
        .set_delivery_guarantee(kafka_delivery_guarantee())
        .set_property("acks", "all")
    )
    return apply_kafka_properties(
        sink_builder, kafka_properties or kafka_client_properties()
    ).build()


def build_string_kafka_sink(
    bootstrap_servers: str,
    topic_name: str,
    *,
    kafka_properties: dict[str, str] | None = None,
):
    serializer = (
        KafkaRecordSerializationSchema.builder()
        .set_topic(topic_name)
        .set_value_serialization_schema(SimpleStringSchema())
        .build()
    )
    sink_builder = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(serializer)
        .set_delivery_guarantee(kafka_delivery_guarantee())
        .set_property("acks", "all")
    )
    return apply_kafka_properties(
        sink_builder, kafka_properties or kafka_client_properties()
    ).build()


def main():
    bootstrap_servers = env_or_default(
        "KAFKA_BOOTSTRAP_SERVERS",
        "kafka1:9092,kafka2:9092,kafka3:9092",
    )
    consumer_group = env_or_default(
        "FLINK_CONSUMER_GROUP",
        "flink-streaming-minimal-v1",
    )
    source_topics = [
        topic.strip()
        for topic in env_or_default(
            "FLINK_SOURCE_TOPICS",
            DEFAULT_SOURCE_TOPICS,
        ).split(",")
        if topic.strip()
    ]
    kafka_properties = kafka_client_properties()

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(int(env_or_default("FLINK_PARALLELISM", "4")))
    env.enable_checkpointing(
        int(env_or_default("FLINK_CHECKPOINT_INTERVAL_MS", "10000")),
        CheckpointingMode.EXACTLY_ONCE,
    )

    topic_streams = [
        build_topic_stream(
            env=env,
            bootstrap_servers=bootstrap_servers,
            group_id=consumer_group,
            topic_name=topic,
            kafka_properties=kafka_properties,
        )
        for topic in source_topics
    ]

    if not topic_streams:
        raise RuntimeError("No source topics configured in FLINK_SOURCE_TOPICS")

    raw_stream = topic_streams[0]
    for stream in topic_streams[1:]:
        raw_stream = raw_stream.union(stream)

    normalized = raw_stream.flat_map(NormalizeEvent(), output_type=EVENT_TYPE)
    raw_stream.filter(
        lambda value: parse_json_record(value[1]) is None,
        output_type=Types.TUPLE([Types.STRING(), Types.STRING()]),
    ).map(
        invalid_event_to_dlq_json,
        output_type=Types.STRING(),
    ).sink_to(
        build_string_kafka_sink(
            bootstrap_servers,
            env_or_default("DLQ_TOPIC", DLQ_TOPIC),
            kafka_properties=kafka_properties,
        )
    )

    latest = normalized.key_by(
        lambda row: row[0],
        key_type=Types.STRING(),
    ).process(
        LatestByEntity(),
        output_type=EVENT_TYPE,
    )

    normalized.sink_to(
        build_kafka_sink(
            bootstrap_servers,
            env_or_default("FEATURES_TOPIC", "features.events"),
            kafka_properties=kafka_properties,
        )
    )

    latest.sink_to(
        build_kafka_sink(
            bootstrap_servers,
            env_or_default("STATE_TOPIC", "state.latest"),
            include_key=True,
            kafka_properties=kafka_properties,
        )
    )

    env.execute("DEALIoT streaming minimal")


if __name__ == "__main__":
    main()
