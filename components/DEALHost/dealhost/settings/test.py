from .dev import *  # noqa: F401,F403

# Keep tests self-contained and independent from external Redis/Valkey.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "dealhost-tests",
    },
}
DEALHOST_API_TOKENS = ("test-token",)  # nosec B105 - test fixture token only.
DEALHOST_ADMIN_API_TOKENS = (
    "test-admin-token",  # nosec B105 - test fixture token only.
)
