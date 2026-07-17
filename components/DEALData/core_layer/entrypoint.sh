#!/bin/sh
set -e

case "${DJANGO_DEBUG:-true}" in
  false|False|FALSE|0|no|No|NO|off|Off|OFF)
    echo "Checking production Django configuration..."
    python manage.py check --deploy
    ;;
esac

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

echo "Starting Django application..."
exec "$@"
