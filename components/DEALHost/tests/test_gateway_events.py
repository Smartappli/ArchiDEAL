import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.gateway.views import (
    GitHubRepositoriesView,
    GitHubWebhookView,
    PublishRouteView,
    SyncGitHubView,
)
from dealhost.settings.env import GitHubConfig

TEST_GITHUB_CONFIG = GitHubConfig(
    owner="Smartappli",
    repository="ArchiDEAL",
    token="test-token",  # nosec B106 - test fixture token only.
    webhook_secret="test-webhook-secret",  # nosec B106 - test fixture secret.
    allowed_repositories=("Smartappli/ArchiDEAL",),
)


class GatewayEventPublishingTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, is_staff=False)
        self.admin_user = SimpleNamespace(is_authenticated=True, is_staff=True)

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    def test_publish_route_emits_requested_and_completed(
        self,
        apisix_service_cls,
        publish_mock,
    ):
        apisix_service_cls.return_value.publish_route.return_value = {"route_id": "r-1"}
        request = self.factory.post(
            "/api/gateway/apisix/publish/",
            {"module_slug": "core"},
            format="json",
        )
        force_authenticate(request, user=self.admin_user)

        response = PublishRouteView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(publish_mock.call_count, 2)
        apisix_service_cls.return_value.publish_route.assert_called_once_with(
            "core",
            dry_run=False,
        )

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    def test_publish_route_rejects_invalid_module_slug(
        self,
        apisix_service_cls,
        publish_mock,
    ):
        request = self.factory.post(
            "/api/gateway/apisix/publish/",
            {"module_slug": "../admin"},
            format="json",
        )
        force_authenticate(request, user=self.admin_user)

        response = PublishRouteView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        apisix_service_cls.assert_not_called()
        publish_mock.assert_not_called()

    @patch("apps.gateway.views.GitHubService")
    def test_sync_github_accepts_repository_full_name(self, github_service_cls):
        github = MagicMock()
        github.is_allowed_repository_full_name.return_value = True
        github.latest_commit.return_value = {
            "sha": "sha-test",
            "repository": {"full_name": "Smartappli/DEALData"},
            "commit": {"message": "test commit"},
        }
        github_service_cls.return_value = github
        request = self.factory.post(
            "/api/gateway/github/sync/",
            {"branch": "main", "repository_full_name": "Smartappli/DEALData"},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = SyncGitHubView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["repository"], "Smartappli/DEALData")
        github.latest_commit.assert_called_once_with(
            branch="main",
            repository_full_name="Smartappli/DEALData",
        )

    @patch("apps.gateway.views.GitHubService")
    def test_sync_github_rejects_a_non_string_branch(self, github_service_cls):
        request = self.factory.post(
            "/api/gateway/github/sync/",
            {"branch": {"name": "main"}},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = SyncGitHubView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "branch must be a non-empty string.")
        github_service_cls.assert_not_called()

    def test_github_repositories_lists_manifest_integrations(self):
        request = self.factory.get("/api/gateway/github/repositories/")
        force_authenticate(request, user=self.user)

        response = GitHubRepositoriesView.as_view()(request)

        repositories = {
            item["repository_full_name"]: item for item in response.data["repositories"]
        }
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(repositories), {"Smartappli/ArchiDEAL"})
        self.assertIn(
            "mqtt-kafka-bridge",
            repositories["Smartappli/ArchiDEAL"]["module_slugs"],
        )
        self.assertEqual(
            repositories["Smartappli/ArchiDEAL"]["source_dependency"]["versioning"],
            "git-sha",
        )

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    @patch("apps.gateway.views.GitHubService")
    def test_dealiot_webhook_maps_changed_paths_and_emits_events(
        self,
        github_service_cls,
        apisix_service_cls,
        publish_mock,
    ):
        github = MagicMock()
        github.verify_signature.return_value = True
        github.repository_full_name.return_value = "Smartappli/DEALIoT"
        github.expected_repository_full_name.return_value = "Smartappli/DEALIoT"
        github.allowed_repository_full_names.return_value = (
            "Smartappli/DEALIoT",
            "Smartappli/DEALData",
        )
        github.is_expected_repository.return_value = True
        github.is_allowed_event.return_value = True
        github.module_slugs_for_webhook.return_value = ["mqtt-kafka-bridge"]
        github_service_cls.return_value = github
        apisix_service_cls.return_value.publish_route.return_value = {"route_id": "r-2"}

        request = self.factory.post(
            "/api/gateway/github/webhook/",
            {
                "repository": {"full_name": "Smartappli/DEALIoT"},
                "commits": [
                    {
                        "modified": ["mqtt-kafka-bridge/bridge.py"],
                        "added": [],
                        "removed": [],
                    },
                ],
            },
            format="json",
            HTTP_X_HUB_SIGNATURE_256="sha256=ok",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_GITHUB_DELIVERY="delivery-dealiot-paths",
        )

        response = GitHubWebhookView.as_view()(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(publish_mock.call_count, 3)
        apisix_service_cls.return_value.publish_route.assert_called_once_with(
            "mqtt-kafka-bridge",
            dry_run=False,
        )
        self.assertEqual(response.data["module_slugs"], ["mqtt-kafka-bridge"])

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    @patch("apps.gateway.views.GitHubService")
    def test_webhook_ignores_unsupported_event(
        self,
        github_service_cls,
        apisix_service_cls,
        publish_mock,
    ):
        github = MagicMock()
        github.verify_signature.return_value = True
        github.repository_full_name.return_value = "Smartappli/DEALIoT"
        github.expected_repository_full_name.return_value = "Smartappli/DEALIoT"
        github.allowed_repository_full_names.return_value = (
            "Smartappli/DEALIoT",
            "Smartappli/DEALData",
        )
        github.is_expected_repository.return_value = True
        github.is_allowed_event.return_value = False
        github.allowed_events_for_repository.return_value = ("push",)
        github_service_cls.return_value = github

        request = self.factory.post(
            "/api/gateway/github/webhook/",
            {"repository": {"full_name": "Smartappli/DEALIoT"}},
            format="json",
            HTTP_X_HUB_SIGNATURE_256="sha256=ok",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_GITHUB_DELIVERY="delivery-unsupported-event",
        )

        response = GitHubWebhookView.as_view()(request)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data["ignored"])
        publish_mock.assert_not_called()
        apisix_service_cls.return_value.publish_route.assert_not_called()

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    @patch("apps.gateway.views.GitHubService")
    def test_webhook_ignores_unexpected_repository(
        self,
        github_service_cls,
        apisix_service_cls,
        publish_mock,
    ):
        github = MagicMock()
        github.verify_signature.return_value = True
        github.repository_full_name.return_value = "Other/Repo"
        github.expected_repository_full_name.return_value = "Smartappli/DEALIoT"
        github.allowed_repository_full_names.return_value = (
            "Smartappli/DEALIoT",
            "Smartappli/DEALData",
        )
        github.is_expected_repository.return_value = False
        github_service_cls.return_value = github

        request = self.factory.post(
            "/api/gateway/github/webhook/",
            {"repository": {"full_name": "Other/Repo"}},
            format="json",
            HTTP_X_HUB_SIGNATURE_256="sha256=ok",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_GITHUB_DELIVERY="delivery-unexpected-repository",
        )

        response = GitHubWebhookView.as_view()(request)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data["ignored"])
        publish_mock.assert_not_called()
        apisix_service_cls.return_value.publish_route.assert_not_called()


