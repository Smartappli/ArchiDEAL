from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class GatewayHealthTests(TestCase):
    invalid_basic_auth = "Basic YXJjaGlkZWFsOnN0YWdpbmc="

    def test_readiness_uses_the_configured_database_and_cache_backends(self):
        response = self.client.get(reverse("gateway-health-ready"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "available")
        self.assertEqual(response.json()["cache"], "available")

    @patch("apps.gateway.views._cache_is_ready")
    @patch("apps.gateway.views._database_is_ready")
    def test_liveness_does_not_call_external_dependencies(
        self,
        database_ready,
        cache_ready,
    ):
        response = self.client.get(reverse("gateway-health-live"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "gateway"})
        database_ready.assert_not_called()
        cache_ready.assert_not_called()

    @patch("apps.gateway.views._cache_is_ready", return_value=True)
    @patch("apps.gateway.views._database_is_ready", return_value=True)
    def test_readiness_requires_database_and_cache(self, database_ready, cache_ready):
        response = self.client.get(reverse("gateway-health-ready"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "gateway",
                "database": "available",
                "cache": "available",
            },
        )
        database_ready.assert_called_once_with()
        cache_ready.assert_called_once_with()

    @patch("apps.gateway.views._cache_is_ready", side_effect=ConnectionError)
    @patch("apps.gateway.views._database_is_ready", return_value=True)
    def test_readiness_returns_503_without_leaking_dependency_errors(
        self,
        _database_ready,
        _cache_ready,
    ):
        response = self.client.get(reverse("gateway-health-ready"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(response.json()["database"], "available")
        self.assertEqual(response.json()["cache"], "unavailable")
        self.assertNotIn("detail", response.json())

    @patch("apps.gateway.views._cache_is_ready", return_value=True)
    @patch("apps.gateway.views._database_is_ready", return_value=True)
    def test_legacy_health_endpoint_remains_a_readiness_alias(self, *_checks):
        response = self.client.get(reverse("gateway-health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "available")
        self.assertEqual(response.json()["cache"], "available")

    @patch("apps.gateway.views._cache_is_ready", return_value=True)
    @patch("apps.gateway.views._database_is_ready", return_value=True)
    def test_health_endpoints_ignore_invalid_basic_auth_from_reverse_proxy(
        self,
        *_checks,
    ):
        for route_name in (
            "gateway-health",
            "gateway-health-live",
            "gateway-health-ready",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(
                    reverse(route_name),
                    HTTP_AUTHORIZATION=self.invalid_basic_auth,
                )

                self.assertEqual(response.status_code, 200)

    def test_invalid_basic_auth_remains_rejected_on_protected_endpoints(self):
        response = self.client.get(
            reverse("github-repositories"),
            HTTP_AUTHORIZATION=self.invalid_basic_auth,
        )

        self.assertEqual(response.status_code, 401)
