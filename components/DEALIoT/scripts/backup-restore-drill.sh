#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.dev.yml)
RESTORE_DATABASE="${RESTORE_DATABASE:-airflow_restore_drill}"
RESTORE_RTO_SECONDS="${RESTORE_RTO_SECONDS:-300}"

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_command docker
require_command mktemp

workdir="$(mktemp -d)"
dump_path="${workdir}/airflow.sql"
started_at="$(date +%s)"

cleanup() {
  compose exec -T airflow-postgres sh -ec \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists --force -U "$POSTGRES_USER" "$1"' \
    sh "$RESTORE_DATABASE" >/dev/null 2>&1 || true
  rm -rf "$workdir"
}
trap cleanup EXIT

echo "Creating a logical backup of the Airflow metadata database"
compose exec -T airflow-postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  >"$dump_path"
test -s "$dump_path"

echo "Restoring the backup into an isolated verification database"
compose exec -T airflow-postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists --force -U "$POSTGRES_USER" "$1" && PGPASSWORD="$POSTGRES_PASSWORD" createdb -U "$POSTGRES_USER" "$1"' \
  sh "$RESTORE_DATABASE"
compose exec -T airflow-postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"' \
  sh "$RESTORE_DATABASE" <"$dump_path" >/dev/null

source_tables="$(compose exec -T airflow-postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from information_schema.tables where table_schema = '\''public'\''"')"
restored_tables="$(compose exec -T airflow-postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -At -U "$POSTGRES_USER" -d "$1" -c "select count(*) from information_schema.tables where table_schema = '\''public'\''"' \
  sh "$RESTORE_DATABASE")"

if [ "$source_tables" != "$restored_tables" ]; then
  echo "Restore verification failed: source tables=${source_tables}, restored=${restored_tables}" >&2
  exit 1
fi

echo "Verifying recoverable Kafka topic configuration"
for topic in raw.sensor state.latest resilience.backup.tests; do
  compose exec -T kafka1 /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server kafka1:9092 --describe --topic "$topic" >/dev/null
done

duration_seconds="$(($(date +%s) - started_at))"
if [ "$duration_seconds" -gt "$RESTORE_RTO_SECONDS" ]; then
  echo "Restore drill exceeded RTO: ${duration_seconds}s > ${RESTORE_RTO_SECONDS}s" >&2
  exit 1
fi

evidence="$(printf '{"kind":"backup_restore_drill","status":"passed","database":"airflow","source_tables":%s,"restored_tables":%s,"duration_seconds":%s,"rto_seconds":%s,"occurred_at":"%s"}' \
  "$source_tables" "$restored_tables" "$duration_seconds" "$RESTORE_RTO_SECONDS" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
printf '%s\n' "$evidence" | compose exec -T kafka1 \
  /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server kafka1:9092 --topic resilience.backup.tests >/dev/null

echo "Backup/restore drill passed in ${duration_seconds}s (${restored_tables} restored tables)"
