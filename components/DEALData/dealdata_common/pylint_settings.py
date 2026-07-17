"""Minimal Django settings used by Pylint-Django analysis."""

from __future__ import annotations

from pathlib import Path
import sys

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

for layer_path in ("core_layer", "gps_layer", "sensor_layer"):
    path = str(BASE_DIR / layer_path)
    if path not in sys.path:
        sys.path.insert(0, path)

SECRET_KEY = get_random_secret_key()
DEBUG = False
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "dealdata_common.pylint_urls"
MIDDLEWARE: list[str] = []
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "auth.apps.AuthConfig",
    "core_data.apps.CoreDataConfig",
    "gps_data.apps.GpsConfig",
    "sensor_data.apps.SensorDataConfig",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}
