from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any, ClassVar, cast
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
FLINK_JOB_PATH = REPO_ROOT / "flink" / "jobs" / "streaming_minimal.py"


def _type_string():
    return "STRING"


def _type_int():
    return "INT"


def _type_boolean():
    return "BOOLEAN"


def _row_named(names, types_):
    return ("ROW_NAMED", tuple(names), tuple(types_))


def _tuple_type(types_):
    return ("TUPLE", tuple(types_))


class _FakeTypes:
    STRING = staticmethod(_type_string)
    INT = staticmethod(_type_int)
    BOOLEAN = staticmethod(_type_boolean)
    ROW_NAMED = staticmethod(_row_named)
    TUPLE = staticmethod(_tuple_type)


def _fake_row(*values):
    return tuple(values)


class _FakeSimpleStringSchema:
    pass


class _FakeSerializationSchema:
    pass


class _FakeWatermarkStrategy:
    @staticmethod
    def no_watermarks():
        return "NO_WATERMARKS"


class _FakeKafkaOffsetResetStrategy:
    EARLIEST = "EARLIEST"
    LATEST = "LATEST"
    NONE = "NONE"


class _FakeKafkaOffsetsInitializer:
    @staticmethod
    def committed_offsets(offset_reset_strategy="NONE"):
        return ("committed_offsets", offset_reset_strategy)


class _FakeKafkaSource:
    def __init__(self, config):
        self.config = config

    @staticmethod
    def builder():
        return _FakeKafkaSourceBuilder()


class _FakeKafkaSourceBuilder:
    def __init__(self):
        self.config: dict[str, Any] = {"properties": {}}

    def set_bootstrap_servers(self, bootstrap_servers):
        self.config["bootstrap_servers"] = bootstrap_servers
        return self

    def set_topics(self, *topics):
        self.config["topics"] = topics
        return self

    def set_group_id(self, group_id):
        self.config["group_id"] = group_id
        return self

    def set_starting_offsets(self, starting_offsets):
        self.config["starting_offsets"] = starting_offsets
        return self

    def set_value_only_deserializer(self, deserialization_schema):
        self.config["deserialization_schema"] = deserialization_schema
        return self

    def set_property(self, key, value):
        self.config["properties"][key] = value
        return self

    def build(self):
        return _FakeKafkaSource(dict(self.config))


class _FakeKafkaRecordSerializationSchema:
    def __init__(self, config):
        self.config = config

    @staticmethod
    def builder():
        return _FakeKafkaRecordSerializationSchemaBuilder()


class _FakeKafkaRecordSerializationSchemaBuilder:
    def __init__(self):
        self.config: dict[str, Any] = {}

    def set_topic(self, topic):
        self.config["topic"] = topic
        return self

    def set_key_serialization_schema(self, schema):
        self.config["key_schema"] = schema
        return self

    def set_value_serialization_schema(self, schema):
        self.config["value_schema"] = schema
        return self

    def build(self):
        return _FakeKafkaRecordSerializationSchema(dict(self.config))


class _FakeKafkaSink:
    def __init__(self, config):
        self.config = config

    @staticmethod
    def builder():
        return _FakeKafkaSinkBuilder()


class _FakeKafkaSinkBuilder:
    def __init__(self):
        self.config: dict[str, Any] = {"properties": {}}

    def set_bootstrap_servers(self, bootstrap_servers):
        self.config["bootstrap_servers"] = bootstrap_servers
        return self

    def set_record_serializer(self, serializer):
        self.config["serializer"] = serializer
        return self

    def set_delivery_guarantee(self, delivery_guarantee):
        self.config["delivery_guarantee"] = delivery_guarantee
        return self

    def set_property(self, key, value):
        self.config["properties"][key] = value
        return self

    def build(self):
        return _FakeKafkaSink(dict(self.config))


class _FakeValueStateDescriptor:
    def __init__(self, name, type_info):
        self.name = name
        self.type_info = type_info


class _FakeState:
    def __init__(self, initial=None):
        self.current = initial
        self.updates: list[Any] = []

    def value(self):
        return self.current

    def update(self, value):
        self.current = value
        self.updates.append(value)


class _FakeRuntimeContext:
    def __init__(self, state):
        self.state = state
        self.descriptor: _FakeValueStateDescriptor | None = None

    def get_state(self, descriptor):
        self.descriptor = descriptor
        return self.state


