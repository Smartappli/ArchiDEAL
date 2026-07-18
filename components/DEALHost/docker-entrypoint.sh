#!/bin/sh
set -eu

if [ "${DEALHOST_DATABASE_ENGINE:-sqlite}" = "sqlite" ]; then
    database_path="${DEALHOST_DB_PATH:-/data/db.sqlite3}"
    database_directory="$(dirname "${database_path}")"

    if [ ! -d "${database_directory}" ]; then
        mkdir -p "${database_directory}"
    fi

    if [ ! -w "${database_directory}" ]; then
        echo "DEALHost database directory is not writable: ${database_directory}" >&2
        exit 1
    fi
fi

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
