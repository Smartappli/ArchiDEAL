"""Minimal production settings for the isolated runtime-operation worker."""

from .base import *  # noqa: F401,F403
from .env import (
    cache_config,
    database_config,
    get_env,
    get_secret_env,
    runtime_controller_config,
)


DEBUG = False
ALLOWED_HOSTS = []
DATABASES = {"default": database_config(BASE_DIR, require_postgres=True)}  # noqa: F405
SECRET_KEY = get_secret_env("DJANGO_SECRET_KEY", allow_placeholder=False)

PRODUCTION_CACHE = cache_config(require_tls=True)
CACHES["default"]["LOCATION"] = PRODUCTION_CACHE.valkey_url  # noqa: F405

RUNTIME_ENABLED = (
    get_env("DEALHOST_RUNTIME_ENABLED", "false").strip().lower() == "true"
)
if not RUNTIME_ENABLED:
    raise RuntimeError("DEALHOST_RUNTIME_ENABLED must be true for the runtime worker.")

RUNTIME_CONTROLLER = runtime_controller_config(require_tls=True)
if not RUNTIME_CONTROLLER.configured:
    raise RuntimeError(
        "The runtime worker requires an isolated runtime-controller URL and token."
    )
