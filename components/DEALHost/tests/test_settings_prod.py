import importlib
import os
import sys
from unittest.mock import patch

from django.test import SimpleTestCase


PROD_SETTINGS_MODULE = "dealhost.settings.prod"


def _reload_prod_settings():
    sys.modules.pop(PROD_SETTINGS_MODULE, None)
    return importlib.import_module(PROD_SETTINGS_MODULE)


class ProductionSettingsTests(SimpleTestCase):
    def test_prod_settings_require_explicit_secure_values(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com,api.dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105 - test fixture.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105 - test fixture.
            "DEALHOST_API_TOKENS": "service-token",  # nosec B105 - test fixture.
            "DEALHOST_ADMIN_API_TOKENS": "",
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

    def test_prod_settings_reject_wildcard_allowed_hosts(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "*",
        }

        with patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            _reload_prod_settings()

    def test_prod_settings_require_at_least_one_api_token(self):
        env = {
            "DJANGO_SECRET_KEY": "prod-secret-key",  # nosec B105 - test fixture.
            "DJANGO_ALLOWED_HOSTS": "dealhost.example.com",
            "GITHUB_TOKEN": "github-token",  # nosec B105 - test fixture.
            "GITHUB_WEBHOOK_SECRET": "github-webhook-secret",  # nosec B105 - test fixture.
            "APISIX_ADMIN_KEY": "apisix-admin-key",  # nosec B105 - test fixture.
            "DEALHOST_API_TOKENS": "",
            "DEALHOST_ADMIN_API_TOKENS": "",
        }

        with patch.dict(os.environ, env, clear=False), self.assertRaises(RuntimeError):
            _reload_prod_settings()