@override_settings(GITHUB=TEST_GITHUB_CONFIG)
class GitHubWebhookSecurityTests(SimpleTestCase):
    github_config = TEST_GITHUB_CONFIG

    def setUp(self):
        cache.clear()

    def _signature(self, payload: bytes) -> str:
        digest = hmac.new(
            self.github_config.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    def test_webhook_ignores_a_replayed_delivery(
        self,
        apisix_service_cls,
        publish_mock,
    ):
        payload = json.dumps(
            {
                "repository": {"full_name": "Smartappli/ArchiDEAL"},
                "commits": [
                    {
                        "modified": [
                            "components/DEALIoT/mqtt-kafka-bridge/bridge.py",
                        ],
                    },
                ],
            },
        ).encode("utf-8")
        apisix_service_cls.return_value.publish_route.return_value = {"route_id": "r-1"}
        headers = {
            "HTTP_X_HUB_SIGNATURE_256": self._signature(payload),
            "HTTP_X_GITHUB_EVENT": "push",
            "HTTP_X_GITHUB_DELIVERY": "delivery-replay-test",
        }

        first = self.client.post(
            reverse("github-webhook"),
            data=payload,
            content_type="application/json",
            **headers,
        )
        second = self.client.post(
            reverse("github-webhook"),
            data=payload,
            content_type="application/json",
            **headers,
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertTrue(second.data["ignored"])
        apisix_service_cls.return_value.publish_route.assert_called_once_with(
            "mqtt-kafka-bridge",
            dry_run=False,
        )
        self.assertEqual(publish_mock.call_count, 3)

    def test_webhook_validates_signature_before_parsing_json(self):
        response = self.client.post(
            reverse("github-webhook"),
            data=b"{not-json",
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
        )

        self.assertEqual(response.status_code, 401)

    def test_webhook_requires_a_delivery_id(self):
        payload = b"{}"
        response = self.client.post(
            reverse("github-webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._signature(payload),
            HTTP_X_GITHUB_EVENT="push",
        )

        self.assertEqual(response.status_code, 400)

    def test_webhook_requires_an_event(self):
        payload = b"{}"
        response = self.client.post(
            reverse("github-webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._signature(payload),
            HTTP_X_GITHUB_DELIVERY="delivery-missing-event",
        )

        self.assertEqual(response.status_code, 400)

    @patch("apps.gateway.views.publish_event")
    @patch("apps.gateway.views.ApisixService")
    def test_webhook_allows_retry_after_processing_failure(
        self,
        apisix_service_cls,
        publish_mock,
    ):
        payload = json.dumps(
            {
                "repository": {"full_name": "Smartappli/ArchiDEAL"},
                "commits": [
                    {
                        "modified": [
                            "components/DEALIoT/mqtt-kafka-bridge/bridge.py",
                        ],
                    },
                ],
            },
        ).encode("utf-8")
        apisix_service_cls.return_value.publish_route.side_effect = [
            RuntimeError("APISIX unavailable"),
            {"route_id": "r-1"},
        ]
        headers = {
            "HTTP_X_HUB_SIGNATURE_256": self._signature(payload),
            "HTTP_X_GITHUB_EVENT": "push",
            "HTTP_X_GITHUB_DELIVERY": "delivery-retry-test",
        }

        with self.assertRaisesRegex(RuntimeError, "APISIX unavailable"):
            self.client.post(
                reverse("github-webhook"),
                data=payload,
                content_type="application/json",
                **headers,
            )
        retry = self.client.post(
            reverse("github-webhook"),
            data=payload,
            content_type="application/json",
            **headers,
        )

        self.assertEqual(retry.status_code, 202)
        self.assertEqual(apisix_service_cls.return_value.publish_route.call_count, 2)
        self.assertEqual(publish_mock.call_count, 6)
