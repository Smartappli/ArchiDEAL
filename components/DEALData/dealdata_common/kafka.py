"""Shared Kafka consumer command support."""

from __future__ import annotations

from argparse import ArgumentTypeError
from importlib import import_module
import json
import os
import time
from typing import Any, Callable

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections, connection
from rest_framework import status

from dealdata_common.consumer_observability import (
    ConsumerMetrics,
    positive_float,
    positive_float_env,
    start_consumer_metrics_server,
)

KafkaIngestEvent = Callable[[dict[str, Any]], tuple[dict[str, Any], int]]

KAFKA_SECURITY_PROTOCOLS = {
    "PLAINTEXT",
    "SSL",
    "SASL_PLAINTEXT",
    "SASL_SSL",
}
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off"}


def env(*names: str, default: str = "") -> str:
    """Return the first populated environment variable from the given names."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def csv(value: str) -> list[str]:
    """Split a comma-separated setting into non-empty trimmed values."""
    return [item.strip() for item in value.split(",") if item.strip()]


def boolean_env(*names: str, default: bool) -> bool:
    """Read a strict boolean from the first populated environment variable."""
    value = env(*names)
    if not value:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_ENV_VALUES:
        return True
    if normalized in FALSE_ENV_VALUES:
        return False
    raise CommandError(
        f"{names[0]} must be one of: true, false, 1, 0, yes, no, on, or off.",
    )


def kafka_security_options() -> dict[str, Any]:
    """Build kafka-python security options from DEALData or shared Kafka env."""
    security_protocol = (
        env(
            "DEALDATA_KAFKA_SECURITY_PROTOCOL",
            "KAFKA_SECURITY_PROTOCOL",
            default="PLAINTEXT",
        )
        .strip()
        .upper()
    )
    if security_protocol not in KAFKA_SECURITY_PROTOCOLS:
        supported = ", ".join(sorted(KAFKA_SECURITY_PROTOCOLS))
        raise CommandError(
            f"DEALDATA_KAFKA_SECURITY_PROTOCOL must be one of: {supported}.",
        )

    options: dict[str, Any] = {"security_protocol": security_protocol}
    if security_protocol.startswith("SASL_"):
        username = env(
            "DEALDATA_KAFKA_SASL_USERNAME",
            "KAFKA_SASL_USERNAME",
        )
        password = env(
            "DEALDATA_KAFKA_SASL_PASSWORD",
            "KAFKA_SASL_PASSWORD",
        )
        if not username or not password:
            raise CommandError(
                "DEALDATA_KAFKA_SASL_USERNAME and "
                "DEALDATA_KAFKA_SASL_PASSWORD must both be set when Kafka SASL "
                "is enabled.",
            )
        options.update(
            sasl_mechanism=env(
                "DEALDATA_KAFKA_SASL_MECHANISM",
                "KAFKA_SASL_MECHANISM",
                default="SCRAM-SHA-512",
            ).strip(),
            sasl_plain_username=username,
            sasl_plain_password=password,
        )

    if "SSL" in security_protocol:
        ssl_cafile = env(
            "DEALDATA_KAFKA_SSL_CAFILE",
            "DEALDATA_KAFKA_SSL_CA_FILE",
            "KAFKA_SSL_CAFILE",
            "KAFKA_SSL_CA_FILE",
        )
        ssl_certfile = env(
            "DEALDATA_KAFKA_SSL_CERTFILE",
            "DEALDATA_KAFKA_SSL_CERT_FILE",
            "KAFKA_SSL_CERTFILE",
            "KAFKA_SSL_CERT_FILE",
        )
        ssl_keyfile = env(
            "DEALDATA_KAFKA_SSL_KEYFILE",
            "DEALDATA_KAFKA_SSL_KEY_FILE",
            "KAFKA_SSL_KEYFILE",
            "KAFKA_SSL_KEY_FILE",
        )
        if bool(ssl_certfile) != bool(ssl_keyfile):
            raise CommandError(
                "DEALDATA_KAFKA_SSL_CERTFILE and DEALDATA_KAFKA_SSL_KEYFILE "
                "must both be set when Kafka mutual TLS is enabled.",
            )
        if ssl_cafile:
            options["ssl_cafile"] = ssl_cafile
        if ssl_certfile:
            options["ssl_certfile"] = ssl_certfile
            options["ssl_keyfile"] = ssl_keyfile
        options["ssl_check_hostname"] = boolean_env(
            "DEALDATA_KAFKA_SSL_CHECK_HOSTNAME",
            "KAFKA_SSL_CHECK_HOSTNAME",
            default=True,
        )

    return options


def non_negative_int(value: str) -> int:
    """Parse a non-negative integer command-line option."""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ArgumentTypeError("Expected a non-negative integer.") from exc
    if parsed < 0:
        raise ArgumentTypeError("Expected a non-negative integer.")
    return parsed


def positive_int(value: str) -> int:
    """Parse a strictly positive integer command-line option."""
    parsed = non_negative_int(value)
    if parsed == 0:
        raise ArgumentTypeError("Expected a positive integer.")
    return parsed


def decode_json(value: bytes) -> dict[str, Any] | None:
    """Decode a Kafka message value into a JSON object payload."""
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def close_stale_connections() -> None:
    """Close stale DB connections without breaking transactional test wrappers."""
    if not connection.in_atomic_block:
        close_old_connections()


def load_kafka_consumer():
    """Import and return kafka-python's consumer class."""
    try:
        kafka_module = import_module("kafka")
    except ImportError as exc:
        raise CommandError(
            "kafka-python is required to consume DEALIoT Kafka topics.",
        ) from exc
    return kafka_module.KafkaConsumer


