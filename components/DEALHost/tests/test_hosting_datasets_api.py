from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.common.authentication import SettingsTokenUser
from apps.hosting.models import Dataset, Module
from apps.iam.services import provision_oidc_acl_identity


class DatasetApiAccessTests(APITestCase):
    def setUp(self) -> None:
        self.group = Group.objects.create(name="analysts")
        self.other_group = Group.objects.create(name="auditors")
        self.user = get_user_model().objects.create_user(
            username="alice",
            password="secret",  # nosec B106 - test fixture password only.
        )
        self.user.groups.add(self.group)
        self.other_user = get_user_model().objects.create_user(
            username="bob",
            password="secret",  # nosec B106 - test fixture password only.
        )
        self.module = Module.objects.create(
            name="DEALData Core",
            slug="dealdata-core",
            image="registry.example/dealdata-core:1.0.0",
        )

        self.direct = Dataset.objects.create(
            name="Direct dataset",
            slug="direct",
            enabled=True,
        )
        self.direct.users.add(self.user)
        self.direct.modules.add(self.module)

        self.group_dataset = Dataset.objects.create(
            name="Group dataset",
            slug="group",
            enabled=True,
        )
        self.group_dataset.groups.add(self.group)

        self.private = Dataset.objects.create(
            name="Private dataset",
            slug="private",
            enabled=True,
        )
        self.private.users.add(self.other_user)

        self.disabled = Dataset.objects.create(
            name="Disabled dataset",
            slug="disabled",
            enabled=False,
        )
        self.disabled.users.add(self.user)

    def test_anonymous_reader_is_rejected(self) -> None:
        response = self.client.get(reverse("datasets-list"))

        self.assertIn(response.status_code, {401, 403})

    def test_non_staff_reader_only_sees_enabled_assigned_datasets(self) -> None:
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse("datasets-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {dataset["slug"] for dataset in response.data},
            {"direct", "group"},
        )
        self.assertNotIn("user_ids", response.data[0])
        self.assertNotIn("group_ids", response.data[0])

    def test_non_staff_reader_cannot_enumerate_inaccessible_dataset(self) -> None:
        self.client.force_authenticate(self.user)

        response = self.client.get(
            reverse("datasets-detail", kwargs={"pk": self.private.pk}),
        )

        self.assertEqual(response.status_code, 404)

    def test_non_staff_reader_cannot_write(self) -> None:
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse("datasets-list"),
            {"name": "Created", "slug": "created"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Dataset.objects.filter(slug="created").exists())

    def test_readonly_bearer_without_local_acl_identity_sees_empty_list(self) -> None:
        response = self.client.get(
            reverse("datasets-list"),
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_readonly_bearer_uses_matching_active_local_account_acl(self) -> None:
        token_user = get_user_model().objects.create_user(
            username="dealhost-api-token",
            password="secret",  # nosec B106 - test fixture password only.
        )
        self.direct.users.add(token_user)

        response = self.client.get(
            reverse("datasets-list"),
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.data], ["direct"])

    def test_oidc_reader_uses_stable_subject_and_external_group_acl(self) -> None:
        token_user = SettingsTokenUser(
            username="renamable-display-name",
            oidc_issuer="https://identity.example.test",
            oidc_subject="subject-123",
            oidc_groups=frozenset({self.other_group.name}),
        )
        local_identity = get_user_model().objects.create_user(
            username=token_user.acl_username,
            password="secret",  # nosec B106 - test fixture password only.
        )
        self.direct.users.add(local_identity)
        self.private.groups.add(self.other_group)
        self.client.force_authenticate(token_user)

        response = self.client.get(reverse("datasets-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["slug"] for item in response.data},
            {"direct", "private"},
        )
        self.assertTrue(token_user.acl_username.startswith("oidc:"))
        self.assertNotIn("renamable-display-name", token_user.acl_username)

    @override_settings(
        DEALHOST_OIDC_ISSUER="https://identity.example.test/realms/archideal"
    )
    def test_provisioned_oidc_identity_grants_the_matching_runtime_user(self) -> None:
        issuer = "https://identity.example.test/realms/archideal"
        subject = "provisioned-subject-123"
        provisioned = provision_oidc_acl_identity(
            issuer=issuer,
            subject=subject,
            display_name="Provisioned reader",
            email="reader@example.test",
        )
        self.direct.users.add(provisioned.identity.user)
        runtime_user = SettingsTokenUser(
            username="mutable-display-name",
            oidc_issuer=issuer,
            oidc_subject=subject,
        )
        self.client.force_authenticate(runtime_user)

        response = self.client.get(reverse("datasets-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.data], ["direct"])
        self.assertEqual(
            provisioned.identity.user.username,
            runtime_user.acl_username,
        )
        self.assertFalse(provisioned.identity.user.has_usable_password())

    def test_non_staff_filters_stay_within_accessible_scope(self) -> None:
        self.client.force_authenticate(self.user)

        module_response = self.client.get(
            reverse("datasets-list"),
            {"module_slug": self.module.slug},
        )
        disabled_response = self.client.get(
            reverse("datasets-list"),
            {"enabled": "false"},
        )

        self.assertEqual(module_response.status_code, 200)
        self.assertEqual([item["slug"] for item in module_response.data], ["direct"])
        self.assertEqual(disabled_response.status_code, 200)
        self.assertEqual(disabled_response.data, [])


class DatasetApiStaffTests(APITestCase):
    def setUp(self) -> None:
        self.staff = get_user_model().objects.create_user(
            username="staff",
            password="secret",  # nosec B106 - test fixture password only.
            is_staff=True,
        )
        self.reader = get_user_model().objects.create_user(
            username="reader",
            password="secret",  # nosec B106 - test fixture password only.
        )
        self.group = Group.objects.create(name="analysts")
        self.module = Module.objects.create(
            name="DEALData Core",
            slug="dealdata-core",
            image="registry.example/dealdata-core:1.0.0",
        )
        self.client.force_authenticate(self.staff)

    def test_staff_can_create_and_update_dataset_acl(self) -> None:
        create_response = self.client.post(
            reverse("datasets-list"),
            {
                "name": "Telemetry",
                "slug": "telemetry",
                "description": "Governed telemetry",
                "module_ids": [self.module.pk],
                "user_ids": [self.reader.pk],
                "group_ids": [self.group.pk],
                "enabled": True,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["user_ids"], [self.reader.pk])
        self.assertEqual(create_response.data["group_ids"], [self.group.pk])
        dataset = Dataset.objects.get(slug="telemetry")
        self.assertEqual(list(dataset.modules.all()), [self.module])
        self.assertEqual(list(dataset.users.all()), [self.reader])
        self.assertEqual(list(dataset.groups.all()), [self.group])

        update_response = self.client.patch(
            reverse("datasets-detail", kwargs={"pk": dataset.pk}),
            {"user_ids": [], "group_ids": [], "enabled": False},
            format="json",
            HTTP_IF_MATCH='"1"',
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response["ETag"], '"2"')
        self.assertEqual(update_response.data["revision"], 2)
        dataset.refresh_from_db()
        self.assertFalse(dataset.enabled)
        self.assertFalse(dataset.users.exists())
        self.assertFalse(dataset.groups.exists())

    def test_dataset_update_requires_current_strong_etag(self) -> None:
        dataset = Dataset.objects.create(name="Concurrent", slug="concurrent")
        url = reverse("datasets-detail", kwargs={"pk": dataset.pk})

        missing = self.client.patch(url, {"description": "missing"}, format="json")
        weak = self.client.patch(
            url,
            {"description": "weak"},
            format="json",
            HTTP_IF_MATCH='W/"1"',
        )
        stale = self.client.patch(
            url,
            {"description": "stale"},
            format="json",
            HTTP_IF_MATCH='"2"',
        )
        current = self.client.patch(
            url,
            {"description": "current"},
            format="json",
            HTTP_IF_MATCH='"1"',
        )

        self.assertEqual(missing.status_code, 428)
        self.assertEqual(weak.status_code, 400)
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale["ETag"], '"1"')
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current["ETag"], '"2"')
        dataset.refresh_from_db()
        self.assertEqual(dataset.description, "current")
        self.assertEqual(dataset.revision, 2)

    def test_staff_can_list_disabled_datasets_and_filter_acl(self) -> None:
        assigned = Dataset.objects.create(
            name="Assigned",
            slug="assigned",
            enabled=False,
        )
        assigned.users.add(self.reader)
        assigned.groups.add(self.group)
        Dataset.objects.create(name="Other", slug="other", enabled=True)

        response = self.client.get(
            reverse("datasets-list"),
            {
                "enabled": "false",
                "user_id": self.reader.pk,
                "group_id": self.group.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.data], ["assigned"])
        self.assertEqual(response.data[0]["user_ids"], [self.reader.pk])
        self.assertEqual(response.data[0]["group_ids"], [self.group.pk])

    @override_settings(
        DEALHOST_OIDC_ISSUER="https://identity.example.test/realms/archideal"
    )
    def test_staff_can_list_minimal_dataset_principals_without_iam_secrets(
        self,
    ) -> None:
        self.reader.first_name = "Read"
        self.reader.last_name = "Only"
        self.reader.email = "reader@example.test"
        self.reader.save(update_fields=["first_name", "last_name", "email"])
        provisioned = provision_oidc_acl_identity(
            issuer="https://identity.example.test/realms/archideal",
            subject="sensitive-subject-not-for-acl-list",
            display_name="Chloé Operator",
            email="chloe@example.test",
        )

        response = self.client.get(reverse("dataset-principals"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertFalse(response.data["can_provision_oidc"])
        self.assertEqual(
            response.data["groups"], [{"id": self.group.pk, "name": "analysts"}]
        )

        users_by_id = {item["id"]: item for item in response.data["users"]}
        self.assertEqual(
            users_by_id[self.reader.pk],
            {
                "id": self.reader.pk,
                "label": "Read Only",
                "email": "reader@example.test",
                "is_active": True,
                "identity_kind": "local",
            },
        )
        self.assertEqual(
            users_by_id[provisioned.identity.user_id],
            {
                "id": provisioned.identity.user_id,
                "label": "Chloé Operator",
                "email": "chloe@example.test",
                "is_active": True,
                "identity_kind": "oidc",
            },
        )
        for principal in response.data["users"]:
            self.assertEqual(
                set(principal),
                {"id", "label", "email", "is_active", "identity_kind"},
            )
        serialized_response = str(response.data)
        self.assertNotIn("sensitive-subject-not-for-acl-list", serialized_response)
        self.assertNotIn("https://identity.example.test", serialized_response)
        self.assertNotIn("permissions", serialized_response)
        self.assertNotIn("token", serialized_response.casefold())

    def test_dataset_principals_requires_staff_and_reports_provision_capability(
        self,
    ) -> None:
        self.client.force_authenticate(self.reader)
        nonstaff_response = self.client.get(reverse("dataset-principals"))

        superuser = get_user_model().objects.create_superuser(
            username="root-operator",
            email="root@example.test",
            password="secret",  # nosec B106 - test fixture password only.
        )
        self.client.force_authenticate(superuser)
        superuser_response = self.client.get(reverse("dataset-principals"))

        self.assertEqual(nonstaff_response.status_code, 403)
        self.assertEqual(superuser_response.status_code, 200)
        self.assertTrue(superuser_response.data["can_provision_oidc"])
