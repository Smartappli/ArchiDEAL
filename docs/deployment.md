# Deployment guide

## Development and integration

Requirements:

- Docker Engine and Docker Compose v2;
- Python 3.12 or newer for validation and smoke checks;
- OpenSSL for local credential generation;
- sufficient disk, memory and build time for Rust, Node and three Python application images.

Create the ignored `.env` file once:

```bash
./scripts/bootstrap-env.sh
```

Review it, then validate and start the stack:

```bash
python scripts/validate-monorepo.py
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
./scripts/smoke-architecture.sh
```

The public entry point is `http://127.0.0.1:8080` by default. No database, Kafka, MQTT, component
HTTP port or APISIX Admin port is exposed on the host.

Useful diagnostics:

```bash
docker compose ps --all
docker compose logs --timestamps apisix apisix-bootstrap
docker compose logs --timestamps mqtt-kafka-bridge dealdata-gps-consumer dealdata-sensor-consumer
docker compose down --remove-orphans
```

The DEALIoT `/api/health` response is expected to mark Kafka and MQTT healthy while optional full
platform services such as Airflow, Flink, Apicurio and Prometheus remain absent or degraded in the
compact profile.

## Release discipline

Every ArchiDEAL release should pin:

- the monorepo commit;
- container image digests;
- Kafka, APISIX, etcd, PostgreSQL, Flink, Beam and Apicurio versions;
- schema versions and topic configuration;
- database migration state.

Run component tests, root validation and the end-to-end smoke test before creating a release tag.
Nested `.github/workflows` files under `components/` are retained as provenance but are not executed
by GitHub; root workflows are authoritative.

## Production gates

The root Compose file must not be deployed as production without a reviewed production overlay.
At minimum, that overlay must provide:

- multi-node Kafka and MQTT with TLS, SASL/authentication and least-privilege ACLs;
- TLS termination, trusted forwarded headers and an explicit public route policy;
- OIDC Authorization Code with PKCE or a backend-for-frontend for DEALInterface;
- PostgreSQL for DEALHost and managed/HA PostgreSQL for DEALData;
- a secret manager, rotation procedure and no plaintext environment secrets;
- APISIX Admin API network allowlisting and preferably mTLS;
- persistent-volume backups plus tested restore procedures;
- full dependency-aware readiness, metrics, logs and traces;
- immutable images and software-bill-of-materials/provenance checks;
- the complete DEALIoT processing, schema, storage and observability services required by the use case.

The full deployment is supported only when the cross-component smoke test also passes against the
production topology.
