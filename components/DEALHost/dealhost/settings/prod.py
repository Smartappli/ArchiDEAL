from .base import *  # noqa: F401,F403
from .env import (
    apisix_config,
    cache_config,
    database_config,
    get_csv_env,
    get_env,
    get_required_csv_env,
    get_secret_csv_env,
    get_secret_env,
    github_config,
)

DEBUG = False
DATABASES = {"default": database_config(BASE_DIR, require_postgres=True)}  # noqa: F405
SECRET_KEY = get_secret_env("DJANGO_SECRET_KEY", allow_placeholder=False)
ALLOWED_HOSTS = list(get_required_csv_env("DJANGO_ALLOWED_HOSTS"))
if "*" in ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must not contain '*' in production.")
CSRF_TRUSTED_ORIGINS = list(get_required_csv_env("DJANGO_CSRF_TRUSTED_ORIGINS"))
if not all(origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise RuntimeError("DJANGO_CSRF_TRUSTED_ORIGINS must contain only HTTPS origins.")
FORCE_SCRIPT_NAME = get_env("DEALHOST_SCRIPT_NAME", "/dealhost").strip()
if not FORCE_SCRIPT_NAME.startswith("/") or FORCE_SCRIPT_NAME.endswith("/"):
    raise RuntimeError(
        "DEALHOST_SCRIPT_NAME must start with '/' and have no trailing '/'."
    )
STATIC_URL = f"{FORCE_SCRIPT_NAME}/static/"
GITHUB = github_config(require_secrets=True)
APISIX = apisix_config(require_secrets=True)
PRODUCTION_CACHE = cache_config(require_tls=True)
CACHES["default"]["LOCATION"] = PRODUCTION_CACHE.valkey_url  # noqa: F405
DEALHOST_API_TOKENS = get_secret_csv_env(
    "DEALHOST_API_TOKENS",
    allow_placeholder=False,
)
DEALHOST_ADMIN_API_TOKENS = get_secret_csv_env(
    "DEALHOST_ADMIN_API_TOKENS",
    allow_placeholder=False,
)
DEALHOST_OIDC_INTROSPECTION_URL = get_env(
    "DEALHOST_OIDC_INTROSPECTION_URL",
    "",
).strip()
DEALHOST_OIDC_ISSUER = get_env("DEALHOST_OIDC_ISSUER", "").strip()
DEALHOST_OIDC_AUDIENCE = get_env("DEALHOST_OIDC_AUDIENCE", "").strip()
DEALHOST_OIDC_CLIENT_ID = get_env("DEALHOST_OIDC_CLIENT_ID", "").strip()
DEALHOST_OIDC_CLIENT_SECRET = get_env(
    "DEALHOST_OIDC_CLIENT_SECRET",
    "",
).strip()
DEALHOST_OIDC_READ_GROUPS = get_csv_env("DEALHOST_OIDC_READ_GROUPS", "")
DEALHOST_OIDC_ADMIN_GROUPS = get_csv_env("DEALHOST_OIDC_ADMIN_GROUPS", "")
DEALHOST_OIDC_TIMEOUT_SECONDS = float(
    get_env("DEALHOST_OIDC_TIMEOUT_SECONDS", "3"),
)
oidc_values = {
    "DEALHOST_OIDC_INTROSPECTION_URL": DEALHOST_OIDC_INTROSPECTION_URL,
    "DEALHOST_OIDC_ISSUER": DEALHOST_OIDC_ISSUER,
    "DEALHOST_OIDC_AUDIENCE": DEALHOST_OIDC_AUDIENCE,
    "DEALHOST_OIDC_CLIENT_ID": DEALHOST_OIDC_CLIENT_ID,
    "DEALHOST_OIDC_CLIENT_SECRET": DEALHOST_OIDC_CLIENT_SECRET,
}
oidc_configured = any(oidc_values.values()) or bool(
    DEALHOST_OIDC_READ_GROUPS or DEALHOST_OIDC_ADMIN_GROUPS
)
if oidc_configured:
    DEALHOST_OIDC_CLIENT_SECRET = get_secret_env(
        "DEALHOST_OIDC_CLIENT_SECRET",
        allow_placeholder=False,
    )
    missing_oidc = sorted(name for name, value in oidc_values.items() if not value)
    if not DEALHOST_OIDC_READ_GROUPS and not DEALHOST_OIDC_ADMIN_GROUPS:
        missing_oidc.append("DEALHOST_OIDC_READ_GROUPS/DEALHOST_OIDC_ADMIN_GROUPS")
    if missing_oidc:
        raise RuntimeError(
            "Incomplete DEALHost OIDC configuration: " + ", ".join(missing_oidc)
        )
    if not DEALHOST_OIDC_INTROSPECTION_URL.startswith("https://"):
        raise RuntimeError("DEALHOST_OIDC_INTROSPECTION_URL must use HTTPS.")
    if not DEALHOST_OIDC_ISSUER.startswith("https://"):
        raise RuntimeError("DEALHOST_OIDC_ISSUER must use HTTPS.")

if not DEALHOST_API_TOKENS and not DEALHOST_ADMIN_API_TOKENS and not oidc_configured:
    raise RuntimeError(
        "At least one static API token or a complete OIDC configuration is "
        "required in production.",
    )

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
