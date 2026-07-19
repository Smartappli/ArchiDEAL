from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.hosting.models import HostedApplication, Module


class HostedApplicationConcurrencyTests(APITestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="application-admin",
            password="secret",  # nosec B106 - test fixture password only.
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.application = HostedApplication.objects.create(
            name="Field portal",
            slug="field-portal",
            description="Initial catalog metadata",
        )
        self.detail_url = reverse(
            "applications-detail",
            kwargs={"pk": self.application.pk},
        )

    def test_retrieve_exposes_readonly_revision_and_strong_etag(self) -> None:
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["revision"], 1)
        self.assertEqual(response["ETag"], '"1"')

        update = self.client.patch(
            self.detail_url,
            {"name": "Updated portal", "revision": 99},
            format="json",
            HTTP_IF_MATCH='"1"',
        )

        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["revision"], 2)
        self.assertEqual(update["ETag"], '"2"')
        self.application.refresh_from_db()
        self.assertEqual(self.application.revision, 2)

        replacement = self.client.put(
            self.detail_url,
            {
                "name": "Replaced portal",
                "slug": "field-portal",
                "description": "Complete replacement",
                "enabled": False,
                "revision": 500,
            },
            format="json",
            HTTP_IF_MATCH='"2"',
        )
        self.assertEqual(replacement.status_code, 200)
        self.assertEqual(replacement.data["revision"], 3)
        self.assertEqual(replacement["ETag"], '"3"')

    def test_patch_and_put_require_one_current_strong_etag(self) -> None:
        missing = self.client.patch(
            self.detail_url,
            {"description": "Unconditional overwrite"},
            format="json",
        )
        self.assertEqual(missing.status_code, 428)

        for malformed in ('W/"1"', "1", '"1", "2"', "*"):
            with self.subTest(if_match=malformed):
                response = self.client.patch(
                    self.detail_url,
                    {"description": "Malformed precondition"},
                    format="json",
                    HTTP_IF_MATCH=malformed,
                )
                self.assertEqual(response.status_code, 400)

        missing_put = self.client.put(
            self.detail_url,
            {
                "name": "Field portal",
                "slug": "field-portal",
                "description": "Unconditional replacement",
                "enabled": True,
            },
            format="json",
        )
        self.assertEqual(missing_put.status_code, 428)
        self.application.refresh_from_db()
        self.assertEqual(self.application.revision, 1)
        self.assertEqual(self.application.description, "Initial catalog metadata")

        missing_delete = self.client.delete(self.detail_url)
        self.assertEqual(missing_delete.status_code, 428)
        self.assertTrue(
            HostedApplication.objects.filter(pk=self.application.pk).exists()
        )

    @patch("apps.hosting.views.publish_event")
    def test_delete_requires_the_current_strong_etag(self, publish_event_mock) -> None:
        stale = self.client.delete(self.detail_url, HTTP_IF_MATCH='"2"')
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale["ETag"], '"1"')
        self.assertTrue(
            HostedApplication.objects.filter(pk=self.application.pk).exists()
        )
        publish_event_mock.assert_not_called()

        deleted = self.client.delete(self.detail_url, HTTP_IF_MATCH='"1"')
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(
            HostedApplication.objects.filter(pk=self.application.pk).exists()
        )
        publish_event_mock.assert_called_once()
        self.assertEqual(publish_event_mock.call_args.kwargs["data"]["revision"], 1)

    @patch("apps.hosting.views.publish_event")
    def test_stale_patch_is_rejected_and_current_patch_increments_once(
        self,
        publish_event_mock,
    ) -> None:
        first = self.client.patch(
            self.detail_url,
            {"description": "First operator"},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["revision"], 2)
        self.assertEqual(first["ETag"], '"2"')

        stale = self.client.patch(
            self.detail_url,
            {"description": "Stale operator"},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale.data["revision"], 2)
        self.assertEqual(stale["ETag"], '"2"')

        self.application.refresh_from_db()
        self.assertEqual(self.application.description, "First operator")
        self.assertEqual(self.application.revision, 2)
        publish_event_mock.assert_called_once()
        self.assertEqual(publish_event_mock.call_args.kwargs["data"]["revision"], 2)

    @patch("apps.hosting.views.publish_event")
    def test_module_membership_is_conditional_and_only_changes_revision_once(
        self,
        publish_event_mock,
    ) -> None:
        module = Module.objects.create(
            name="Telemetry",
            slug="telemetry",
            image="registry.example/telemetry:latest",
        )
        attach_url = reverse(
            "applications-attach-module",
            kwargs={"pk": self.application.pk},
        )
        detach_url = reverse(
            "applications-detach-module",
            kwargs={"pk": self.application.pk},
        )

        missing = self.client.post(
            attach_url,
            {"module_id": module.pk},
            format="json",
        )
        self.assertEqual(missing.status_code, 428)

        attached = self.client.post(
            attach_url,
            {"module_id": module.pk},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(attached.status_code, 200)
        self.assertEqual(attached.data["revision"], 2)
        self.assertEqual(attached["ETag"], '"2"')

        replay = self.client.post(
            attach_url,
            {"module_id": module.pk},
            format="json",
            HTTP_IF_MATCH='"2"',
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["revision"], 2)
        publish_event_mock.assert_called_once()

        stale = self.client.post(
            detach_url,
            {"module_id": module.pk},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale["ETag"], '"2"')

        detached = self.client.post(
            detach_url,
            {"module_id": module.pk},
            format="json",
            HTTP_IF_MATCH='"2"',
        )
        self.assertEqual(detached.status_code, 200)
        self.assertEqual(detached.data["revision"], 3)
        self.assertEqual(detached["ETag"], '"3"')
        self.assertEqual(publish_event_mock.call_count, 2)
        self.assertFalse(self.application.modules.filter(pk=module.pk).exists())

    @patch("apps.hosting.views.publish_event")
    def test_new_version_increments_revision_but_exact_replay_does_not(
        self,
        publish_event_mock,
    ) -> None:
        versions_url = reverse(
            "applications-versions",
            kwargs={"pk": self.application.pk},
        )
        payload = {
            "version": "1.2.0",
            "notes": "Signed release metadata",
            "source": "ci",
        }

        missing = self.client.post(versions_url, payload, format="json")
        self.assertEqual(missing.status_code, 428)

        for malformed in ('W/"1"', "1", '"1", "2"', "*"):
            with self.subTest(if_match=malformed):
                response = self.client.post(
                    versions_url,
                    payload,
                    format="json",
                    HTTP_IF_MATCH=malformed,
                )
                self.assertEqual(response.status_code, 400)

        created = self.client.post(
            versions_url,
            payload,
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created["ETag"], '"2"')
        self.application.refresh_from_db()
        updated_at = self.application.updated_at
        self.assertEqual(self.application.revision, 2)

        stale = self.client.post(
            versions_url,
            {**payload, "version": "1.3.0"},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale["ETag"], '"2"')
        self.assertEqual(self.application.versions.count(), 1)

        replay = self.client.post(
            versions_url,
            payload,
            format="json",
            HTTP_IF_MATCH='"2"',
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay["ETag"], '"2"')
        self.application.refresh_from_db()
        self.assertEqual(self.application.revision, 2)
        self.assertEqual(self.application.updated_at, updated_at)
        publish_event_mock.assert_called_once()
        self.assertEqual(publish_event_mock.call_args.kwargs["data"]["revision"], 2)

    @patch("apps.hosting.views.publish_event")
    def test_exact_replay_of_an_older_version_never_moves_the_catalog_back(
        self,
        publish_event_mock,
    ) -> None:
        versions_url = reverse(
            "applications-versions",
            kwargs={"pk": self.application.pk},
        )
        first_payload = {
            "version": "1.2.0",
            "notes": "First immutable release",
            "source": "ci",
        }
        second_payload = {
            "version": "1.3.0",
            "notes": "Second immutable release",
            "source": "ci",
        }

        first = self.client.post(
            versions_url,
            first_payload,
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            versions_url,
            second_payload,
            format="json",
            HTTP_IF_MATCH='"2"',
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second["ETag"], '"3"')
        self.application.refresh_from_db()
        released_at = self.application.released_at
        updated_at = self.application.updated_at

        replay = self.client.post(
            versions_url,
            first_payload,
            format="json",
            HTTP_IF_MATCH='"3"',
        )

        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(replay["ETag"], '"3"')
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_version, "1.3.0")
        self.assertEqual(self.application.revision, 3)
        self.assertEqual(self.application.released_at, released_at)
        self.assertEqual(self.application.updated_at, updated_at)
        self.assertEqual(publish_event_mock.call_count, 2)
