# WildFi ingestion API contract

This document defines the stable contract shared by the GPS and Sensor ingestion services.
Existing endpoints are unversioned; incompatible changes require a documented deprecation and a versioned endpoint.

## Authentication

When `DEALDATA_INGEST_TOKEN` is configured, ingestion requests must send it in the `X-DEALDATA-INGEST-TOKEN` header.
Invalid or missing tokens receive `403 Forbidden`. Read and observability endpoints do not use this shared ingestion token.

## Single-event ingestion

- `POST /api/ingest/wildfi/gps/` accepts one decoded `raw.gps` event.
- `POST /api/ingest/wildfi/sensor/` accepts one decoded `raw.sensor` event.

Every event requires `device_id` and an ISO-8601 `timestamp`. GPS events also require finite latitude and longitude values.
Sensor events require an object as their decoded `payload`.

The canonical success response contains the persisted identifier, device ID, event ID, payload hash, topic, timestamp, and `duplicate`.
Sensor responses also include `sensor_type`.

## Idempotency

The services first identify events using the tuple of `source` and non-empty `event_id`.
If no event ID is supplied, they use a stable SHA-256 payload hash.
The database constraints are the final protection against concurrent workers.

- `201 Created` means the event was persisted.
- `200 OK` with `duplicate: true` means the event was already persisted.
- `400 Bad Request` means the event cannot be validated or stored.

## Batch ingestion

- `POST /api/ingest/wildfi/gps/batch/`
- `POST /api/ingest/wildfi/sensor/batch/`

The request body may be an array or an object containing `events`. A batch is limited to 1,000 events.
The response reports `inserted`, `duplicates`, `errors`, and one result per input index.

- `200 OK` means every item succeeded or was a duplicate.
- `207 Multi-Status` means one or more items failed while other items were processed.
- `400 Bad Request` means the batch envelope itself is invalid.

## Event listing

- `GET /api/wildfi/gps/`
- `GET /api/wildfi/sensor/`

Supported shared query parameters are `device_id`, `source`, `topic`, `from`, `to`, `limit`, and `offset`; Sensor adds `sensor_type`.
`from` and `to` must be ISO-8601 timestamps and `from` cannot be later than `to`.
The default limit is 100 and the maximum is 1,000. A malformed query receives `400 Bad Request`.

## Kafka parity and worker configuration

The `consume_dealiot_kafka` command sends decoded Kafka payloads through the same ingestion functions as HTTP.
This preserves idempotency and validation outcomes across both transports.
Transport-parity tests verify that replaying an HTTP-persisted event through Kafka keeps its identifier and payload hash while reporting a duplicate.
The consumer commits a batch only after every message has been processed; invalid JSON and validation failures are counted as rejected and committed to avoid an infinite retry loop.

Worker configuration requirements:

- At least one bootstrap server is required.
- Topic and consumer group ID must be non-empty.
- `DEALDATA_KAFKA_POLL_TIMEOUT_MS` must be a non-negative integer.
- `DEALDATA_KAFKA_MAX_RECORDS` must be a positive integer.
- `DEALDATA_KAFKA_AUTO_OFFSET_RESET` is one of `earliest`, `latest`, or `none`.
- `DEALDATA_KAFKA_SECURITY_PROTOCOL` is one of `PLAINTEXT`, `SSL`,
  `SASL_PLAINTEXT`, or `SASL_SSL`; production deployments should use
  `SASL_SSL`.
- SASL modes require both `DEALDATA_KAFKA_SASL_USERNAME` and
  `DEALDATA_KAFKA_SASL_PASSWORD`. The mechanism defaults to `SCRAM-SHA-512`
  and can be selected with `DEALDATA_KAFKA_SASL_MECHANISM`.
- SSL modes accept `DEALDATA_KAFKA_SSL_CAFILE` and an optional client identity
  through the paired `DEALDATA_KAFKA_SSL_CERTFILE` and
  `DEALDATA_KAFKA_SSL_KEYFILE` settings. Hostname verification defaults to
  enabled and is controlled by `DEALDATA_KAFKA_SSL_CHECK_HOSTNAME`.

The equivalent unprefixed `KAFKA_*` variables used by DEALIoT are supported as
fallbacks. DEALData-prefixed settings take precedence, allowing the services to
share one Kafka security configuration while retaining explicit overrides.
