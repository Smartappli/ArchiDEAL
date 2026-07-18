from __future__ import annotations

from pathlib import Path

from django.utils.translation import gettext_lazy as _

from .env import (
    apisix_config,
    cache_config,
    database_config,
    get_csv_env,
    get_env,
    github_config,
    nats_config,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = get_env("DJANGO_SECRET_KEY", "replace-me")
DEBUG = False
ALLOWED_HOSTS = list(get_csv_env("DJANGO_ALLOWED_HOSTS", "*"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.hosting",
    "apps.iam",
    "apps.gateway",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "servestatic.middleware.ServeStaticMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dealhost.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "dealhost.asgi.application"

DATABASES = {"default": database_config(BASE_DIR)}

LANGUAGE_CODE = "fr-fr"
LANGUAGES = [
    ("ar", _("Arabic")),
    ("zh-hans", _("Chinese (Simplified)")),
    ("en", _("English")),
    ("fr", _("French")),
    ("ru", _("Russian")),
    ("es", _("Spanish")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "servestatic.storage.CompressedManifestStaticFilesStorage",
    },
}

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_CACHE_ALIAS = "default"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": cache_config().valkey_url,
        "OPTIONS": {
            "socket_connect_timeout": 2.0,
            "socket_timeout": 2.0,
        },
    },
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.common.authentication.EnvBearerAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

DEALHOST_API_TOKENS = get_csv_env("DEALHOST_API_TOKENS", "")
DEALHOST_ADMIN_API_TOKENS = get_csv_env("DEALHOST_ADMIN_API_TOKENS", "")
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

GITHUB = github_config()
APISIX = apisix_config()

NATS = {
    "URL": nats_config().url,
    "STREAM": nats_config().stream,
    "SUBJECT_PREFIX": nats_config().subject_prefix,
    "ENABLED": nats_config().enabled,
}
