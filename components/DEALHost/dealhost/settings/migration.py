"""Least-privilege settings used only by the production migration Job."""

from .base import *  # noqa: F401,F403
from .env import database_config

DEBUG = False
DATABASES = {"default": database_config(BASE_DIR, require_postgres=True)}  # noqa: F405

# The migration process never serves HTTP, signs sessions or handles user data. Keeping these
# facilities process-local avoids granting it the runtime Valkey, OIDC, GitHub and APISIX secrets.
SECRET_KEY = "archideal-migration-process-does-not-serve-http-or-sign-user-sessions"
ALLOWED_HOSTS = ["localhost"]
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "archideal-migration-only",
    },
}
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