class _FakeStream:
    def __init__(self, name):
        self.name = name
        self.unions: list[Any] = []
        self.operations: list[Any] = []
        self.sinks: list[Any] = []

    def map(self, mapper, output_type=None):
        self.operations.append(("map", mapper, output_type))
        return self

    def union(self, other):
        self.unions.append(other)
        return self

    def flat_map(self, mapper, output_type=None):
        self.operations.append(("flat_map", mapper, output_type))
        return self

    def filter(self, filter_function, output_type=None):
        self.operations.append(("filter", filter_function, output_type))
        return self

    def key_by(self, key_selector, key_type=None):
        self.operations.append(("key_by", key_selector, key_type))
        return self

    def process(self, processor, output_type=None):
        self.operations.append(("process", processor, output_type))
        return self

    def sink_to(self, sink):
        self.sinks.append(sink)
        self.operations.append(("sink_to", sink))
        return self


class _FakeStreamExecutionEnvironment:
    latest: ClassVar[_FakeStreamExecutionEnvironment | None] = None

    def __init__(self):
        self.runtime_mode = None
        self.parallelism = None
        self.checkpointing = None
        self.sources: list[Any] = []
        self.executions: list[str] = []

    @classmethod
    def get_execution_environment(cls):
        cls.latest = cls()
        return cls.latest

    def set_runtime_mode(self, mode):
        self.runtime_mode = mode

    def set_parallelism(self, parallelism):
        self.parallelism = parallelism

    def enable_checkpointing(self, interval_ms, mode):
        self.checkpointing = (interval_ms, mode)

    def from_source(self, source, watermark_strategy, source_name):
        stream = _FakeStream(source.config["topics"][0])
        self.sources.append((source, stream, watermark_strategy, source_name))
        return stream

    def execute(self, job_name):
        self.executions.append(job_name)
        return "executed"


class _FakeRuntimeExecutionMode:
    STREAMING = "STREAMING"


class _FakeCheckpointingMode:
    EXACTLY_ONCE = "EXACTLY_ONCE"


class _FakeDeliveryGuarantee:
    NONE = "NONE"
    AT_LEAST_ONCE = "AT_LEAST_ONCE"


