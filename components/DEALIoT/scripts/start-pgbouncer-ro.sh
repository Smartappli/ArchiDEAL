#!/bin/sh
set -eu
DB_PASSWORD="$(tr -d '\r\n' < /run/secrets/app_user_password)"
export DB_PASSWORD
exec /entrypoint.sh pgbouncer /etc/pgbouncer/pgbouncer.ini
