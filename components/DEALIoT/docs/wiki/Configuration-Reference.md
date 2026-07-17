# Configuration Reference

## Runtime ConfigMap

Production runtime config is generated from `deploy/kubernetes/overlays/production/runtime-config.production.example.env`.

| Variable | Purpose | Production default |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka bootstrap endpoints | Replace with private broker list |
| `KAFKA_SECURITY_PROTOCOL` | Kafka client security protocol | `SASL_SSL` |
| `KAFKA_SASL_MECHANISM` | Kafka SASL mechanism | `SCRAM-SHA-512` |
| `KAFKA_SASL_USERNAME` | Kafka SASL username | `dealiot_runtime` |
| `KAFKA_SSL_CHECK_HOSTNAME` | Hostname verification | `true` |
| `MQTT_HOST` | MQTT broker host | Replace with private endpoint |
| `MQTT_PORT` | MQTT broker port | `8883` |
| `MQTT_TLS_ENABLED` | MQTT TLS toggle | `true` |
| `MQTT_CLIENT_ID` | Stable MQTT session identity | Injected from the Kubernetes pod or Swarm task slot |
| `MQTT_CLEAN_SESSION` | Discard broker session on disconnect | `false` |
| `MQTT_TOPICS` | MQTT subscriptions | devices and WildFi shared subscriptions |
| `MQTT_USERNAME` | MQTT username | `dealiot_ingestor` |
| `S3_ENDPOINT_URL` | S3 endpoint | Replace with private TLS endpoint |
| `FLINK_PARALLELISM` | Default stream parallelism | `4` |
| `FLINK_TASK_SLOTS` | Task slots per TaskManager | `4` |
| `DEFAULT_KAFKA_TOPIC` | Bridge fallback topic | `raw.sensor` |
| `LOG_LEVEL` | Runtime log level | `INFO` |

## Secret Contract

Secrets are documented in `deploy/kubernetes/overlays/production/dealiot-secrets.example.env` and enforced through `external-dependency-contract.yaml`.

Do not commit real secret values. Do not render `SET_FROM_SECRET_MANAGER` into production manifests.

## Kafka Client Security

Python producers and PyFlink jobs share the same Kafka security environment model:

- `KAFKA_SECURITY_PROTOCOL`
- `KAFKA_SASL_MECHANISM`
- `KAFKA_SASL_USERNAME`
- `KAFKA_SASL_PASSWORD`
- `KAFKA_SSL_CA_FILE`
- `KAFKA_SSL_CERT_FILE`
- `KAFKA_SSL_KEY_FILE`
- `KAFKA_SSL_CHECK_HOSTNAME`

For Swarm, the bridge reads `KAFKA_SASL_PASSWORD_FILE` from Docker secrets.

## MQTT TLS

The bridge supports:

- `MQTT_TLS_ENABLED`
- `MQTT_TLS_CA_FILE`
- `MQTT_TLS_CERT_FILE`
- `MQTT_TLS_KEY_FILE`
- `MQTT_TLS_INSECURE_SKIP_VERIFY`

When `MQTT_TLS_CA_FILE` is unset, the Rust bridge uses the platform root certificate store for server verification. Set `MQTT_TLS_CA_FILE` for private broker CAs and whenever `MQTT_TLS_CERT_FILE`/`MQTT_TLS_KEY_FILE` enable MQTT client certificate authentication.

`MQTT_TLS_INSECURE_SKIP_VERIFY` must stay disabled in production unless a temporary break-glass exception is documented.

Production requires a stable `MQTT_CLIENT_ID` with `MQTT_CLEAN_SESSION=false`. Kubernetes injects
the StatefulSet pod name and Swarm uses the task slot. Do not reuse one client ID across concurrent
replicas.

## Runtime Probes

The Rust bridge and normalizer expose two unauthenticated, internal-only endpoints:

- `/healthz` reports process liveness and does not depend on external services.
- `/readyz` reports whether the service has established its required MQTT or Kafka control path.

Use `/readyz` for readiness and container health checks, and `/healthz` for liveness checks.

## Management Console Auth

Production configures OIDC introspection through `MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL`,
`MANAGEMENT_CONSOLE_OIDC_CLIENT_ID`, and `MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET`. Read and write
role lists map identity-provider roles to API authorization. `MANAGEMENT_CONSOLE_TOKEN` remains a
local compatibility fallback; `/healthz` stays public for Kubernetes probes.

Example:

```bash
curl -H "Authorization: Bearer $MANAGEMENT_CONSOLE_TOKEN" \
  https://console.example.internal/api/architecture
```

## WildFi

WildFi-specific variables:

- `WILDFI_TOPIC_PREFIXES=wildfi,wild-fi`
- `WILDFI_DECODER_REPOSITORY=https://github.com/wildlab/WildFiDecoder`
- `WILDFI_FIRMWARE_REPOSITORY=https://github.com/trichl/WildFiOpenSource`

Offline decoder defaults are stored in `deploy/kubernetes/overlays/production/wildfi-decoder-config.yaml`.
