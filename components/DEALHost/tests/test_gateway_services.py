import hashlib
import hmac
from dataclasses import replace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.gateway.services import (
    ApisixService,
    DisabledModuleRouteError,
    GitHubService,
    MissingRoutePolicyError,
    ModuleNotProductionReadyError,
    RoutePathConflictError,
    UnsafeRoutePathError,
    UnsafeUpstreamError,
    UnknownModuleRouteError,
)
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


TEST_APISIX_CONFIG = ApisixConfig(
    admin_url="http://apisix:9180",
    admin_key="test-key",
    upstream_host="django-app",
    upstream_port=8000,
    route_allowed_upstream_hosts=(
        "dealhost",
        "dealiot",
        "django-app",
        "apicurio-registry",
        "flink-jobmanager",
        "airflow-apiserver",
        "prometheus",
        "dealdata-core",
        "dealdata-gps",
        "dealdata-sensor",
        "field-portal",
        "farm-portal",
    ),
    route_allowed_upstream_ports=(7000, 7001, 7002, 8000, 8080, 8081, 9090),
)


@override_settings(DEBUG=True, APISIX=TEST_APISIX_CONFIG)
class ApisixServiceTests(TestCase):
    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_rejects_invalid_module_slug(self, put_mock):
        with self.assertRaisesRegex(ValueError, "module_slug"):
            ApisixService().publish_route("../admin")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    @patch("apps.hosting.models.Module.objects.select_for_update")
    def test_publish_route_does_not_hide_database_errors(self, lock_mock, put_mock):
        lock_mock.side_effect = RuntimeError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            ApisixService().publish_route("module-core")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_rejects_disabled_database_module_even_with_manifest(
        self,
        put_mock,
    ):
        Module.objects.create(
            name="Disabled GPS",
            slug="dealdata-gps-layer",
            image="ghcr.io/smartappli/dealdata-gps:sha-test",
            enabled=False,
        )

        for dry_run in (False, True):
            with (
                self.subTest(dry_run=dry_run),
                self.assertRaisesRegex(
                    DisabledModuleRouteError,
                    "disabled module",
                ),
            ):
                ApisixService().publish_route(
                    "dealdata-gps-layer",
                    dry_run=dry_run,
                )

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_api_returns_conflict_for_disabled_database_module(
        self,
        put_mock,
    ):
        Module.objects.create(
            name="Disabled Core",
            slug="dealdata-core-layer",
            image="ghcr.io/smartappli/dealdata-core:sha-test",
            enabled=False,
        )

        response = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "dealdata-core-layer", "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "module_disabled")
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_rejects_unknown_module_even_for_dry_run(self, put_mock):
        for dry_run in (False, True):
            with (
                self.subTest(dry_run=dry_run),
                self.assertRaisesRegex(UnknownModuleRouteError, "Unknown module"),
            ):
                ApisixService().publish_route(
                    "not-registered",
                    dry_run=dry_run,
                )

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_api_returns_bad_request_for_unknown_module(self, put_mock):
        response = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "not-registered", "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "module_unknown")
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_cannot_replace_its_exact_bootstrap_route(self, put_mock):
        Module.objects.create(
            name="Flink",
            slug="flink-runtime",
            image="ghcr.io/smartappli/dealiot-flink-pyflink:sha-test",
            public_path="/dealiot/flink",
            upstream_host="flink-jobmanager",
            upstream_port=8081,
        )

        with self.assertRaisesRegex(RoutePathConflictError, "bootstrap route"):
            ApisixService().publish_route("flink-runtime")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_cannot_recreate_dealiot_bootstrap_route_when_missing(
        self,
        put_mock,
    ):
        with self.assertRaisesRegex(RoutePathConflictError, "bootstrap route"):
            ApisixService().publish_route("schema-registry-contracts")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_cannot_recreate_dealdata_bootstrap_route_when_missing(
        self,
        put_mock,
    ):
        with self.assertRaisesRegex(RoutePathConflictError, "bootstrap route"):
            ApisixService().publish_route("dealdata-gps-layer")

        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_dry_run_returns_payload_without_calling_apisix(
        self,
        put_mock,
    ):
        Module.objects.create(
            name="Route preview",
            slug="route-preview",
            image="ghcr.io/smartappli/route-preview:sha-test",
            public_path="/preview",
            upstream_host="field-portal",
            upstream_port=8080,
        )
        result = ApisixService().publish_route("route-preview", dry_run=True)

        self.assertEqual(result["route_id"], "module-route-preview")
        self.assertTrue(result["dry_run"])
        self.assertEqual(
            result["payload"]["uris"],
            ["/preview", "/preview/*"],
        )
        self.assertEqual(
            result["payload"]["plugins"]["proxy-rewrite"]["regex_uri"],
            [r"^/preview(?:/(.*))?$", "/$1"],
        )
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_route_preview_returns_a_deterministic_strong_etag(self, put_mock):
        Module.objects.create(
            name="Route preview",
            slug="route-preview",
            image="ghcr.io/smartappli/route-preview:sha-test",
            public_path="/preview",
            upstream_host="field-portal",
            upstream_port=8080,
        )
        first = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "route-preview", "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )
        second = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "route-preview", "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertRegex(first.json()["etag"], r'^"sha256-[0-9a-f]{64}"$')
        self.assertEqual(first["ETag"], first.json()["etag"])
        self.assertEqual(second.json()["etag"], first.json()["etag"])
        self.assertEqual(second.json()["payload"], first.json()["payload"])
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_operator_publication_requires_a_preview_etag(self, put_mock):
        response = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "dealdata-core-layer", "dry_run": False},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 428)
        self.assertEqual(response.json()["code"], "route_preview_required")
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_operator_publication_rejects_malformed_or_weak_etags(self, put_mock):
        invalid_etags = (
            'W/"sha256-' + ("a" * 64) + '"',
            '"not-a-route-digest"',
            "*",
            '"sha256-' + ("a" * 64) + '", "sha256-' + ("b" * 64) + '"',
        )

        for invalid_etag in invalid_etags:
            with self.subTest(etag=invalid_etag):
                response = self.client.post(
                    reverse("apisix-publish"),
                    data={"module_slug": "dealdata-core-layer", "dry_run": False},
                    content_type="application/json",
                    HTTP_AUTHORIZATION="Bearer test-admin-token",
                    HTTP_IF_MATCH=invalid_etag,
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["code"],
                    "route_preview_etag_invalid",
                )
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_operator_publication_rejects_a_stale_route_preview(self, put_mock):
        module = Module.objects.create(
            name="Field portal",
            slug="field-portal",
            image="ghcr.io/smartappli/field-portal:sha-test",
            public_path="/field",
            upstream_host="field-portal",
            upstream_port=8080,
        )
        preview = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": module.slug, "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )
        module.upstream_port = 8081
        module.save(update_fields=["upstream_port"])

        response = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": module.slug, "dry_run": False},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
            HTTP_IF_MATCH=preview["ETag"],
        )

        self.assertEqual(response.status_code, 412)
        self.assertEqual(response.json()["code"], "route_preview_stale")
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_preview_for_another_module_cannot_authorize_publication(self, put_mock):
        for slug, public_path in (
            ("field-portal", "/field"),
            ("farm-portal", "/farm"),
        ):
            Module.objects.create(
                name=slug,
                slug=slug,
                image=f"ghcr.io/smartappli/{slug}:sha-test",
                public_path=public_path,
                upstream_host=slug,
                upstream_port=8080,
            )
        preview = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "field-portal", "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        response = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": "farm-portal", "dry_run": False},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
            HTTP_IF_MATCH=preview["ETag"],
        )

        self.assertEqual(response.status_code, 412)
        self.assertEqual(response.json()["code"], "route_preview_stale")
        put_mock.assert_not_called()

    @patch("apps.gateway.services.httpx.put")
    def test_conditional_publication_sends_the_exact_previewed_payload(self, put_mock):
        response = Mock()
        response.json.return_value = {"value": {"id": "module-field-portal"}}
        put_mock.return_value = response
        module = Module.objects.create(
            name="Field portal",
            slug="field-portal",
            image="ghcr.io/smartappli/field-portal:sha-test",
            public_path="/field",
            upstream_host="field-portal",
            upstream_port=8080,
        )
        preview = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": module.slug, "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        published = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": module.slug, "dry_run": False},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
            HTTP_IF_MATCH=preview["ETag"],
        )

        self.assertEqual(published.status_code, 201)
        self.assertEqual(published["ETag"], preview["ETag"])
        self.assertEqual(published.json()["etag"], preview.json()["etag"])
        self.assertEqual(put_mock.call_args.kwargs["json"], preview.json()["payload"])
        response.raise_for_status.assert_called_once()

    @override_settings(
        DEBUG=False,
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstreams=("dealdata-core:7000",),
        ),
    )
    @patch("apps.gateway.services.httpx.put")
    def test_production_non_introspecting_route_strips_all_identity_headers(
        self,
        put_mock,
    ):
        module = Module.objects.create(
            name="Analytics extension",
            slug="analytics-extension",
            image="ghcr.io/smartappli/analytics-extension:sha-test",
            public_path="/analytics-extension",
            upstream_host="dealdata-core",
            upstream_port=7000,
        )
        service = ApisixService()
        service.module_manifests[module.slug] = {
            "slug": module.slug,
            "production_ready": True,
        }
        result = service.publish_route(module.slug, dry_run=True)

        payload = result["payload"]
        self.assertEqual(payload["priority"], 100)
        self.assertEqual(
            payload["plugins"],
            {
                "prometheus": {},
                "opentelemetry": {"sampler": {"name": "always_on"}},
                "proxy-rewrite": {
                    "regex_uri": [
                        r"^/analytics\-extension(?:/(.*))?$",
                        "/$1",
                    ],
                    "host": "dealdata-core",
                    "headers": {
                        "set": {
                            "X-Forwarded-Proto": "$http_x_forwarded_proto",
                        },
                        "remove": [
                            "Authorization",
                            "X-Forwarded-Access-Token",
                        ],
                    },
                },
            },
        )
        self.assertEqual(payload["upstream"]["pass_host"], "node")
        put_mock.assert_not_called()

    @override_settings(
        DEBUG=False,
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstreams=("dealhost:8000",),
        ),
    )
    def test_production_introspecting_route_exchanges_then_strips_raw_token(self):
        module = Module.objects.create(
            name="Operator extension",
            slug="operator-extension",
            image="ghcr.io/smartappli/operator-extension:sha-test",
            public_path="/operator-extension",
            upstream_host="dealhost",
            upstream_port=8000,
        )
        service = ApisixService()
        service.module_manifests[module.slug] = {
            "slug": module.slug,
            "production_ready": True,
        }

        result = service.publish_route(module.slug, dry_run=True)

        headers = result["payload"]["plugins"]["proxy-rewrite"]["headers"]
        self.assertEqual(
            headers,
            {
                "set": {
                    "X-Forwarded-Proto": "$http_x_forwarded_proto",
                    "Authorization": "Bearer $http_x_forwarded_access_token",
                },
                "remove": ["X-Forwarded-Access-Token"],
            },
        )

    @override_settings(DEBUG=False)
    @patch("apps.gateway.services.httpx.put")
    def test_production_rejects_module_without_explicit_readiness(self, put_mock):
        module = Module.objects.create(
            name="Unreviewed extension",
            slug="unreviewed-extension",
            image="ghcr.io/smartappli/unreviewed-extension:sha-test",
            public_path="/unreviewed-extension",
            upstream_host="dealhost",
            upstream_port=8000,
        )

        with self.assertRaisesRegex(
            ModuleNotProductionReadyError,
            "production_ready=true",
        ):
            ApisixService().publish_route(module.slug, dry_run=True)

        put_mock.assert_not_called()

    @override_settings(DEBUG=False)
    @patch("apps.gateway.services.httpx.put")
    def test_production_api_reports_readiness_conflict(self, put_mock):
        module = Module.objects.create(
            name="Unreviewed API extension",
            slug="unreviewed-api-extension",
            image="ghcr.io/smartappli/unreviewed-api-extension:sha-test",
            public_path="/unreviewed-api-extension",
            upstream_host="dealhost",
            upstream_port=8000,
        )

        response = self.client.post(
            reverse("apisix-publish"),
            data={"module_slug": module.slug, "dry_run": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "module_not_production_ready")
        put_mock.assert_not_called()

    @override_settings(DEBUG=True)
    @patch("apps.gateway.services.httpx.put")
    def test_development_route_preserves_existing_authorization_and_skips_otel(
        self,
        put_mock,
    ):
        module = Module.objects.create(
            name="Development extension",
            slug="development-extension",
            image="ghcr.io/smartappli/development-extension:sha-test",
            public_path="/development-extension",
            upstream_host="dealdata-core",
            upstream_port=7000,
        )
        result = ApisixService().publish_route(module.slug, dry_run=True)

        plugins = result["payload"]["plugins"]
        self.assertEqual(set(plugins), {"proxy-rewrite"})
        self.assertNotIn("headers", plugins["proxy-rewrite"])
        self.assertEqual(plugins["proxy-rewrite"]["host"], "dealdata-core")
        put_mock.assert_not_called()

    @override_settings(
        DEBUG=True,
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstream_hosts=(),
            route_allowed_upstream_ports=(),
        ),
    )
    def test_development_derives_policy_from_trusted_manifest_routes(self):
        hosts, suffixes, ports, exact_pairs = ApisixService()._upstream_policy()

        self.assertIn("dealdata-core", hosts)
        self.assertIn(7000, ports)
        self.assertFalse(suffixes)
        self.assertFalse(exact_pairs)

    @override_settings(
        DEBUG=False,
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstream_hosts=(),
            route_allowed_upstream_ports=(),
            route_allowed_upstreams=(),
        ),
    )
    def test_production_fails_closed_when_route_policy_is_missing(self):
        module = Module.objects.create(
            name="Ready extension",
            slug="ready-extension",
            image="ghcr.io/smartappli/ready-extension:sha-test",
            public_path="/ready-extension",
            upstream_host="dealhost",
            upstream_port=8000,
        )
        service = ApisixService()
        service.module_manifests[module.slug] = {
            "slug": module.slug,
            "production_ready": True,
        }
        with self.assertRaisesRegex(
            MissingRoutePolicyError,
            "exact host:port",
        ):
            service.publish_route(module.slug, dry_run=True)

    def test_database_route_cannot_claim_reserved_system_namespaces(self):
        module = Module.objects.create(
            name="Unsafe portal",
            slug="unsafe-portal",
            image="ghcr.io/smartappli/unsafe-portal:sha-test",
            public_path="/field",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        for public_path in (
            "/oauth2",
            "/oauth2/callback",
            "/healthz/internal",
            "/readyz",
            "/apisix/admin",
            "/dealhost/api",
            "/dealiot/custom",
            "/dealdata/core",
        ):
            with self.subTest(public_path=public_path):
                module.public_path = public_path
                module.save(update_fields=["public_path"])

                with self.assertRaises((RoutePathConflictError, UnsafeRoutePathError)):
                    ApisixService().publish_route(module.slug, dry_run=True)

    def test_manifest_route_is_always_owned_by_bootstrap_even_when_exact(self):
        module = Module.objects.create(
            name="GPS route override",
            slug="dealdata-gps-layer",
            image="ghcr.io/smartappli/dealdata-gps:sha-test",
            public_path="/dealdata/gps",
            upstream_host="dealdata-gps",
            upstream_port=7001,
        )

        with self.assertRaisesRegex(RoutePathConflictError, "bootstrap route"):
            ApisixService().publish_route(module.slug, dry_run=True)

        overrides = (
            ("/dealdata/gps-v2", "dealdata-gps", 7001),
            ("/dealdata/gps", "dealdata-core", 7001),
            ("/dealdata/gps", "dealdata-gps", 7000),
        )
        for public_path, upstream_host, upstream_port in overrides:
            with self.subTest(
                public_path=public_path,
                upstream_host=upstream_host,
                upstream_port=upstream_port,
            ):
                module.public_path = public_path
                module.upstream_host = upstream_host
                module.upstream_port = upstream_port
                module.save(
                    update_fields=["public_path", "upstream_host", "upstream_port"],
                )

                with self.assertRaises((RoutePathConflictError, UnsafeRoutePathError)):
                    ApisixService().publish_route(module.slug, dry_run=True)

    def test_reserved_prefix_check_uses_path_segment_boundaries(self):
        Module.objects.create(
            name="DEAL tools",
            slug="deal-tools",
            image="ghcr.io/smartappli/deal-tools:sha-test",
            public_path="/dealiot-tools",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        result = ApisixService().publish_route("deal-tools", dry_run=True)

        self.assertEqual(
            result["payload"]["uris"],
            ["/dealiot-tools", "/dealiot-tools/*"],
        )

    def test_route_rejects_ambiguous_or_encoded_paths(self):
        module = Module.objects.create(
            name="Unsafe syntax portal",
            slug="unsafe-syntax-portal",
            image="ghcr.io/smartappli/unsafe-syntax-portal:sha-test",
            public_path="/field",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        for public_path in (
            "/",
            "//field",
            "/field//admin",
            "/field/../admin",
            "/field%2fadmin",
            "/field\\admin",
            "/field?admin=true",
        ):
            with self.subTest(public_path=public_path):
                module.public_path = public_path
                module.save(update_fields=["public_path"])

                with self.assertRaises(UnsafeRoutePathError):
                    ApisixService().publish_route(module.slug, dry_run=True)

    def test_route_rejects_exact_parent_and_child_module_path_overlaps(self):
        Module.objects.create(
            name="Existing tenant apps",
            slug="existing-tenant-apps",
            image="ghcr.io/smartappli/existing-tenant-apps:sha-test",
            public_path="/tenant/apps",
            upstream_host="farm-portal",
            upstream_port=8080,
        )
        candidate = Module.objects.create(
            name="Candidate tenant app",
            slug="candidate-tenant-app",
            image="ghcr.io/smartappli/candidate-tenant-app:sha-test",
            public_path="/candidate",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        for public_path in ("/tenant/apps", "/tenant", "/tenant/apps/v2"):
            with self.subTest(public_path=public_path):
                candidate.public_path = public_path
                candidate.save(update_fields=["public_path"])

                with self.assertRaises(RoutePathConflictError):
                    ApisixService().publish_route(candidate.slug, dry_run=True)

    def test_route_rejects_parent_or_child_overlap_with_bootstrap_route(self):
        module = Module.objects.create(
            name="Core shadow",
            slug="core-shadow",
            image="ghcr.io/smartappli/core-shadow:sha-test",
            public_path="/core/admin",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        with self.assertRaisesRegex(RoutePathConflictError, "bootstrap route"):
            ApisixService().publish_route(module.slug, dry_run=True)

    def test_route_rejects_ip_localhost_metacharacter_and_unlisted_hosts(self):
        module = Module.objects.create(
            name="Unsafe upstream",
            slug="unsafe-upstream",
            image="ghcr.io/smartappli/unsafe-upstream:sha-test",
            public_path="/unsafe-upstream",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        for upstream_host in (
            "127.0.0.1",
            "2130706433",
            "localhost",
            "api.localhost",
            "field_portal",
            "field-portal:8080",
            "unlisted-service",
        ):
            with self.subTest(upstream_host=upstream_host):
                module.upstream_host = upstream_host
                module.save(update_fields=["upstream_host"])

                with self.assertRaises(UnsafeUpstreamError):
                    ApisixService().publish_route(module.slug, dry_run=True)

    def test_route_rejects_unlisted_upstream_port(self):
        Module.objects.create(
            name="Unsafe upstream port",
            slug="unsafe-upstream-port",
            image="ghcr.io/smartappli/unsafe-upstream-port:sha-test",
            public_path="/unsafe-upstream-port",
            upstream_host="field-portal",
            upstream_port=4444,
        )

        with self.assertRaisesRegex(UnsafeUpstreamError, "port.*allowlist"):
            ApisixService().publish_route("unsafe-upstream-port", dry_run=True)

    @override_settings(
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstream_hosts=("field-portal", "farm-portal"),
            route_allowed_upstream_ports=(8000, 8080),
            route_allowed_upstreams=("field-portal:8080",),
        ),
    )
    def test_route_requires_an_exact_host_port_pair_when_configured(self):
        module = Module.objects.create(
            name="Cross product target",
            slug="cross-product-target",
            image="ghcr.io/smartappli/cross-product-target:sha-test",
            public_path="/cross-product-target",
            upstream_host="farm-portal",
            upstream_port=8080,
        )

        with self.assertRaisesRegex(UnsafeUpstreamError, "exact route allowlist"):
            ApisixService().publish_route(module.slug, dry_run=True)

        module.upstream_host = "field-portal"
        module.save(update_fields=["upstream_host"])
        result = ApisixService().publish_route(module.slug, dry_run=True)
        self.assertEqual(
            result["payload"]["upstream"]["nodes"],
            {"field-portal:8080": 1},
        )

    @override_settings(
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstreams=("field-portal:08080",),
        ),
    )
    def test_exact_upstream_allowlist_requires_canonical_pairs(self):
        module = Module.objects.create(
            name="Canonical target",
            slug="canonical-target",
            image="ghcr.io/smartappli/canonical-target:sha-test",
            public_path="/canonical-target",
            upstream_host="field-portal",
            upstream_port=8080,
        )

        with self.assertRaisesRegex(UnsafeUpstreamError, "canonical host:port"):
            ApisixService().publish_route(module.slug, dry_run=True)

    @override_settings(
        APISIX=replace(
            TEST_APISIX_CONFIG,
            route_allowed_upstream_hosts=(),
            route_allowed_upstream_suffixes=("services.example",),
            route_allowed_upstream_ports=(8443,),
        ),
    )
    def test_route_allows_only_dns_boundary_matches_for_approved_suffixes(self):
        module = Module.objects.create(
            name="Approved service",
            slug="approved-service",
            image="ghcr.io/smartappli/approved-service:sha-test",
            public_path="/approved-service",
            upstream_host="api.services.example",
            upstream_port=8443,
        )

        result = ApisixService().publish_route(module.slug, dry_run=True)
        self.assertEqual(
            result["payload"]["upstream"]["nodes"],
            {"api.services.example:8443": 1},
        )

        module.upstream_host = "evilservices.example"
        module.save(update_fields=["upstream_host"])
        with self.assertRaisesRegex(UnsafeUpstreamError, "not in"):
            ApisixService().publish_route(module.slug, dry_run=True)

    @patch("apps.gateway.services.httpx.put")
    def test_publish_route_keeps_prefixed_module_route_id(self, put_mock):
        Module.objects.create(
            name="Prefixed module",
            slug="module-custom",
            image="ghcr.io/smartappli/module-custom:sha-test",
            public_path="/module-custom",
            upstream_host="field-portal",
            upstream_port=8080,
        )
        result = ApisixService().publish_route("module-custom", dry_run=True)

        self.assertEqual(result["route_id"], "module-custom")
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
