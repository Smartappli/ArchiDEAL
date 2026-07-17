# Backup And Restore Runbook

This is the minimum backup policy for operating DEALIoT beyond a disposable local demo.

## Backup Targets

Back up these state stores:

- TimescaleDB/Patroni data: application tables, Airflow metadata if migrated, roles, publications
- Kafka: topic configs, ACLs when enabled, consumer offsets, and broker metadata
- SeaweedFS: filer metadata and volume data
- Apicurio: registry KafkaSQL topics
- Grafana: provisioning plus dashboard database state
- Airflow: DAGs, logs if required, metadata database, Fernet/API/JWT secrets

## TimescaleDB

Use logical backup for portability:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec pg1 \
  pg_dumpall -U postgres > backups/postgres/full-$(date +%Y%m%dT%H%M%S).sql
```

Restore into a clean cluster:

```bash
cat backups/postgres/full-YYYYMMDDTHHMMSS.sql | \
  docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T pg1 \
    psql -U postgres
```

## Kafka Metadata

Export topic definitions:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec kafka1 \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka1:9092 --describe \
  > backups/kafka/topics-$(date +%Y%m%dT%H%M%S).txt
```

For production, add a proper MirrorMaker/cluster-linking or vendor backup strategy before
depending on Kafka as the only event archive.

## SeaweedFS

Back up both filer metadata and volume storage. In Compose these are Docker volumes; for a real
deployment use the storage backend snapshot mechanism plus periodic restore drills.

## Restore Drill

Run a restore drill at least before each release that changes:

- database schema or Debezium publication settings
- Kafka topic names, partition counts, or compaction policy
- SeaweedFS bucket layout
- Apicurio artifact groups or compatibility policy

The drill must finish with:

```bash
bash scripts/smoke-e2e.sh
bash scripts/fault-injection-smoke.sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait airflow-postgres
bash scripts/backup-restore-drill.sh
```

The automated restore drill dumps Airflow PostgreSQL, restores it into an isolated database,
compares public table counts, verifies critical Kafka topic definitions, enforces
`RESTORE_RTO_SECONDS` (300 seconds by default), and publishes a result to
`resilience.backup.tests`. Production providers still require their native point-in-time recovery,
cross-region Kafka replication, and object-storage versioning procedures.
