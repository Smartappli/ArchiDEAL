# Operations Runbook

This runbook defines the minimum operating procedures for the local and production-like DEALIoT
topologies.

## Scope

The Compose topology is a local validation environment. It verifies integration behavior, startup
ordering, contracts, and smoke flows. It does not prove multi-host resilience because Kafka,
Patroni, etcd, SeaweedFS, and observability still share one Docker host.

## Required Readiness Checks

Run these checks before accepting a deployment change:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml config -q
bash scripts/smoke-e2e.sh
bash scripts/fault-injection-smoke.sh
```

The E2E smoke test must prove:

- MQTT valid telemetry reaches `raw.sensor`
- WildFi decoded telemetry reaches `raw.sensor` or `raw.gps`
- invalid media metadata reaches `dlq.events`
- Flink emits `features.events`
- Flink updates `state.latest`
- Apicurio contains the `raw.sensor` and `dlq.events` artifacts
- a crash before source acknowledgement produces no loss and at most one duplicate

## Incident Triage

1. Check container health:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
   ```

2. Dump recent logs:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail=300 --timestamps
   ```

3. Verify Kafka topic creation:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml exec kafka1 \
     /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka1:9092 --list
   ```

4. Verify DLQ volume before retrying producers:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml exec kafka1 \
     /opt/kafka/bin/kafka-console-consumer.sh \
       --bootstrap-server kafka1:9092 \
       --topic dlq.events \
       --from-beginning \
       --timeout-ms 10000
   ```

## Restart Order

Use dependency layers, not a full blind restart:

1. etcd
2. Patroni PostgreSQL
3. HAProxy and PgBouncer
4. Kafka
5. Apicurio and Kafka Connect
6. SeaweedFS
7. VerneMQ and `mqtt-kafka-bridge`
8. Flink, Beam, and Airflow
9. Prometheus and Grafana

## Release Acceptance

A release is not accepted until all of these are true:

- unit and repository tests pass
- Compose renders with the target overlay
- `scripts/smoke-e2e.sh` passes on a clean volume set
- no sensitive fallback passwords are present in Compose
- local-only ports are absent from the base Compose file
