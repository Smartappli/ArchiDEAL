# Kubernetes Production Overlay

This overlay is the production contract for Kubernetes deployments.

It intentionally does not deploy Kafka, PostgreSQL, Redis, MQTT, or S3-compatible storage. Those
stateful dependencies must be provided by managed services or dedicated operators and exposed to
DEALIoT through `dealiot-runtime-config` plus the `dealiot-secrets` Secret.

Install Apache Flink Kubernetes Operator `1.15.0` before applying this overlay. Production uses an
application-mode `FlinkDeployment` with Kubernetes HA metadata, S3 checkpoints/savepoints,
savepoint upgrades, and job-aware autoscaling. The legacy standalone package remains available for
migration only; the `rust-normalizer` overlay is the mutually exclusive lightweight alternative.
The JVM distribution, PyFlink package, plugins, and Python driver are aligned on Flink `2.2.1`,
which is in the operator 1.15 validated compatibility matrix.
Install the operator in a namespace labeled `dealiot.io/flink-operator=allowed`; the production
NetworkPolicy permits that namespace to reach the Flink REST control endpoint.

## Release Images

Replace the placeholder tags before deployment:

```bash
RELEASE_SHA="$(git rev-parse HEAD)"
kustomize edit set image \
  ghcr.io/smartappli/dealiot-mqtt-kafka-bridge=ghcr.io/smartappli/dealiot-mqtt-kafka-bridge:sha-"$RELEASE_SHA" \
  ghcr.io/smartappli/dealiot-stream-normalizer=ghcr.io/smartappli/dealiot-stream-normalizer:sha-"$RELEASE_SHA" \
  ghcr.io/smartappli/dealiot-management-console=ghcr.io/smartappli/dealiot-management-console:sha-"$RELEASE_SHA" \
  ghcr.io/smartappli/dealiot-flink-pyflink=ghcr.io/smartappli/dealiot-flink-pyflink:sha-"$RELEASE_SHA" \
  ghcr.io/smartappli/dealiot-orchestration=ghcr.io/smartappli/dealiot-orchestration:sha-"$RELEASE_SHA"
```

Do not deploy `latest` in production.

## Runtime Config

This overlay replaces the base `dealiot-runtime-config` ConfigMap with
`runtime-config.production.example.env` so production does not inherit local development endpoints.
Before deployment, copy or patch that file through a site-specific overlay or GitOps tooling with
your private Kafka, MQTT, S3, PostgreSQL, and Redis endpoints.

Kafka is configured for `SASL_SSL` by default in the production example. MQTT is configured for TLS
on port `8883`. Keep those defaults unless the network path is already private and encrypted by a
separate control plane.

The production runtime config subscribes to both generic device telemetry and WildFi telemetry:

```text
MQTT_TOPICS=$share/ingestors/devices/#,$share/ingestors/wildfi/#
WILDFI_TOPIC_PREFIXES=wildfi,wild-fi
```

`wildfi-decoder-config.yaml` documents the `wildlab/WildFiDecoder` conversion factors and expected
MQTT topic mapping. `wildfi-decoder-job.yaml` defines a suspended offline decoding Job using
`ghcr.io/smartappli/dealiot-wildfi-decoder`. Keep native WildFi binary logs in object storage or
decode them before publication.

Create a PVC named `wildfi-decoder-workdir` containing the `.bin` files before unsuspending a copied
decoder Job. The default mode is `2`, which decodes WildFi hdLogger movement data; mode `1` targets
proxLogger data and mode `3` decodes gateway metadata.

## Required Secret

Create `dealiot-secrets` with all keys listed in
`external-dependency-contract.yaml`. Prefer External Secrets Operator, Vault, or your cloud secret
manager over literal in-repo manifests. `dealiot-secrets.example.env` documents the required keys.

The runtime services require at least:

- `MQTT_PASSWORD`
- `KAFKA_SASL_PASSWORD`
- `MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET`

The Management Console keeps `/healthz` public for probes. Production bearer tokens are
introspected through OIDC and mapped to read/write roles. The production process rejects
`MANAGEMENT_CONSOLE_TOKEN`. Set `MANAGEMENT_CONSOLE_PUBLIC_ORIGIN` to the exact external HTTPS
origin so browser mutations from any other origin fail closed; bearer service clients without an
`Origin` header remain supported.

## Availability

The overlay runs the MQTT bridge as a StatefulSet so each replica has a stable MQTT client ID and
persistent session. Its HorizontalPodAutoscaler has a conservative scale-down policy to limit
session churn. The overlay also adds HorizontalPodAutoscalers for Airflow workers and the
Management Console, adds PodDisruptionBudgets for the application tiers, and uses topology spread
constraints so replicas are not concentrated on one node.

Flink capacity is controlled by the operator autoscaler using job backlog and utilization metrics.
Upgrades use savepoints and the adaptive scheduler; do not attach a CPU HPA to operator-managed
TaskManagers.

## Network Policy

The overlay applies default deny ingress/egress, then opens:

- explicit Airflow, Apicurio, and Flink east-west ports,
- DNS egress,
- production dependency ports for Kafka, MQTT over TLS, S3 over TLS, PostgreSQL, Redis,
- Airflow API ingress only from namespaces labeled `dealiot.io/ingress=allowed`.
- Management Console ingress only from namespaces labeled `dealiot.io/ingress=allowed`.

Patch `network-policies.yaml` with narrower `ipBlock` ranges for your actual private networks.

## Optional Platform Controls

Add `../../components/security-platform` only after External Secrets Operator and Kyverno 1.18+
are installed. It materializes `dealiot-secrets` and denies unsigned DEALIoT images. Add
`../../components/observability` after Prometheus Operator is installed to enable PodMonitors and
the SLO alert rules. Patch the remote secret store, GitHub signer identity, and monitoring labels in
a site-specific overlay.
