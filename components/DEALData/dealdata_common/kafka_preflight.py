"""Fail-closed production preflight for the external DEAL Kafka contract."""

from __future__ import annotations

from importlib import import_module
import os
import sys
from typing import Any

from dealdata_common.kafka import csv, env, kafka_security_options


DEFAULT_REQUIRED_TOPICS = (
    "raw.sensor",
    "raw.gps",
    "raw.image2d.meta",
    "raw.image3d.meta",
    "raw.video2d.meta",
    "raw.video3d.meta",
    "dlq.events",
)


def positive_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def required_topics() -> tuple[str, ...]:
    configured = csv(os.getenv("KAFKA_PREFLIGHT_TOPICS", ""))
    topics = tuple(configured) if configured else DEFAULT_REQUIRED_TOPICS
    if len(topics) != len(set(topics)):
        raise ValueError("KAFKA_PREFLIGHT_TOPICS must not contain duplicates")
    return topics


def validate_topic_metadata(
    descriptions: list[dict[str, Any]],
    topics: tuple[str, ...],
    *,
    minimum_partitions: int,
    minimum_replication_factor: int,
    minimum_in_sync_replicas: int,
) -> list[str]:
    """Return all contract violations reported by Kafka metadata."""
    by_topic = {
        str(description.get("topic")): description
        for description in descriptions
        if isinstance(description, dict) and description.get("topic")
    }
    errors: list[str] = []
    for topic in topics:
        description = by_topic.get(topic)
        if description is None:
            errors.append(f"{topic}: topic is missing or cannot be described")
            continue
        error_code = int(description.get("error_code", 0) or 0)
        if error_code:
            errors.append(f"{topic}: Kafka returned error_code={error_code}")
            continue
        partitions = description.get("partitions")
        if not isinstance(partitions, list) or len(partitions) < minimum_partitions:
            count = len(partitions) if isinstance(partitions, list) else 0
            errors.append(
                f"{topic}: partitions={count}, expected at least {minimum_partitions}",
            )
            continue
        for partition in partitions:
            partition_id = partition.get("partition", "unknown")
            replicas = partition.get("replicas")
            in_sync = partition.get("isr")
            replication_factor = len(replicas) if isinstance(replicas, list) else 0
            in_sync_count = len(in_sync) if isinstance(in_sync, list) else 0
            if replication_factor < minimum_replication_factor:
                errors.append(
                    f"{topic}[{partition_id}]: replication_factor="
                    f"{replication_factor}, expected at least "
                    f"{minimum_replication_factor}",
                )
            if in_sync_count < minimum_in_sync_replicas:
                errors.append(
                    f"{topic}[{partition_id}]: in_sync_replicas={in_sync_count}, "
                    f"expected at least {minimum_in_sync_replicas}",
                )
    return errors


def validate_topic_configs(
    configurations: dict[str, Any],
    topics: tuple[str, ...],
    *,
    minimum_in_sync_replicas: int,
) -> list[str]:
    """Validate durable topic settings, not only the current ISR snapshot."""
    topic_configs = configurations.get("topic")
    if not isinstance(topic_configs, dict):
        return ["Kafka did not return topic configuration metadata"]
    errors: list[str] = []
    for topic in topics:
        config = topic_configs.get(topic)
        if not isinstance(config, dict):
            errors.append(f"{topic}: topic configuration is missing")
            continue
        minimum_isr = config.get("min.insync.replicas", {}).get("value")
        try:
            configured_minimum_isr = int(minimum_isr)
        except (TypeError, ValueError):
            errors.append(f"{topic}: min.insync.replicas is missing or invalid")
        else:
            if configured_minimum_isr < minimum_in_sync_replicas:
                errors.append(
                    f"{topic}: min.insync.replicas={configured_minimum_isr}, "
                    f"expected at least {minimum_in_sync_replicas}",
                )
        unclean_election = config.get("unclean.leader.election.enable", {}).get(
            "value",
        )
        if str(unclean_election).strip().lower() != "false":
            errors.append(
                f"{topic}: unclean.leader.election.enable must be false",
            )
    return errors


def run_preflight() -> None:
    topics = required_topics()
    bootstrap_servers = csv(
        env(
            "DEALDATA_KAFKA_BOOTSTRAP_SERVERS",
            "KAFKA_BOOTSTRAP_SERVERS",
        ),
    )
    if len({server.rpartition(":")[0] for server in bootstrap_servers}) < 3:
        raise RuntimeError("Kafka preflight requires at least three distinct brokers")

    kafka_module = import_module("kafka")
    admin = kafka_module.KafkaAdminClient(
        bootstrap_servers=bootstrap_servers,
        client_id="archideal-production-preflight",
        request_timeout_ms=positive_env("KAFKA_PREFLIGHT_TIMEOUT_MS", 15000),
        **kafka_security_options(),
    )
    try:
        descriptions = admin.describe_topics(list(topics))
        kafka_admin_module = import_module("kafka.admin")
        config_resources = [
            kafka_admin_module.ConfigResource(
                kafka_admin_module.ConfigResourceType.TOPIC,
                topic,
            )
            for topic in topics
        ]
        configurations = admin.describe_configs(
            config_resources,
            config_filter="all",
        )
    finally:
        admin.close()

    minimum_in_sync_replicas = positive_env(
        "KAFKA_PREFLIGHT_MIN_IN_SYNC_REPLICAS",
        2,
    )
    errors = validate_topic_metadata(
        descriptions,
        topics,
        minimum_partitions=positive_env("KAFKA_PREFLIGHT_MIN_PARTITIONS", 3),
        minimum_replication_factor=positive_env(
            "KAFKA_PREFLIGHT_MIN_REPLICATION_FACTOR",
            3,
        ),
        minimum_in_sync_replicas=minimum_in_sync_replicas,
    )
    errors.extend(
        validate_topic_configs(
            configurations,
            topics,
            minimum_in_sync_replicas=minimum_in_sync_replicas,
        ),
    )
    if errors:
        raise RuntimeError("Kafka production contract failed:\n- " + "\n- ".join(errors))
    print(
        "Kafka production contract passed for "
        f"{len(topics)} topics across {len(bootstrap_servers)} brokers.",
    )


def main() -> int:
    try:
        run_preflight()
    except Exception as exc:  # noqa: BLE001 - CLI must turn every preflight failure into NO-GO.
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
