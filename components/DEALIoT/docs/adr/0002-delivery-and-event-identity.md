# ADR 0002: Delivery and event identity

- Status: accepted
- Date: 2026-07-10

## Context

MQTT-to-Kafka and Kafka-to-derived-topic delivery is at-least-once. A process can stop after a
downstream write succeeds but before its source acknowledgement is durable.

## Decision

All new raw events use envelope version `1` and carry a deterministic `event_id`, `schema_version`,
`occurred_at`, `ingested_at`, `source`, and `device_id`.

For MQTT ingestion, `event_id` is a SHA-256 digest of the source identity, MQTT topic, and raw
payload. Event time normally remains part of the raw payload, while omitting the ingestion clock
from the digest keeps broker redelivery stable.

Kafka producers remain idempotent and source acknowledgements occur only after downstream delivery.
Consumers must deduplicate by `event_id` where side effects are not naturally idempotent.

## Consequences

- The platform guarantees at-least-once delivery, not global exactly-once processing.
- Contract evolution is governed by versioned JSON Schemas and backward-transitive compatibility.
- Historical events without the envelope remain readable during the migration window.
