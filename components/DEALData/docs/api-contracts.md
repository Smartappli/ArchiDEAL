# DEALData API contracts

This document defines the scientific metadata, WildFi ingestion, and event-listing contracts shared by the Core, GPS, and Sensor services.
Existing endpoints are unversioned; incompatible changes require a documented deprecation and a versioned endpoint.

## Authentication

When `DEALDATA_INGEST_TOKEN` is configured, ingestion requests must send it in the `X-DEALDATA-INGEST-TOKEN` header.
Invalid or missing tokens receive `403 Forbidden`. This token is restricted to ingestion and never authenticates metadata management or event-listing requests.

Metadata management and WildFi event listings use Django REST Framework authentication. A local staff user may use a session or Basic authentication for development. The production edge forwards an OIDC bearer, which every DEALData service introspects without persisting a local user. Introspection fails closed unless the token is active and its issuer, audience, stable subject, and configured top-level group claim are valid.

The OIDC settings are `DEALDATA_OIDC_INTROSPECTION_URL`, `DEALDATA_OIDC_ISSUER`, `DEALDATA_OIDC_AUDIENCE`, `DEALDATA_OIDC_CLIENT_ID`, `DEALDATA_OIDC_CLIENT_SECRET`, `DEALDATA_OIDC_GROUPS_CLAIM`, `DEALDATA_OIDC_READ_GROUPS`, `DEALDATA_OIDC_ADMIN_GROUPS`, and `DEALDATA_OIDC_TIMEOUT_SECONDS`. Read and admin group sets must be non-empty and disjoint. All metadata and event-listing routes documented below require the admin group (`IsAdminUser`); a read-group-only principal cannot access them.

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

## Scientific metadata management

Every route in this section is staff/admin-only:

- `GET` and `POST /api/experiments/`; `GET`, `PATCH`, and `DELETE /api/experiments/{uuid}/`.
  The public fields are `id` (read-only), `project`, and `observed_objects`. Related UUIDs must identify existing Core projects and observed objects.
- `GET` and `POST /api/sensors/`; `GET`, `PATCH`, and `DELETE /api/sensors/{uuid}/`.
  The public fields are `id`, `vendor`, `model`, `code`, `created_at`, and `updated_at`; generated fields are read-only and `code` is unique.
- `GET` and `POST /api/gps-sensors/`; `GET`, `PATCH`, and `DELETE /api/gps-sensors/{uuid}/`.
  The public fields are `id`, `code`, `purchase_date`, `frequency`, `vendor`, `model`, `sim_card`, `active`, `created_at`, and `updated_at`. `code` is unique and `frequency` must be finite and greater than zero.

Sensor and GPS sensor deletion is metadata-safe: it returns `409 Conflict` while measurements, processed positions, or observed-object links still reference the device. Clients must migrate or explicitly remove those related records before retrying; the metadata endpoint never cascades the deletion into scientific observations.

## Event listing

- `GET /api/wildfi/gps/`
- `GET /api/wildfi/sensor/`

Both routes are staff/admin-only; they do not accept the shared ingestion token as read authorization.
Supported shared query parameters are `device_id`, `source`, `topic`, `from`, `to`, `limit`, and `offset`; Sensor adds `sensor_type`.
`from` and `to` must be ISO-8601 timestamps and `from` cannot be later than `to`.
The default limit is 100 and the maximum is 1,000. A malformed query receives `400 Bad Request`.

Passing `summary=true` returns a compact representation and omits raw `payload`, transport `metadata`, hashes, topics, and other detailed fields from the HTTP response. GPS summaries contain `id`, `device_id`, `observed_object_id`, `timestamp`, `latitude`, and `longitude`; Sensor summaries contain `id`, `device_id`, `observed_object_id`, `timestamp`, and `sensor_type`. DEALInterface requests `limit=20&offset=0&summary=true` for its recent read-only panels. Omitting `summary=true` preserves the existing detailed response for authorized administrators.

These contracts manage scientific associations and device metadata. They do not provide map rendering, bulk acquisition/import, or retention/routing configuration. Dataset entries shown by DEALInterface are a DEALHost catalogue contract, not a DEALData storage or event-level authorization contract.

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
