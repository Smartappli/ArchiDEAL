import hashlib
import hmac
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.gateway.services import ApisixService, GitHubService
from apps.hosting.models import Module
from dealhost.settings.env import ApisixConfig, GitHubConfig


@override_settings(
    GITHUB=GitHubConfig(
        owner="Smartappli",
        repository="ArchiDEAL",
        token="token",  # nosec B106 - test fixture token only.
        webhook_secret="secret-test",  # nosec B106 - test fixture secret only.
        allowed_repositories=("Smartappli/ArchiDEAL",),
    ),
)
class GitHubServiceTests(SimpleTestCase):
    def test_verify_signature_true(self):
        payload = b'{"ref":"refs/heads/main"}'
        digest = hmac.new(
            b"secret-test",  # nosec B105 - test fixture secret only.
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={digest}"

        self.assertTrue(GitHubService().verify_signature(payload, signature))

    def test_verify_signature_false(self):
        payload = b"{}"
        self.assertFalse(GitHubService().verify_signature(payload, "sha256=wrong"))

    def test_expected_repository_matches_archideal_payload(self):
        payload = {"repository": {"full_name": "Smartappli/ArchiDEAL"}}

        self.assertTrue(GitHubService().is_expected_repository(payload))

    def test_expected_repository_rejects_legacy_dealdata_payload(self):
        payload = {"repository": {"full_name": "Smartappli/DEALData"}}

        self.assertFalse(GitHubService().is_expected_repository(payload))

    @patch("apps.gateway.services.httpx.get")
    def test_latest_commit_uses_selected_allowed_repository(self, get_mock):
        response = Mock()
        response.json.return_value = {
            "sha": "sha-test",
            "repository": {"full_name": "Smartappli/ArchiDEAL"},
            "commit": {"message": "test commit"},
        }
        get_mock.return_value = response

        result = GitHubService().latest_commit(
            branch="main",
            repository_full_name="Smartappli/ArchiDEAL",
        )

        self.assertEqual(result["sha"], "sha-test")
        self.assertIn(
            "/repos/Smartappli/ArchiDEAL/commits/main",
            get_mock.call_args.args[0],
        )
        response.raise_for_status.assert_called_once()

    @patch("apps.gateway.services.httpx.get")
    def test_latest_commit_url_encodes_branch_refs(self, get_mock):
        response = Mock()
        response.json.return_value = {
            "sha": "sha-test",
            "repository": {"full_name": "Smartappli/ArchiDEAL"},
            "commit": {"message": "test commit"},
        }
        get_mock.return_value = response

        GitHubService().latest_commit(
            branch="release/1.0",
            repository_full_name="Smartappli/ArchiDEAL",
        )

        self.assertIn(
            "/repos/Smartappli/ArchiDEAL/commits/release%2F1.0",
            get_mock.call_args.args[0],
        )

    def test_latest_commit_rejects_disallowed_repository(self):
        with self.assertRaises(ValueError):
            GitHubService().latest_commit(
                branch="main",
                repository_full_name="Other/Repo",
            )

    def test_allowed_events_are_loaded_from_repository_manifest(self):
        self.assertEqual(
            GitHubService().allowed_events_for_repository("Smartappli/ArchiDEAL"),
            ("push",),
        )

    def test_repository_integrations_summarize_manifest_links(self):
        integrations = GitHubService().repository_integrations()
        by_repository = {
            integration["repository_full_name"]: integration
            for integration in integrations
        }

        self.assertEqual(set(by_repository), {"Smartappli/ArchiDEAL"})
        self.assertTrue(by_repository["Smartappli/ArchiDEAL"]["allowed"])
        self.assertIn(
            "airflow-orchestration",
            by_repository["Smartappli/ArchiDEAL"]["module_slugs"],
        )
        self.assertIn(
            "dealdata-core-layer",
            by_repository["Smartappli/ArchiDEAL"]["public_module_slugs"],
        )
        self.assertEqual(
            by_repository["Smartappli/ArchiDEAL"]["source_dependency"]["versioning"],
            "git-sha",
        )

    def test_module_slugs_for_dealiot_push_changed_paths(self):
        payload = {
            "repository": {"full_name": "Smartappli/ArchiDEAL"},
            "commits": [
                {
                    "modified": [
                        "components/DEALIoT/mqtt-kafka-bridge/bridge.py",
                        "components/DEALIoT/apicurio/bootstrap/raw.sensor.json",
                        "components/DEALIoT/orchestration/Dockerfile",
                    ],
                    "added": [
                        "components/DEALIoT/deploy/kubernetes/base/kustomization.yaml",
                    ],
                    "removed": [],
                },
            ],
        }

        self.assertEqual(
            set(GitHubService().module_slugs_for_webhook(payload)),
            {
                "dealiot-platform",
                "schema-registry-contracts",
                "mqtt-kafka-bridge",
                "airflow-orchestration",
            },
        )

    def test_module_slug_for_path_requires_a_path_segment_boundary(self):
        service = GitHubService()
        manifest = {
            "path_mappings": [
                {"prefix": "services/api", "module_slug": "api-module"},
            ],
        }
        service.repository_manifests = [manifest]
        service.repository_manifest_map = {"example/repository": manifest}

        self.assertEqual(
            service.module_slug_for_path(
                "services/api/views.py",
                repository="example/repository",
            ),
            "api-module",
        )
        self.assertIsNone(
            service.module_slug_for_path(
                "services/api-v2/views.py",
                repository="example/repository",
            ),
        )

    def test_explicit_module_slug_is_preserved_for_manual_payloads(self):
        payload = {
            "repository": {"full_name": "Smartappli/DEALIoT"},
            "module_slug": "flink-runtime",
        }

        self.assertEqual(
            GitHubService().module_slugs_for_webhook(payload),
            ["flink-runtime"],
        )

    def test_module_slugs_for_dealdata_push_changed_paths(self):
        payload = {
            "repository": {"full_name": "Smartappli/ArchiDEAL"},
            "commits": [
                {
                    "modified": [
                        "components/DEALData/core_layer/core_data/models.py",
                        "components/DEALData/gps_layer/gps_data/models.py",
                    ],
                    "added": [
                        "components/DEALData/sensor_layer/sensor_data/models.py",
                    ],
                    "removed": [],
                },
            ],
        }

        self.assertEqual(
            set(GitHubService().module_slugs_for_webhook(payload)),
            {
                "dealdata-core-layer",
                "dealdata-gps-layer",
                "dealdata-sensor-layer",
            },
        )


@override_settings(
    APISIX=ApisixConfig(
        admin_url="http://apisix:9180",
        admin_key="test-key",
        upstream_host="django-app",
        upstream_port=8000,
    ),
)
class ApisixServiceTests(TestCase):
    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_rejects_invalid_module_slug(self, put_mock):
        with self.assertRaisesRegex(ValueError, "module_slug"):
            ApisixService().publish_route("../admin")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    @patch("apps.hosting.models.Module.objects.filter")
    def test_publish_route_does_not_hide_database_errors(self, filter_mock, put_mock):
        filter_mock.side_effect = RuntimeError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            ApisixService().publish_route("module-core")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_uses_module_routing_metadata(self, put_mock):
        response = Mock()
        response.json.return_value = {"ok": True}
        put_mock.return_value = response
        Module.objects.create(
            name="Flink",
            slug="flink-runtime",
            image="ghcr.io/smartappli/dealiot-flink-pyflink:sha-test",
            public_path="/dealiot/flink",
            upstream_host="flink-jobmanager",
            upstream_port=8081,
        )

        result = ApisixService().publish_route("flink-runtime")

        self.assertEqual(result["route_id"], "module-flink-runtime")
        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(
            payload["uris"],
            ["/dealiot/flink", "/dealiot/flink/*"],
        )
        self.assertNotIn("uri", payload)
        self.assertEqual(
            payload["plugins"]["proxy-rewrite"]["regex_uri"],
            [r"^/dealiot/flink(?:/(.*))?$", "/$1"],
        )
        self.assertEqual(
            payload["upstream"]["nodes"],
            {"flink-jobmanager:8081": 1},
        )
        response.raise_for_status.assert_called_once()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_uses_dealiot_default_route_when_module_missing(
        self,
        put_mock,
    ):
        response = Mock()
        response.json.return_value = {"ok": True}
        put_mock.return_value = response

        result = ApisixService().publish_route("schema-registry-contracts")

        self.assertEqual(result["route_id"], "module-schema-registry-contracts")
        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(
            payload["uris"],
            ["/dealiot/apicurio", "/dealiot/apicurio/*"],
        )
        self.assertEqual(
            payload["plugins"]["proxy-rewrite"]["regex_uri"],
            [r"^/dealiot/apicurio(?:/(.*))?$", "/$1"],
        )
        self.assertEqual(
            payload["upstream"]["nodes"],
            {"apicurio-registry:8080": 1},
        )

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_uses_dealdata_default_route_when_module_missing(
        self,
        put_mock,
    ):
        response = Mock()
        response.json.return_value = {"ok": True}
        put_mock.return_value = response

        result = ApisixService().publish_route("dealdata-gps-layer")

        self.assertEqual(result["route_id"], "module-dealdata-gps-layer")
        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(
            payload["uris"],
            ["/dealdata/gps", "/dealdata/gps/*"],
        )
        self.assertEqual(
            payload["plugins"]["proxy-rewrite"]["regex_uri"],
            [r"^/dealdata/gps(?:/(.*))?$", "/$1"],
        )
        self.assertEqual(
            payload["upstream"]["nodes"],
            {"dealdata-gps:7001": 1},
        )

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_dry_run_returns_payload_without_calling_apisix(
        self,
        put_mock,
    ):
        result = ApisixService().publish_route("dealdata-core-layer", dry_run=True)

        self.assertEqual(result["route_id"], "module-dealdata-core-layer")
        self.assertTrue(result["dry_run"])
        self.assertEqual(
            result["payload"]["uris"],
            ["/dealdata/core", "/dealdata/core/*"],
        )
        self.assertEqual(
            result["payload"]["plugins"]["proxy-rewrite"]["regex_uri"],
            [r"^/dealdata/core(?:/(.*))?$", "/$1"],
        )
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_keeps_prefixed_module_route_id(self, put_mock):
        result = ApisixService().publish_route("module-core", dry_run=True)

        self.assertEqual(result["route_id"], "module-core")
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_skips_known_module_without_public_upstream(self, put_mock):
        Module.objects.create(
            name="Bridge",
            slug="mqtt-kafka-bridge",
            image="ghcr.io/smartappli/dealiot-mqtt-kafka-bridge:sha-test",
        )

        result = ApisixService().publish_route("mqtt-kafka-bridge")

        self.assertTrue(result["skipped"])
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_skips_internal_dealiot_module_when_missing(self, put_mock):
        result = ApisixService().publish_route("mqtt-kafka-bridge")

        self.assertTrue(result["skipped"])
        put_mock.assert_not_called()
