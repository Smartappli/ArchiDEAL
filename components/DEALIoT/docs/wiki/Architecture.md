# Architecture

DEALIoT is structured as an event-driven IoT platform. Devices and media producers publish to edge interfaces. The platform normalizes events, governs schemas, processes streams and batches, and exposes operational evidence for governance and compliance.

## Logical Flow

```mermaid
flowchart LR
  Device[IoT devices] --> MQTT[MQTT broker]
  Media[Media producers] --> S3[S3-compatible storage]
  MQTT --> Bridge[MQTT-Kafka bridge]
  Bridge --> Kafka[(Kafka)]
  S3 --> Kafka
  Kafka --> Registry[Apicurio Registry]
  Kafka --> Flink[Flink streaming jobs]
  Kafka --> Beam[Beam pipelines]
  Airflow[Airflow] --> S3
  Airflow --> Kafka
  Flink --> State[(Operational state)]
  Prometheus[Prometheus] --> Grafana[Grafana]
  Console[Management Console] --> Airflow
  Console --> Registry
  Console --> Flink
```

## Ingestion

The MQTT-Kafka bridge is packaged as a Rust service. It subscribes through shared MQTT subscriptions so replicas can scale horizontally without duplicate processing. Production MQTT defaults to TLS on port `8883`.

Default topic filters:

- `$share/ingestors/devices/#`
- `$share/ingestors/wildfi/#`

The bridge validates core event contracts through the shared Rust `dealiot-event-contracts` crate and routes invalid payloads to `dlq.events`. The Python `dealiot_contracts` package remains available for pipelines and compatibility tests that need the same topic semantics.

The production bridge runs as a Kubernetes StatefulSet. Each replica keeps a stable MQTT client ID
and a persistent broker session. MQTT acknowledgements are manual and occur only after Kafka has
acknowledged the corresponding record. The producer is idempotent, so its own retries do not create
duplicate Kafka records. A failure after Kafka delivery but before the MQTT acknowledgement can
still replay a record; the contract is deliberately at-least-once rather than exactly-once.

## Kafka And Schemas

Kafka is the durable event backbone. Production clients use `SASL_SSL` by default with SCRAM credentials. Apicurio Registry stores JSON schema artifacts for raw telemetry, media metadata, governance evidence, security evidence, resilience evidence, and legal/compliance evidence.

Core topics:

| Topic | Purpose |
|---|---|
| `raw.sensor` | Generic telemetry and decoded WildFi sensor payloads |
| `raw.gps` | GPS and GNSS events |
| `raw.image2d.meta` | 2D image metadata |
| `raw.image3d.meta` | 3D image metadata |
| `raw.video2d.meta` | 2D video metadata |
| `raw.video3d.meta` | 3D video metadata |
| `media.object.events` | Object storage notifications |
| `features.events` | Derived features |
| `state.latest` | Compacted latest state |
| `dlq.events` | Dead-letter records |

## Processing

Flink owns continuous stateful processing. Checkpoints and savepoints are stored in S3-compatible storage:

- `s3://flink-checkpoints/streaming`
- `s3://flink-savepoints/streaming`
- `s3://flink-ha/streaming`

Airflow owns scheduled orchestration, replay, export, and bounded backfill workflows. Beam images are available for portable pipelines.

Production uses the Flink Kubernetes Operator and makes the checkpointed PyFlink job the sole owner
of `state.latest`. The Rust `stream-normalizer` is a mutually exclusive lightweight mode: it emits
`features.events`, while state output is disabled by default.

The normalizer commits each Kafka source offset synchronously only after both output deliveries
succeed. Its output producer is idempotent. This prevents source-message loss but retains the same
documented at-least-once duplicate window during process failure.

The Rust normalizer's latest-event comparison cache is process-local and is therefore not an
authoritative production state store.

## Production Runtime Model

Production Kubernetes uses:

- Replicas and HPA for horizontally scalable components.
- PDBs to protect availability during voluntary disruption.
- Topology spread constraints to avoid replica concentration on one node.
- Readiness/liveness probes for runtime services.
- Pod Security `restricted` namespace labels.
- Default-deny NetworkPolicies.

Liveness (`/healthz`) means that the process and its health server are running. Readiness
(`/readyz`) is dependency-aware: the bridge waits for an MQTT subscription acknowledgement and the
normalizer verifies Kafka metadata access before becoming ready.

## Deliberate External Dependencies

The production overlay intentionally excludes stateful dependencies. Use managed services or operators for:

- Kafka or Strimzi.
- PostgreSQL or CloudNativePG/Crunchy.
- Redis or managed Redis.
- MQTT or an operator/Helm-managed broker.
- S3-compatible object storage.

This keeps application rollout independent from stateful lifecycle management.
