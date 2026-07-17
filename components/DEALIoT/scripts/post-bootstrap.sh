#!/usr/bin/env bash
set -Eeuo pipefail

CONNSTR="${1:?missing connection string}"

REPL_PASSWORD="$(< /run/secrets/patroni_repl_password)"
REWIND_PASSWORD="$(< /run/secrets/patroni_rewind_password)"
APP_PASSWORD="$(< /run/secrets/app_user_password)"
POSTGRES_EXPORTER_PASSWORD="$(< /run/secrets/postgres_exporter_password)"
DEBEZIUM_PASSWORD="$(< /run/secrets/debezium_password)"

APPDB_CONNSTR="$(printf '%s' "$CONNSTR" | sed -E 's/(^|[[:space:]])dbname=[^[:space:]]+/\1dbname=appdb/')"
if [[ "$APPDB_CONNSTR" == "$CONNSTR" ]]; then
  APPDB_CONNSTR="$CONNSTR dbname=appdb"
fi

psql "$CONNSTR" \
  -v ON_ERROR_STOP=1 \
  -v repl_password="$REPL_PASSWORD" \
  -v rewind_password="$REWIND_PASSWORD" \
  -v app_password="$APP_PASSWORD" \
  -v postgres_exporter_password="$POSTGRES_EXPORTER_PASSWORD" \
  -v debezium_password="$DEBEZIUM_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD %L',
  :'repl_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'replicator'
) \gexec

SELECT format(
  'ALTER ROLE replicator WITH LOGIN REPLICATION PASSWORD %L',
  :'repl_password'
) \gexec

ALTER ROLE replicator WITH REPLICATION;

SELECT format(
  'CREATE ROLE rewind_user WITH LOGIN PASSWORD %L',
  :'rewind_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'rewind_user'
) \gexec

SELECT format(
  'ALTER ROLE rewind_user WITH LOGIN PASSWORD %L',
  :'rewind_password'
) \gexec

SELECT format(
  'CREATE ROLE app_user WITH LOGIN PASSWORD %L',
  :'app_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'app_user'
) \gexec

SELECT format(
  'ALTER ROLE app_user WITH LOGIN PASSWORD %L',
  :'app_password'
) \gexec

SELECT format(
  'CREATE ROLE postgres_exporter WITH LOGIN PASSWORD %L',
  :'postgres_exporter_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter'
) \gexec

SELECT format(
  'ALTER ROLE postgres_exporter WITH LOGIN PASSWORD %L',
  :'postgres_exporter_password'
) \gexec

SELECT format(
  'CREATE ROLE debezium WITH LOGIN REPLICATION PASSWORD %L',
  :'debezium_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'debezium'
) \gexec

SELECT format(
  'ALTER ROLE debezium WITH LOGIN REPLICATION PASSWORD %L',
  :'debezium_password'
) \gexec

ALTER ROLE debezium WITH REPLICATION;

SELECT 'GRANT pg_monitor TO postgres_exporter'
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_auth_members m
  JOIN pg_roles r ON r.oid = m.roleid
  JOIN pg_roles u ON u.oid = m.member
  WHERE r.rolname = 'pg_monitor'
    AND u.rolname = 'postgres_exporter'
) \gexec

SELECT 'CREATE DATABASE appdb OWNER app_user'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = 'appdb'
) \gexec

GRANT ALL PRIVILEGES ON DATABASE appdb TO app_user;
GRANT CONNECT ON DATABASE postgres TO postgres_exporter;
GRANT CONNECT ON DATABASE appdb TO debezium;
SQL

psql "$APPDB_CONNSTR" -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

GRANT USAGE, CREATE ON SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE app_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE app_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE app_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON FUNCTIONS TO app_user;

GRANT USAGE ON SCHEMA public TO debezium;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO debezium;

ALTER DEFAULT PRIVILEGES FOR ROLE app_user IN SCHEMA public
  GRANT SELECT ON TABLES TO debezium;
ALTER DEFAULT PRIVILEGES FOR ROLE app_user IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO debezium;

DROP PUBLICATION IF EXISTS dbz_publication;
CREATE PUBLICATION dbz_publication FOR ALL TABLES;
SQL