def iter_messages(records):
    """Yield Kafka messages from the records mapping returned by poll()."""
    for messages in records.values():
        yield from messages


class DealIotKafkaCommand(BaseCommand):
    """Base command for persisting DEALIoT Kafka batches."""

    bootstrap_servers_env = ""
    topic_env = ""
    group_id_env = ""
    auto_offset_reset_env = ""
    default_topic = ""
    default_group_id = ""
    service_key = ""
    event_label = ""
    ingest_event: KafkaIngestEvent

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--bootstrap-servers",
            default=env(
                self.bootstrap_servers_env,
                "DEALDATA_KAFKA_BOOTSTRAP_SERVERS",
                "KAFKA_BOOTSTRAP_SERVERS",
                default="kafka1:9092,kafka2:9092,kafka3:9092",
            ),
        )
        parser.add_argument(
            "--topic",
            default=env(self.topic_env, default=self.default_topic),
        )
        parser.add_argument(
            "--group-id",
            default=env(self.group_id_env, default=self.default_group_id),
        )
        parser.add_argument(
            "--auto-offset-reset",
            choices=["earliest", "latest", "none"],
            default=env(
                self.auto_offset_reset_env,
                "DEALDATA_KAFKA_AUTO_OFFSET_RESET",
                default="earliest",
            ),
        )
        parser.add_argument(
            "--poll-timeout-ms",
            type=non_negative_int,
            default=env("DEALDATA_KAFKA_POLL_TIMEOUT_MS", default="1000"),
        )
        parser.add_argument(
            "--max-records",
            type=positive_int,
            default=env("DEALDATA_KAFKA_MAX_RECORDS", default="100"),
        )
        parser.add_argument(
            "--database-check-interval-seconds",
            type=positive_float,
            default=positive_float_env(
                "DEALDATA_CONSUMER_DATABASE_CHECK_INTERVAL_SECONDS",
                15.0,
            ),
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Poll once, process available records, then exit.",
        )

    def handle(self, *args, **options) -> None:
        del args
        metrics, metrics_server = start_consumer_metrics_server(self.service_key)
        consumer = None
        self.stdout.write(
            f"Consuming DEALIoT {self.event_label} events "
            f"topic={options['topic']} group_id={options['group_id']}",
        )

        try:
            consumer = self._build_consumer(options)
            self._consume_batches(consumer, options, metrics)
        finally:
            metrics.mark_not_ready()
            try:
                if consumer is not None:
                    consumer.close()
            finally:
                metrics_server.stop()

    @staticmethod
    def _build_consumer(options):
        bootstrap_servers = csv(options["bootstrap_servers"])
        if not bootstrap_servers:
            raise CommandError("At least one Kafka bootstrap server is required.")
        topic = options["topic"].strip()
        if not topic:
            raise CommandError("A Kafka topic is required.")
        group_id = options["group_id"].strip()
        if not group_id:
            raise CommandError("A Kafka group ID is required.")

        kafka_consumer = load_kafka_consumer()
        return kafka_consumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset=options["auto_offset_reset"],
            **kafka_security_options(),
        )

    def _consume_batches(
        self,
        consumer,
        options,
        metrics: ConsumerMetrics,
    ) -> None:
        database_ready = False
        next_database_check = 0.0
        while True:
            now = time.monotonic()
            if now >= next_database_check:
                database_ready = self._database_is_ready(metrics)
                next_database_check = now + options["database_check_interval_seconds"]
            try:
                records = consumer.poll(
                    timeout_ms=options["poll_timeout_ms"],
                    max_records=options["max_records"],
                )
            except Exception:
                metrics.record_poll_error()
                raise
            metrics.record_poll(
                kafka_assigned=self._has_partition_assignment(consumer),
                database_ready=database_ready,
            )
            if not records:
                if options["once"]:
                    return
                continue

            counts = self._process_records(records, metrics)
            try:
                consumer.commit()
            except Exception:
                metrics.record_commit("failure")
                raise
            metrics.record_commit("success")
            self.stdout.write(
                f"Processed DEALIoT {self.event_label} Kafka batch "
                f"inserted={counts['inserted']} "
                f"duplicates={counts['duplicates']} "
                f"rejected={counts['rejected']}",
            )
            if options["once"]:
                return

    @staticmethod
    def _has_partition_assignment(consumer) -> bool:
        assignment = getattr(consumer, "assignment", None)
        if not callable(assignment):
            # Lightweight test doubles and older integrations do not expose
            # assignment(); a successful poll remains the best available signal.
            return True
        return bool(assignment())

    @staticmethod
    def _database_is_ready(metrics: ConsumerMetrics) -> bool:
        try:
            close_stale_connections()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            metrics.record_database_error()
            return False
        return True

    def _process_records(
        self,
        records,
        metrics: ConsumerMetrics,
    ) -> dict[str, int]:
        counts = {"inserted": 0, "duplicates": 0, "rejected": 0}
        for message in iter_messages(records):
            counts[self._process_message(message, metrics)] += 1
        return counts

    def _process_message(self, message, metrics: ConsumerMetrics) -> str:
        started_at = time.perf_counter()
        payload = decode_json(message.value)
        if payload is None:
            self._write_rejected_json(message)
            metrics.record_event(
                "rejected",
                payload=None,
                persistence_duration_seconds=time.perf_counter() - started_at,
            )
            return "rejected"

        close_stale_connections()
        try:
            body, response_status = self.ingest_event(payload)
        except DatabaseError:
            metrics.record_database_error()
            raise
        if response_status == status.HTTP_201_CREATED:
            metrics.record_event(
                "inserted",
                payload=payload,
                persistence_duration_seconds=time.perf_counter() - started_at,
            )
            return "inserted"
        if response_status == status.HTTP_200_OK and body.get("duplicate"):
            metrics.record_event(
                "duplicate",
                payload=payload,
                persistence_duration_seconds=time.perf_counter() - started_at,
            )
            return "duplicates"
        if response_status == status.HTTP_400_BAD_REQUEST:
            self.stderr.write(
                f"Rejected DEALIoT {self.event_label} event "
                f"offset={message.offset} detail={body.get('detail')}",
            )
            metrics.record_event(
                "rejected",
                payload=payload,
                persistence_duration_seconds=time.perf_counter() - started_at,
            )
            return "rejected"

        raise CommandError(
            f"Unexpected {self.event_label} ingestion response "
            f"status={response_status} body={body}",
        )

    def _write_rejected_json(self, message) -> None:
        self.stderr.write(
            "Rejected non-object or invalid JSON Kafka message "
            f"topic={message.topic} partition={message.partition} "
            f"offset={message.offset}",
        )


def build_dealiot_kafka_command(
    *,
    service_key: str,
    event_label: str,
    model_path: str,
    ingest_event: KafkaIngestEvent,
):
    """Create a Django management command for one DEALIoT event stream."""
    service_env = service_key.upper()
    help_text = f"Consume DEALIoT Kafka raw.{service_key} events into {model_path}."
    bootstrap_servers_env = f"DEALDATA_{service_env}_KAFKA_BOOTSTRAP_SERVERS"
    auto_offset_reset_env = f"DEALDATA_{service_env}_KAFKA_AUTO_OFFSET_RESET"
    command_attrs = {
        "help": help_text,
        "bootstrap_servers_env": bootstrap_servers_env,
        "topic_env": f"DEALDATA_{service_env}_KAFKA_TOPIC",
        "group_id_env": f"DEALDATA_{service_env}_KAFKA_GROUP_ID",
        "auto_offset_reset_env": auto_offset_reset_env,
        "default_topic": f"raw.{service_key}",
        "default_group_id": f"dealdata-{service_key}-ingest",
        "service_key": service_key,
        "event_label": event_label,
        "ingest_event": staticmethod(ingest_event),
    }
    return type("Command", (DealIotKafkaCommand,), command_attrs)
