from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.hosting.models import HostedApplication, Module, Tool


class HostingRelationsTests(TestCase):
    def test_tool_and_application_can_share_multiple_modules(self) -> None:
        module_auth = Module.objects.create(
            name="Auth",
            slug="auth",
            image="registry.example/auth:latest",
            branch="main",
            enabled=True,
        )
        module_billing = Module.objects.create(
            name="Billing",
            slug="billing",
            image="registry.example/billing:latest",
            branch="main",
            enabled=True,
        )

        tool = Tool.objects.create(name="Backoffice", slug="backoffice")
        app = HostedApplication.objects.create(name="Storefront", slug="storefront")

        tool.modules.set([module_auth, module_billing])
        app.modules.set([module_auth, module_billing])

        self.assertEqual(tool.modules.count(), 2)
        self.assertEqual(app.modules.count(), 2)


class HostingManagementApiTests(APITestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="api-admin",
            password="secret",  # nosec B106 - test fixture password only.
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.module_auth = Module.objects.create(
            name="Auth",
            slug="auth",
            image="registry.example/auth:latest",
            branch="main",
            enabled=True,
        )
        self.module_billing = Module.objects.create(
            name="Billing",
            slug="billing",
            image="registry.example/billing:latest",
            branch="main",
            enabled=True,
        )
        self.tool = Tool.objects.create(name="Backoffice", slug="backoffice")
        self.application = HostedApplication.objects.create(
            name="Storefront",
            slug="storefront",
        )

    def test_tool_attach_and_detach_module(self) -> None:
        attach_url = reverse("tools-attach-module", kwargs={"pk": self.tool.pk})
        detach_url = reverse("tools-detach-module", kwargs={"pk": self.tool.pk})

        attach_response = self.client.post(
            attach_url,
            {"module_id": self.module_auth.pk},
            format="json",
        )
        self.assertEqual(attach_response.status_code, 200)
        self.assertEqual(len(attach_response.data["modules"]), 1)

        detach_response = self.client.post(
            detach_url,
            {"module_id": self.module_auth.pk},
            format="json",
        )
        self.assertEqual(detach_response.status_code, 200)
        self.assertEqual(len(detach_response.data["modules"]), 0)

    def test_application_filter_by_module_slug(self) -> None:
        self.application.modules.add(self.module_billing)
        url = reverse("applications-list")
        response = self.client.get(url, {"module_slug": "billing"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "storefront")

    def test_routable_module_cannot_be_disabled_or_retargeted_without_unpublish(
        self,
    ) -> None:
        module = Module.objects.create(
            name="Published candidate",
            slug="published-candidate",
            image="registry.example/published-candidate:latest",
            public_path="/published-candidate",
            upstream_host="dealhost",
            upstream_port=8000,
            enabled=True,
        )
        url = reverse("modules-detail", kwargs={"pk": module.pk})

        mutations = (
            {"enabled": False},
            {"slug": "renamed-candidate"},
            {"public_path": "/renamed-candidate"},
            {"upstream_host": "dealiot"},
            {"upstream_port": 8080},
        )
        for payload in mutations:
            with self.subTest(payload=payload):
                response = self.client.patch(url, payload, format="json")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(
                    response.data["code"],
                    "route_revocation_unavailable",
                )

        module.refresh_from_db()
        self.assertTrue(module.enabled)
        self.assertEqual(module.slug, "published-candidate")
        self.assertEqual(module.public_path, "/published-candidate")
        self.assertEqual(module.upstream_host, "dealhost")
        self.assertEqual(module.upstream_port, 8000)

    def test_routable_module_delete_is_blocked_without_audited_unpublish(self) -> None:
        module = Module.objects.create(
            name="Deletion candidate",
            slug="deletion-candidate",
            image="registry.example/deletion-candidate:latest",
            public_path="/deletion-candidate",
            upstream_host="dealhost",
            upstream_port=8000,
        )

        response = self.client.delete(
            reverse("modules-detail", kwargs={"pk": module.pk}),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "route_revocation_unavailable")
        self.assertTrue(Module.objects.filter(pk=module.pk).exists())

    def test_non_routable_module_can_still_be_deleted(self) -> None:
        module = Module.objects.create(
            name="Internal worker",
            slug="internal-worker",
            image="registry.example/internal-worker:latest",
        )

        response = self.client.delete(
            reverse("modules-detail", kwargs={"pk": module.pk}),
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Module.objects.filter(pk=module.pk).exists())

    def test_tool_version_lifecycle_endpoint(self) -> None:
        url = reverse("tools-versions", kwargs={"pk": self.tool.pk})

        create_response = self.client.post(
            url,
            {"version": "1.2.0", "notes": "Minor release", "source": "manual"},
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.current_version, "1.2.0")

        list_response = self.client.get(url)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["version"], "1.2.0")

    def test_catalog_updates_cannot_forge_release_state(self) -> None:
        released_at = "2026-07-19T12:00:00Z"

        for route_name, resource in (
            ("tools-detail", self.tool),
            ("applications-detail", self.application),
        ):
            with self.subTest(route_name=route_name):
                headers = (
                    {"HTTP_IF_MATCH": '"1"'}
                    if isinstance(resource, HostedApplication)
                    else {}
                )
                response = self.client.patch(
                    reverse(route_name, kwargs={"pk": resource.pk}),
                    {
                        "current_version": "9.9.9",
                        "released_at": released_at,
                    },
                    format="json",
                    **headers,
                )

                self.assertEqual(response.status_code, 200)
                resource.refresh_from_db()
                self.assertEqual(resource.current_version, "0.1.0")
                self.assertIsNone(resource.released_at)

    @patch("apps.hosting.views.publish_event")
    def test_tool_version_publication_is_immutable_and_idempotent(
        self,
        publish_event_mock,
    ) -> None:
        self._assert_immutable_version_contract(
            route_name="tools-versions",
            resource=self.tool,
            publish_event_mock=publish_event_mock,
        )

    @patch("apps.hosting.views.publish_event")
    def test_application_version_publication_is_immutable_and_idempotent(
        self,
        publish_event_mock,
    ) -> None:
        self._assert_immutable_version_contract(
            route_name="applications-versions",
            resource=self.application,
            publish_event_mock=publish_event_mock,
        )

    def _assert_immutable_version_contract(
        self,
        *,
        route_name,
        resource,
        publish_event_mock,
    ) -> None:
        url = reverse(route_name, kwargs={"pk": resource.pk})
        payload = {
            "version": "v2.4.0",
            "notes": "Signed release metadata",
            "source": "ci",
        }
        headers = (
            {"HTTP_IF_MATCH": f'"{resource.revision}"'}
            if isinstance(resource, HostedApplication)
            else {}
        )

        created = self.client.post(url, payload, format="json", **headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["version"], "2.4.0")
        resource.refresh_from_db()
        released_at = resource.released_at
        updated_at = resource.updated_at
        self.assertIsNotNone(released_at)
        self.assertEqual(resource.current_version, "2.4.0")
        self.assertEqual(resource.versions.count(), 1)
        publish_event_mock.assert_called_once()

        replayed = self.client.post(
            url,
            {**payload, "version": "2.4.0"},
            format="json",
            **(
                {"HTTP_IF_MATCH": f'"{resource.revision}"'}
                if isinstance(resource, HostedApplication)
                else {}
            ),
        )
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.data["id"], created.data["id"])
        resource.refresh_from_db()
        self.assertEqual(resource.released_at, released_at)
        self.assertEqual(resource.updated_at, updated_at)
        self.assertEqual(resource.versions.count(), 1)
        publish_event_mock.assert_called_once()

        for changed_field, changed_value in (
            ("notes", "Replacement notes"),
            ("source", "manual"),
        ):
            with self.subTest(changed_field=changed_field):
                conflict = self.client.post(
                    url,
                    {**payload, "version": "2.4.0", changed_field: changed_value},
                    format="json",
                    **(
                        {"HTTP_IF_MATCH": f'"{resource.revision}"'}
                        if isinstance(resource, HostedApplication)
                        else {}
                    ),
                )
                self.assertEqual(conflict.status_code, 409)
                self.assertEqual(conflict.data["code"], "version_conflict")

        version = resource.versions.get()
        self.assertEqual(version.notes, payload["notes"])
        self.assertEqual(version.source, payload["source"])
        self.assertEqual(resource.versions.count(), 1)
        publish_event_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_tool_publication_rolls_back_if_catalog_pointer_cannot_be_saved(
        self,
        publish_event_mock,
    ) -> None:
        url = reverse("tools-versions", kwargs={"pk": self.tool.pk})

        with patch.object(Tool, "save", side_effect=RuntimeError("save failed")):
            with self.assertRaisesRegex(RuntimeError, "save failed"):
                self.client.post(url, {"version": "4.0.0"}, format="json")

        self.tool.refresh_from_db()
        self.assertEqual(self.tool.current_version, "0.1.0")
        self.assertIsNone(self.tool.released_at)
        self.assertEqual(self.tool.versions.count(), 0)
        publish_event_mock.assert_not_called()

    @patch("apps.hosting.views.publish_event")
    def test_application_publication_rolls_back_if_catalog_pointer_cannot_be_saved(
        self,
        publish_event_mock,
    ) -> None:
        url = reverse("applications-versions", kwargs={"pk": self.application.pk})

        with patch.object(
            HostedApplication,
            "save",
            side_effect=RuntimeError("save failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "save failed"):
                self.client.post(
                    url,
                    {"version": "4.0.0"},
                    format="json",
                    HTTP_IF_MATCH='"1"',
                )

        self.application.refresh_from_db()
        self.assertEqual(self.application.current_version, "0.1.0")
        self.assertIsNone(self.application.released_at)
        self.assertEqual(self.application.versions.count(), 0)
        publish_event_mock.assert_not_called()

    def test_application_version_rejects_invalid_semver(self) -> None:
        url = reverse("applications-versions", kwargs={"pk": self.application.pk})
        response = self.client.post(
            url,
            {"version": "2026"},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("version", response.data)


class HostingApiSecurityTests(APITestCase):
    def test_modules_api_rejects_anonymous_requests(self) -> None:
        response = self.client.get(reverse("modules-list"))

        self.assertIn(response.status_code, {401, 403})

    def test_modules_api_allows_readonly_bearer_token_for_reads(self) -> None:
        Module.objects.create(
            name="Core",
            slug="core",
            image="registry.example/core:1.0.0",
        )

        response = self.client.get(
            reverse("modules-list"),
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["slug"], "core")

    def test_modules_api_rejects_readonly_bearer_token_for_writes(self) -> None:
        response = self.client.post(
            reverse("modules-list"),
            {"name": "Core", "slug": "core", "image": "registry.example/core:1.0.0"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Module.objects.filter(slug="core").exists())

    def test_modules_api_allows_admin_bearer_token_for_writes(self) -> None:
        response = self.client.post(
            reverse("modules-list"),
            {"name": "Core", "slug": "core", "image": "registry.example/core:1.0.0"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Module.objects.filter(slug="core").exists())
