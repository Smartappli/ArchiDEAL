from .base import *  # noqa: F401,F403
from .env import (
    apisix_config,
    get_required_csv_env,
    get_secret_csv_env,
    get_secret_env,
    github_config,
)

DEBUG = False
SECRET_KEY = get_secret_env("DJANGO_SECRET_KEY", allow_placeholder=False)
ALLOWED_HOSTS = list(get_required_csv_env("DJANGO_ALLOWED_HOSTS"))
if "*" in ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must not contain '*' in production.")
GITHUB = github_config(require_secrets=True)
APISIX = apisix_config(require_secrets=True)
DEALHOST_API_TOKENS = get_secret_csv_env(
    "DEALHOST_API_TOKENS",
    allow_placeholder=False,
)
DEALHOST_ADMIN_API_TOKENS = get_secret_csv_env(
    "DEALHOST_ADMIN_API_TOKENS",
    allow_placeholder=False,
)
if not DEALHOST_API_TOKENS and not DEALHOST_ADMIN_API_TOKENS:
    raise RuntimeError(
        "At least one DEALHOST_API_TOKENS or DEALHOST_ADMIN_API_TOKENS value "
        "is required in production.",
    )

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