def _load_streaming_module():
    fake_pyflink = types.ModuleType("pyflink")
    fake_common = types.ModuleType("pyflink.common")
    fake_serialization = types.ModuleType("pyflink.common.serialization")
    fake_watermark_strategy = types.ModuleType("pyflink.common.watermark_strategy")
    fake_datastream = types.ModuleType("pyflink.datastream")
    fake_connectors = types.ModuleType("pyflink.datastream.connectors")
    fake_connectors_base = types.ModuleType("pyflink.datastream.connectors.base")
    fake_kafka = types.ModuleType("pyflink.datastream.connectors.kafka")
    fake_functions = types.ModuleType("pyflink.datastream.functions")
    fake_state = types.ModuleType("pyflink.datastream.state")

    cast("Any", fake_common).Row = _fake_row
    cast("Any", fake_common).Types = _FakeTypes
    cast("Any", fake_serialization).SimpleStringSchema = _FakeSimpleStringSchema
    cast("Any", fake_serialization).SerializationSchema = _FakeSerializationSchema
    cast("Any", fake_watermark_strategy).WatermarkStrategy = _FakeWatermarkStrategy
    cast("Any", fake_datastream).CheckpointingMode = _FakeCheckpointingMode
    cast("Any", fake_datastream).RuntimeExecutionMode = _FakeRuntimeExecutionMode
    cast("Any", fake_datastream).StreamExecutionEnvironment = _FakeStreamExecutionEnvironment
    cast("Any", fake_connectors_base).DeliveryGuarantee = _FakeDeliveryGuarantee
    cast("Any", fake_kafka).KafkaOffsetResetStrategy = _FakeKafkaOffsetResetStrategy
    cast("Any", fake_kafka).KafkaOffsetsInitializer = _FakeKafkaOffsetsInitializer
    cast("Any", fake_kafka).KafkaRecordSerializationSchema = _FakeKafkaRecordSerializationSchema
    cast("Any", fake_kafka).KafkaSink = _FakeKafkaSink
    cast("Any", fake_kafka).KafkaSource = _FakeKafkaSource
    cast("Any", fake_functions).FlatMapFunction = object
    cast("Any", fake_functions).KeyedProcessFunction = object
    cast("Any", fake_functions).RuntimeContext = object
    cast("Any", fake_state).ValueStateDescriptor = _FakeValueStateDescriptor

    with patch.dict(
        sys.modules,
        {
            "pyflink": fake_pyflink,
            "pyflink.common": fake_common,
            "pyflink.common.serialization": fake_serialization,
            "pyflink.common.watermark_strategy": fake_watermark_strategy,
            "pyflink.datastream": fake_datastream,
            "pyflink.datastream.connectors": fake_connectors,
            "pyflink.datastream.connectors.base": fake_connectors_base,
            "pyflink.datastream.connectors.kafka": fake_kafka,
            "pyflink.datastream.functions": fake_functions,
            "pyflink.datastream.state": fake_state,
        },
    ):
        spec = importlib.util.spec_from_file_location(
            "streaming_minimal_under_test", FLINK_JOB_PATH
        )
        if spec is None:
            raise RuntimeError("Unable to load module spec for streaming_minimal.py")
        if spec.loader is None:
            raise RuntimeError("Unable to load streaming_minimal.py module loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class StreamingMinimalUnitTests(unittest.TestCase):
    module: ClassVar[Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_streaming_module()

    def test_env_and_inference_helpers(self) -> None:
        with patch.dict(self.module.os.environ, {"SOME_VALUE": " configured "}, clear=False):
            self.assertEqual(self.module.env_or_default("SOME_VALUE", "fallback"), "configured")

        with patch.dict(self.module.os.environ, {"SOME_VALUE": "   "}, clear=False):
            self.assertEqual(self.module.env_or_default("SOME_VALUE", "fallback"), "fallback")

        self.assertEqual(self.module.infer_entity_id("/tenant/devices/device-1/sensor"), "device-1")
        self.assertEqual(self.module.infer_entity_id("wildfi/tags/WF-001/gps"), "WF-001")
        self.assertEqual(self.module.infer_entity_id("wildfi/WF-002/environment"), "WF-002")
        self.assertEqual(self.module.infer_entity_id("orphan-topic"), "orphan-topic")
        self.assertEqual(self.module.infer_entity_id("/"), "unknown")

        cases = {
            ("raw.sensor", "devices/a/sensor"): "sensor",
            ("raw.gps", "devices/a/gnss/fix"): "gps",
            ("raw.image2d.meta", "devices/a/camera/frame"): "image2d",
            ("raw.image3d.meta", "devices/a/lidar/frame"): "image3d",
            ("raw.video2d.meta", "devices/a/video/frame"): "video2d",
            ("raw.video3d.meta", "devices/a/stereo-video/frame"): "video3d",
            ("other", "devices/a/gnss/fix"): "gps",
            ("other", "devices/a/volumetric-video/frame"): "video3d",
            ("other", "devices/a/camera-stream/frame"): "video2d",
            ("other", "devices/a/pointcloud/frame"): "image3d",
            ("other", "devices/a/image/frame"): "image2d",
            ("other", "devices/a/other"): "unknown",
        }
        for args, expected in cases.items():
            self.assertEqual(self.module.infer_event_kind(*args), expected)

    def test_kafka_client_properties_support_sasl_ssl(self) -> None:
        with patch.dict(
            self.module.os.environ,
            {
                "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
                "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
                "KAFKA_SASL_USERNAME": "flink",
                "KAFKA_SASL_PASSWORD": "secret",
                "KAFKA_SSL_TRUSTSTORE_LOCATION": "/etc/kafka/truststore.p12",
                "KAFKA_SSL_TRUSTSTORE_PASSWORD": "truststore-secret",
                "KAFKA_CLIENT_PROPERTIES": "client.dns.lookup=use_all_dns_ips",
            },
            clear=False,
        ):
            properties = self.module.kafka_client_properties()

        self.assertEqual(properties["security.protocol"], "SASL_SSL")
        self.assertEqual(properties["sasl.mechanism"], "SCRAM-SHA-512")
        self.assertIn('username="flink"', properties["sasl.jaas.config"])
        self.assertIn('password="secret"', properties["sasl.jaas.config"])
        self.assertEqual(properties["ssl.truststore.location"], "/etc/kafka/truststore.p12")
        self.assertEqual(properties["ssl.truststore.password"], "truststore-secret")
        self.assertEqual(properties["client.dns.lookup"], "use_all_dns_ips")

    def test_kafka_client_properties_reject_invalid_and_incomplete_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "key=value syntax"):
            self.module.parse_kafka_client_properties("missing-separator")

        with (
            patch.dict(
                self.module.os.environ,
                {"KAFKA_SECURITY_PROTOCOL": "SASL_SSL"},
                clear=True,
            ),
            self.assertRaisesRegex(
                ValueError,
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD must both be set",
            ),
        ):
            self.module.kafka_client_properties()

    def test_kafka_client_properties_can_disable_ssl_hostname_check(self) -> None:
        with patch.dict(
            self.module.os.environ,
            {
                "KAFKA_SECURITY_PROTOCOL": "SSL",
                "KAFKA_SSL_CHECK_HOSTNAME": "false",
            },
            clear=True,
        ):
            properties = self.module.kafka_client_properties()

        self.assertEqual(properties["ssl.endpoint.identification.algorithm"], "")

    def test_delivery_guarantee_and_offset_strategy_validation(self) -> None:
        with patch.dict(
            self.module.os.environ,
            {"FLINK_KAFKA_DELIVERY_GUARANTEE": "none"},
            clear=False,
        ):
            self.assertEqual(self.module.kafka_delivery_guarantee(), "NONE")

        with (
            patch.dict(
                self.module.os.environ,
                {"FLINK_KAFKA_DELIVERY_GUARANTEE": "invalid"},
                clear=False,
            ),
            self.assertRaisesRegex(ValueError, "must be NONE or AT_LEAST_ONCE"),
        ):
            self.module.kafka_delivery_guarantee()

        self.assertEqual(self.module.kafka_offset_reset_strategy("latest"), "LATEST")
        self.assertEqual(self.module.kafka_offset_reset_strategy("none"), "NONE")
        with self.assertRaisesRegex(ValueError, "earliest, latest, none"):
            self.module.kafka_offset_reset_strategy("invalid")

    def test_normalize_event_flat_map_handles_valid_and_invalid_json(self) -> None:
        normalizer = self.module.NormalizeEvent()
        raw = json.dumps(
            {
                "device_id": "dev-1",
                "event_id": "a" * 64,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "mqtt_topic": "wildfi/tags/ignored/gnss/fix",
                "payload_b64": "abc",
                "qos": "1",
                "retain": True,
            }
        )

        rows = list(normalizer.flat_map(("raw.gps", raw)))

        self.assertEqual(
            rows,
            [
                (
                    "dev-1",
                    "a" * 64,
                    "2026-01-01T00:00:00+00:00",
                    "raw.gps",
                    "wildfi/tags/ignored/gnss/fix",
                    "gps",
                    "abc",
                    1,
                    True,
                    raw,
                )
            ],
        )
        self.assertEqual(normalizer.flat_map(("raw.sensor", "{bad json")), [])
        self.assertEqual(normalizer.flat_map(("raw.sensor", "[]")), [])

    def test_invalid_event_is_serialized_for_the_dlq(self) -> None:
        payload = json.loads(self.module.invalid_event_to_dlq_json(("raw.sensor", "{bad json")))

        self.assertEqual(payload["source"], "flink-streaming-minimal")
        self.assertEqual(payload["intended_topic"], "raw.sensor")
        self.assertEqual(payload["errors"], ["record must be a JSON object"])
        self.assertEqual(payload["raw_event"], {"raw_payload": "{bad json"})

    def test_latest_by_entity_keeps_newer_records_only(self) -> None:
        state = _FakeState("2026-01-01T00:00:00+00:00")
        runtime_context = _FakeRuntimeContext(state)
        processor = self.module.LatestByEntity()
        processor.open(runtime_context)

        old_record = ("dev-1", "a" * 64, "2025-12-31T23:59:59+00:00")
        new_record = ("dev-1", "b" * 64, "2026-01-01T00:00:01+00:00")

        self.assertEqual(list(processor.process_element(old_record, None)), [])
        self.assertEqual(list(processor.process_element(new_record, None)), [new_record])
        self.assertEqual(state.updates, ["2026-01-01T00:00:01+00:00"])
        assert runtime_context.descriptor is not None
        self.assertEqual(runtime_context.descriptor.name, "latest_event_ts")

    def test_build_topic_stream_and_kafka_sink(self) -> None:
        env = _FakeStreamExecutionEnvironment()

        stream = self.module.build_topic_stream(
            env=env,
            bootstrap_servers="kafka:9092",
            group_id="group",
            topic_name="raw.sensor",
        )

        source, _stream, watermark_strategy, source_name = env.sources[0]
        self.assertEqual(source.config["topics"], ("raw.sensor",))
        self.assertEqual(source.config["bootstrap_servers"], "kafka:9092")
        self.assertEqual(source.config["group_id"], "group")
        self.assertEqual(source.config["starting_offsets"], ("committed_offsets", "EARLIEST"))
        self.assertEqual(source.config["properties"]["enable.auto.commit"], "false")
        self.assertEqual(source.config["properties"]["commit.offsets.on.checkpoint"], "true")
        self.assertEqual(source.config["properties"]["security.protocol"], "PLAINTEXT")
        self.assertEqual(watermark_strategy, "NO_WATERMARKS")
        self.assertEqual(source_name, "Kafka Source raw.sensor")
        self.assertEqual(stream.operations[0][0], "map")

        sink = self.module.build_kafka_sink("kafka:9092", "features.events")
        self.assertEqual(sink.config["bootstrap_servers"], "kafka:9092")
        self.assertEqual(sink.config["delivery_guarantee"], "AT_LEAST_ONCE")
        self.assertEqual(sink.config["properties"]["acks"], "all")
        self.assertEqual(sink.config["properties"]["security.protocol"], "PLAINTEXT")
        self.assertEqual(sink.config["serializer"].config["topic"], "features.events")
        self.assertIn("value_schema", sink.config["serializer"].config)
        self.assertNotIn("key_schema", sink.config["serializer"].config)

        value_schema = sink.config["serializer"].config["value_schema"]
        serialized_value = json.loads(
            value_schema.serialize(
                (
                    "dev-1",
                    "event-1",
                    "2026-01-01T00:00:00+00:00",
                    "raw.sensor",
                    "devices/dev-1/sensor",
                    "sensor",
                    "",
                    1,
                    False,
                    "{}",
                )
            )
        )
        self.assertEqual(
            (serialized_value["entity_id"], serialized_value["source_event_id"]),
            ("dev-1", "event-1"),
        )

        keyed_sink = self.module.build_kafka_sink(
            "kafka:9092",
            "state.latest",
            include_key=True,
        )
        self.assertIn("key_schema", keyed_sink.config["serializer"].config)
        key_schema = keyed_sink.config["serializer"].config["key_schema"]
        self.assertEqual(key_schema.serialize(("dev-1", "event-1")), b"dev-1")

    def test_event_to_json_uses_contract_field_names(self) -> None:
        row = (
            "dev-1",
            "a" * 64,
            "2026-01-01T00:00:00+00:00",
            "raw.sensor",
            "devices/dev-1/sensor",
            "sensor",
            "",
            1,
            False,
            '{"temperature_c":21.5}',
        )

        self.assertEqual(
            json.loads(self.module.event_to_json(row)),
            {
                "entity_id": "dev-1",
                "source_event_id": "a" * 64,
                "event_ts": "2026-01-01T00:00:00+00:00",
                "source_topic": "raw.sensor",
                "mqtt_topic": "devices/dev-1/sensor",
                "event_kind": "sensor",
                "payload_b64": "",
                "qos": 1,
                "retain": False,
                "raw_json": '{"temperature_c":21.5}',
            },
        )

    def test_main_configures_streaming_pipeline(self) -> None:
        with patch.dict(
            self.module.os.environ,
            {
                "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
                "FLINK_CONSUMER_GROUP": "group",
                "FLINK_SOURCE_TOPICS": "raw.sensor, raw.gps",
                "FLINK_PARALLELISM": "2",
                "FLINK_CHECKPOINT_INTERVAL_MS": "5000",
                "FEATURES_TOPIC": "features.custom",
                "STATE_TOPIC": "state.custom",
            },
            clear=False,
        ):
            self.module.main()

        env = _FakeStreamExecutionEnvironment.latest
        assert env is not None

        self.assertEqual(env.runtime_mode, "STREAMING")
        self.assertEqual(env.parallelism, 2)
        self.assertEqual(env.checkpointing, (5000, "EXACTLY_ONCE"))
        self.assertEqual(
            [source.config["topics"][0] for source, _stream, _watermark, _name in env.sources],
            ["raw.sensor", "raw.gps"],
        )
        raw_stream = env.sources[0][1]
        self.assertTrue(
            any(
                operation[0] == "sink_to"
                and operation[1].config["serializer"].config["topic"] == "features.custom"
                for operation in raw_stream.operations
            )
        )
        self.assertTrue(
            any(
                operation[0] == "sink_to"
                and operation[1].config["serializer"].config["topic"] == "state.custom"
                for operation in raw_stream.operations
            )
        )
        self.assertTrue(
            any(
                operation[0] == "sink_to"
                and operation[1].config["serializer"].config["topic"] == "dlq.events"
                for operation in raw_stream.operations
            )
        )
        self.assertEqual(env.executions, ["DEALIoT streaming minimal"])


if __name__ == "__main__":
    unittest.main()
