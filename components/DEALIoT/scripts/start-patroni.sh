#!/bin/sh
set -eu

read_secret() {
  file="$1"
  [ -r "$file" ] || {
    echo "Secret file not readable: $file" >&2
    exit 1
  }
  tr -d '\r\n' < "$file"
}

POSTGRES_SUPERUSER_PASSWORD="$(read_secret /run/secrets/postgres_superuser_password)"
PATRONI_REPL_PASSWORD="$(read_secret /run/secrets/patroni_repl_password)"
PATRONI_REWIND_PASSWORD="$(read_secret /run/secrets/patroni_rewind_password)"
export POSTGRES_SUPERUSER_PASSWORD
export PATRONI_REPL_PASSWORD
export PATRONI_REWIND_PASSWORD

python3 - <<'PY'
import os
from pathlib import Path

src = Path("/home/postgres/postgres.yml.tmpl")
dst = Path("/home/postgres/postgres.yml")

if not src.is_file():
    raise SystemExit(f"Template not found: {src}")

template = src.read_text(encoding="utf-8")

required = (
    "POSTGRES_SUPERUSER_PASSWORD",
    "PATRONI_REPL_PASSWORD",
    "PATRONI_REWIND_PASSWORD",
)

for key in required:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing environment variable: {key}")
    template = template.replace("${" + key + "}", value)

tmp = dst.with_suffix(".yml.tmp")
tmp.write_text(template, encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(dst)
PY

# Laisse l'entrypoint officiel faire le reste:
# - création/permissions de PGDATA
# - nettoyage éventuel du postmaster.pid
# - lancement final de Patroni avec /home/postgres/postgres.yml
exec /timescaledb_entrypoint.sh
