#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET="$ROOT/.env"

if [ -e "$TARGET" ]; then
  echo "$TARGET already exists; refusing to overwrite it." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate local credentials." >&2
  exit 1
fi

random_value() {
  openssl rand -hex 32
}

umask 077
cat >"$TARGET" <<EOF
ARCHIDEAL_HTTP_PORT=8080
ARCHIDEAL_IMAGE_TAG=dev
APISIX_ADMIN_KEY=$(random_value)
VERNEMQ_DISTRIBUTED_COOKIE=$(random_value)
VERNEMQ_ADMIN_PASSWORD=$(random_value)
CORE_DJANGO_SECRET_KEY=$(random_value)
GPS_DJANGO_SECRET_KEY=$(random_value)
SENSOR_DJANGO_SECRET_KEY=$(random_value)
CORE_DATABASE_PASSWORD=$(random_value)
GPS_DATABASE_PASSWORD=$(random_value)
SENSOR_DATABASE_PASSWORD=$(random_value)
DEALIOT_REGISTRY_DATABASE_PASSWORD=$(random_value)
DEALDATA_INGEST_TOKEN=$(random_value)
DEALHOST_DJANGO_SECRET_KEY=$(random_value)
DEALHOST_API_TOKENS=$(random_value)
DEALHOST_ADMIN_API_TOKENS=$(random_value)
GITHUB_TOKEN=
GITHUB_WEBHOOK_SECRET=$(random_value)
EOF

echo "Created $TARGET with local-only random credentials."
