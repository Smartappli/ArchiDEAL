"""Shared Kafka consumer command support."""

from __future__ import annotations

from argparse import ArgumentTypeError
from importlib import import_module
import json
import os
from typing import Any, Callable

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection
from rest_framework import status

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
    except UnicodeDecodeError, json.JSONDecodeError:
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
            "--once",
            action="store_true",
            help="Poll once, process available records, then exit.",
        )

    def handle(self, *args, **options) -> None:
        del args
        consumer = self._build_consumer(options)
        self.stdout.write(
            f"Consuming DEALIoT {self.event_label} events "
            f"topic={options['topic']} group_id={options['group_id']}",
        )

        try:
            self._consume_batches(consumer, options)
        finally:
            consumer.close()

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

    def _consume_batches(self, consumer, options) -> None:
        while True:
            records = consumer.poll(
                timeout_ms=options["poll_timeout_ms"],
                max_records=options["max_records"],
            )
            if not records:
                if options["once"]:
                    return
                continue

            counts = self._process_records(records)
            consumer.commit()
            self.stdout.write(
                f"Processed DEALIoT {self.event_label} Kafka batch "
                f"inserted={counts['inserted']} "
                f"duplicates={counts['duplicates']} "
                f"rejected={counts['rejected']}",
            )
            if options["once"]:
                return

    def _process_records(self, records) -> dict[str, int]:
        counts = {"inserted": 0, "duplicates": 0, "rejected": 0}
        for message in iter_messages(records):
            counts[self._process_message(message)] += 1
        return counts

    def _process_message(self, message) -> str:
        payload = decode_json(message.value)
        if payload is None:
            self._write_rejected_json(message)
            return "rejected"

        close_stale_connections()
        body, response_status = self.ingest_event(payload)
        if response_status == status.HTTP_201_CREATED:
            return "inserted"
        if response_status == status.HTTP_200_OK and body.get("duplicate"):
            return "duplicates"
        if response_status == status.HTTP_400_BAD_REQUEST:
            self.stderr.write(
                f"Rejected DEALIoT {self.event_label} event "
                f"offset={message.offset} detail={body.get('detail')}",
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
        "event_label": event_label,
        "ingest_event": staticmethod(ingest_event),
    }
    return type("Command", (DealIotKafkaCommand,), command_attrs)
