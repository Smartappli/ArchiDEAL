import importlib
import os
import sys
from unittest.mock import patch

from django.test import SimpleTestCase

from dealhost.settings.env import cache_config, get_secret_env


PROD_SETTINGS_MODULE = "dealhost.settings.prod"
MIGRATION_SETTINGS_MODULE = "dealhost.settings.migration"


def _reload_prod_settings():
    sys.modules.pop(PROD_SETTINGS_MODULE, None)
    return importlib.import_module(PROD_SETTINGS_MODULE)


def _reload_migration_settings():
    sys.modules.pop(MIGRATION_SETTINGS_MODULE, None)
    return importlib.import_module(MIGRATION_SETTINGS_MODULE)


class ProductionSettingsTests(SimpleTestCase):
    def test_migration_settings_need_only_hardened_postgres_configuration(self):
        env = {
            "DEALHOST_DATABASE_ENGINE": "postgresql",
            "DEALHOST_DATABASE_HOST": "postgres.example.com",
            "DEALHOST_DATABASE_PASSWORD": "database-secret",  # nosec B105.
            "DEALHOST_DATABASE_SSLMODE": "verify-full",
            "DEALHOST_DATABASE_SSLROOTCERT": "/run/secrets/postgres/ca.crt",
        }

        with patch.dict(os.environ, env, clear=True):
            migration = _reload_migration_settings()

        self.assertEqual(
            migration.DATABASES["default"]["ENGINE"],
            "django.db.backends.postgresql",
        )
        self.assertEqual(
            migration.DATABASES["default"]["OPTIONS"]["sslmode"],
            "verify-full",
        )
        self.assertEqual(
            migration.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )

    def test_prod_settings_require_explicit_secure_values(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com,api.dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105 - test fixture.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105 - test fixture.
            "DEALHOST_API_TOKENS": "service-token",  # nosec B105 - test fixture.
            "DEALHOST_ADMIN_API_TOKENS": "",
            "DEALHOST_DATABASE_ENGINE": "postgresql",
            "DEALHOST_DATABASE_HOST": "postgres.example.com",
            "DEALHOST_DATABASE_PASSWORD": "database-secret",  # nosec B105
            "DEALHOST_DATABASE_SSLMODE": "verify-full",
            "DEALHOST_DATABASE_SSLROOTCERT": "/run/secrets/postgres/ca.crt",
            "VALKEY_URL": "rediss://dealhost:secret@valkey.example.com:6380/1",
        }

        with patch.dict(os.environ, env, clear=False):
            prod = _reload_prod_settings()

        self.assertFalse(prod.DEBUG)
        self.assertEqual(
            prod.ALLOWED_HOSTS,
            ["dealhost.example.com", "api.dealhost.example.com"],
        )
        self.assertEqual(
            prod.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(prod.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(prod.SECURE_HSTS_PRELOAD)
        self.assertEqual(prod.CSRF_TRUSTED_ORIGINS, ["https://dealhost.example.com"])
        self.assertEqual(prod.FORCE_SCRIPT_NAME, "/dealhost")
        self.assertEqual(prod.STATIC_URL, "/dealhost/static/")
        self.assertEqual(
            prod.DATABASES["default"]["ENGINE"],
            "django.db.backends.postgresql",
        )
        self.assertEqual(prod.DATABASES["default"]["OPTIONS"]["sslmode"], "verify-full")
        self.assertEqual(prod.DATABASES["default"]["OPTIONS"]["connect_timeout"], 3)
        self.assertEqual(
            prod.CACHES["default"]["OPTIONS"],
            {"socket_connect_timeout": 2.0, "socket_timeout": 2.0},
        )
        self.assertEqual(
            prod.CACHES["default"]["LOCATION"],
            "rediss://dealhost:secret@valkey.example.com:6380/1",
        )

    def test_prod_settings_reject_sqlite_database(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105 - test fixture.
            "DEALHOST_API_TOKENS": "service-token",  # nosec B105 - test fixture.
            "DEALHOST_DATABASE_ENGINE": "sqlite",
        }

        with patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            _reload_prod_settings()

    def test_prod_settings_reject_wildcard_allowed_hosts(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "*",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
        }

        with patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            _reload_prod_settings()

    def test_prod_settings_accept_complete_oidc_without_static_api_token(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105.
            "DEALHOST_API_TOKENS": "",
            "DEALHOST_ADMIN_API_TOKENS": "",
            "DEALHOST_DATABASE_ENGINE": "postgresql",
            "DEALHOST_DATABASE_HOST": "postgres.example.com",
            "DEALHOST_DATABASE_PASSWORD": "database-secret",  # nosec B105.
            "DEALHOST_DATABASE_SSLMODE": "verify-full",
            "DEALHOST_DATABASE_SSLROOTCERT": "/run/secrets/postgres/ca.crt",
            "VALKEY_URL": "rediss://dealhost:secret@valkey.example.com:6380/1",
            "DEALHOST_OIDC_INTROSPECTION_URL": (
                "https://identity.example.com/oauth2/introspect"
            ),
            "DEALHOST_OIDC_ISSUER": "https://identity.example.com",
            "DEALHOST_OIDC_AUDIENCE": "archideal-production",
            "DEALHOST_OIDC_CLIENT_ID": "dealhost",
            "DEALHOST_OIDC_CLIENT_SECRET": "oidc-client-secret",  # nosec B105.
            "DEALHOST_OIDC_READ_GROUPS": "archideal-readers",
            "DEALHOST_OIDC_ADMIN_GROUPS": "archideal-operators",
        }

        with patch.dict(os.environ, env, clear=False):
            prod = _reload_prod_settings()

        self.assertEqual(
            prod.DEALHOST_OIDC_INTROSPECTION_URL,
            "https://identity.example.com/oauth2/introspect",
        )

    def test_prod_settings_validate_oidc_completeness_after_secret_loading(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105.
            "DEALHOST_API_TOKENS": "",
            "DEALHOST_ADMIN_API_TOKENS": "",
            "DEALHOST_DATABASE_ENGINE": "postgresql",
            "DEALHOST_DATABASE_HOST": "postgres.example.com",
            "DEALHOST_DATABASE_PASSWORD": "database-secret",  # nosec B105.
            "DEALHOST_DATABASE_SSLMODE": "verify-full",
            "DEALHOST_DATABASE_SSLROOTCERT": "/run/secrets/postgres/ca.crt",
            "VALKEY_URL": "rediss://dealhost:secret@valkey.example.com:6380/1",
            "DEALHOST_OIDC_INTROSPECTION_URL": (
                "https://identity.example.com/oauth2/introspect"
            ),
            "DEALHOST_OIDC_ISSUER": "https://identity.example.com",
            "DEALHOST_OIDC_AUDIENCE": "archideal-production",
            "DEALHOST_OIDC_CLIENT_ID": "dealhost",
            "DEALHOST_OIDC_CLIENT_SECRET": "unresolved-secret",  # nosec B105.
            "DEALHOST_OIDC_READ_GROUPS": "archideal-readers",
        }

        def resolve_secret(name, default=None, *, allow_placeholder=True):
            if name == "DEALHOST_OIDC_CLIENT_SECRET":
                return "resolved-oidc-secret"
            return get_secret_env(
                name,
                default,
                allow_placeholder=allow_placeholder,
            )

        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "dealhost.settings.env.get_secret_env",
                side_effect=resolve_secret,
            ),
        ):
            prod = _reload_prod_settings()

        self.assertEqual(
            prod.oidc_values["DEALHOST_OIDC_CLIENT_SECRET"],
            "resolved-oidc-secret",
        )
        self.assertEqual(
            prod.DEALHOST_OIDC_CLIENT_SECRET,
            "resolved-oidc-secret",
        )

    def test_prod_settings_reject_unencrypted_valkey(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105.
            "DEALHOST_API_TOKENS": "service-token",  # nosec B105.
            "DEALHOST_DATABASE_ENGINE": "postgresql",
            "DEALHOST_DATABASE_HOST": "postgres.example.com",
            "DEALHOST_DATABASE_PASSWORD": "database-secret",  # nosec B105.
            "DEALHOST_DATABASE_SSLMODE": "verify-full",
            "DEALHOST_DATABASE_SSLROOTCERT": "/run/secrets/postgres/ca.crt",
            "VALKEY_URL": "redis://valkey.example.com:6379/1",
        }

        with (
            patch.dict(os.environ, env, clear=False),
            self.assertRaisesRegex(RuntimeError, "rediss://"),
        ):
            _reload_prod_settings()

    def test_prod_settings_reject_valkey_tls_verification_override(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105.
            "DEALHOST_API_TOKENS": "service-token",  # nosec B105.
            "DEALHOST_DATABASE_ENGINE": "postgresql",
            "DEALHOST_DATABASE_HOST": "postgres.example.com",
            "DEALHOST_DATABASE_PASSWORD": "database-secret",  # nosec B105.
            "DEALHOST_DATABASE_SSLMODE": "verify-full",
            "DEALHOST_DATABASE_SSLROOTCERT": "/run/secrets/postgres/ca.crt",
            "VALKEY_URL": (
                "rediss://session-user:secret@valkey.example.com:6380/1"
                "?ssl_cert_reqs=none"
            ),
        }

        with (
            patch.dict(os.environ, env, clear=False),
            self.assertRaisesRegex(RuntimeError, "authenticated rediss://"),
        ):
            _reload_prod_settings()

    def test_non_production_cache_keeps_plaintext_development_compatibility(self):
        with patch.dict(
            os.environ,
            {"VALKEY_URL": "redis://valkey:6379/1"},
            clear=False,
        ):
            config = cache_config()

        self.assertEqual(config.valkey_url, "redis://valkey:6379/1")

    def test_prod_settings_require_at_least_one_api_token(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105 - test fixture.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105 - test fixture.
            "DEALHOST_API_TOKENS": "",
            "DEALHOST_ADMIN_API_TOKENS": "",
        }

        with patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            _reload_prod_settings()
