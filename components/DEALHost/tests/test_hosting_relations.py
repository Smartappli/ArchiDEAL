from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

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

    def test_application_version_rejects_invalid_semver(self) -> None:
        url = reverse("applications-versions", kwargs={"pk": self.application.pk})
        response = self.client.post(url, {"version": "2026"}, format="json")
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
