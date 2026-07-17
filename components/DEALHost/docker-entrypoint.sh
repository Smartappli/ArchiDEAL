#!/bin/sh
set -eu

database_path="${DEALHOST_DB_PATH:-/data/db.sqlite3}"
database_directory="$(dirname "${database_path}")"

if [ ! -d "${database_directory}" ]; then
    mkdir -p "${database_directory}"
fi

if [ ! -w "${database_directory}" ]; then
    echo "DEALHost database directory is not writable: ${database_directory}" >&2
    exit 1
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
