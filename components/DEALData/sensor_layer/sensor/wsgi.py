"""WSGI config for the sensor service."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sensor.settings")

application = get_wsgi_application()
