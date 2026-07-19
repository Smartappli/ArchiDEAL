from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.common.events.subjects import IAM_OIDC_ACL_IDENTITY_DEPROVISIONED
from apps.common.oidc import derive_oidc_acl_username
from apps.hosting.models import Dataset
from apps.iam.models import OIDCAclIdentity


class IamSecurityTests(APITestCase):
    def test_iam_api_rejects_anonymous_requests(self) -> None:
        response = self.client.get(reverse("iam-users-list"))

        self.assertIn(response.status_code, {401, 403})

    def test_iam_api_allows_superuser_requests(self) -> None:
        user = get_user_model().objects.create_user(
            username="admin",
            password="secret",  # nosec B106 - test fixture password only.
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(user)

        response = self.client.get(reverse("iam-users-list"))

        self.assertEqual(response.status_code, 200)

    def test_iam_api_rejects_non_superuser_staff(self) -> None:
        user = get_user_model().objects.create_user(
            username="staff",
            password="secret",  # nosec B106 - test fixture password only.
            is_staff=True,
            is_superuser=False,
        )
        self.client.force_authenticate(user)

        response = self.client.get(reverse("iam-users-list"))

        self.assertEqual(response.status_code, 403)

    def test_iam_api_allows_admin_bearer_token(self) -> None:
        response = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 200)

    def test_iam_api_rejects_readonly_bearer_token(self) -> None:
        response = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(
        DEALHOST_OIDC_INTROSPECTION_URL="https://identity.example.test/introspect",
        DEALHOST_OIDC_ISSUER="https://identity.example.test",
        DEALHOST_OIDC_AUDIENCE="archideal-production",
        DEALHOST_OIDC_CLIENT_ID="dealhost",
        DEALHOST_OIDC_CLIENT_SECRET="test-client-secret",
        DEALHOST_OIDC_READ_GROUPS=("archideal-readers",),
        DEALHOST_OIDC_ADMIN_GROUPS=("archideal-operators",),
        DEALHOST_OIDC_TIMEOUT_SECONDS=2.0,
    )
    @patch("apps.common.authentication.httpx.post")
    def test_iam_api_accepts_oidc_operator_group(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "active": True,
            "iss": "https://identity.example.test",
            "aud": ["archideal-production"],
            "sub": "operator-123",
            "preferred_username": "operator",
            "groups": ["archideal-operators"],
        }
        post.return_value = response

        result = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer oidc-id-token",
        )

        self.assertEqual(result.status_code, 200)
        post.assert_called_once_with(
            "https://identity.example.test/introspect",
            data={"token": "oidc-id-token"},
            auth=("dealhost", "test-client-secret"),
            headers={"Accept": "application/json"},
            timeout=2.0,
        )

    @override_settings(
        DEALHOST_OIDC_INTROSPECTION_URL="https://identity.example.test/introspect",
        DEALHOST_OIDC_ISSUER="https://identity.example.test",
        DEALHOST_OIDC_AUDIENCE="archideal-production",
        DEALHOST_OIDC_CLIENT_ID="dealhost",
        DEALHOST_OIDC_CLIENT_SECRET="test-client-secret",
        DEALHOST_OIDC_READ_GROUPS=("archideal-readers",),
        DEALHOST_OIDC_ADMIN_GROUPS=("archideal-operators",),
        DEALHOST_OIDC_TIMEOUT_SECONDS=2.0,
    )
    @patch("apps.common.authentication.httpx.post")
    def test_scope_and_role_claims_cannot_elevate_oidc_reader(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "active": True,
            "iss": "https://identity.example.test",
            "aud": "archideal-production",
            "sub": "reader-123",
            "groups": ["archideal-readers"],
            "scope": "openid archideal-operators",
            "roles": ["archideal-operators"],
            "realm_access": {"roles": ["archideal-operators"]},
        }
        post.return_value = response

        result = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer oidc-reader-token",
        )

        self.assertEqual(result.status_code, 403)

    @override_settings(
        DEALHOST_OIDC_INTROSPECTION_URL="https://identity.example.test/introspect",
        DEALHOST_OIDC_ISSUER="https://identity.example.test",
        DEALHOST_OIDC_AUDIENCE="archideal-production",
        DEALHOST_OIDC_CLIENT_ID="dealhost",
        DEALHOST_OIDC_CLIENT_SECRET="test-client-secret",
        DEALHOST_OIDC_GROUPS_CLAIM="entitlements",
        DEALHOST_OIDC_READ_GROUPS=("archideal-readers",),
        DEALHOST_OIDC_ADMIN_GROUPS=("archideal-operators",),
        DEALHOST_OIDC_TIMEOUT_SECONDS=2.0,
    )
    @patch("apps.common.authentication.httpx.post")
    def test_oidc_uses_only_the_configured_group_claim(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "active": True,
            "iss": "https://identity.example.test",
            "aud": "archideal-production",
            "sub": "reader-123",
            "entitlements": ["archideal-readers"],
            "groups": ["archideal-operators"],
        }
        post.return_value = response

        result = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer oidc-reader-token",
        )

        self.assertEqual(result.status_code, 403)

    @override_settings(
        DEALHOST_OIDC_INTROSPECTION_URL="https://identity.example.test/introspect",
        DEALHOST_OIDC_ISSUER="https://identity.example.test",
        DEALHOST_OIDC_AUDIENCE="archideal-production",
        DEALHOST_OIDC_CLIENT_ID="dealhost",
        DEALHOST_OIDC_CLIENT_SECRET="test-client-secret",
        DEALHOST_OIDC_GROUPS_CLAIM="roles",
        DEALHOST_OIDC_READ_GROUPS=("archideal-readers",),
        DEALHOST_OIDC_ADMIN_GROUPS=("archideal-operators",),
        DEALHOST_OIDC_TIMEOUT_SECONDS=2.0,
    )
    @patch("apps.common.authentication.httpx.post")
    def test_reserved_group_claim_configuration_fails_closed(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "active": True,
            "iss": "https://identity.example.test",
            "aud": "archideal-production",
            "sub": "reader-123",
            "groups": ["archideal-readers"],
            "roles": ["archideal-operators"],
        }
        post.return_value = response

        result = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer oidc-reader-token",
        )

        self.assertEqual(result.status_code, 401)

    @override_settings(
        DEALHOST_OIDC_INTROSPECTION_URL="https://identity.example.test/introspect",
        DEALHOST_OIDC_ISSUER="https://identity.example.test",
        DEALHOST_OIDC_AUDIENCE="archideal-production",
        DEALHOST_OIDC_CLIENT_ID="dealhost",
        DEALHOST_OIDC_CLIENT_SECRET="test-client-secret",
        DEALHOST_OIDC_READ_GROUPS=("archideal-readers",),
        DEALHOST_OIDC_ADMIN_GROUPS=("archideal-operators",),
        DEALHOST_OIDC_TIMEOUT_SECONDS=2.0,
    )
    @patch("apps.common.authentication.httpx.post")
    def test_oidc_authentication_requires_a_canonical_stable_subject(
        self,
        post: Mock,
    ) -> None:
        for subject in (
            None,
            "",
            "   ",
            " operator-123",
            "operator-123 ",
            "bad\0sub",
            "x" * 256,
        ):
            with self.subTest(subject=subject):
                response = Mock()
                response.json.return_value = {
                    "active": True,
                    "iss": "https://identity.example.test",
                    "aud": "archideal-production",
                    "sub": subject,
                    "groups": ["archideal-readers"],
                }
                post.return_value = response

                result = self.client.get(
                    reverse("iam-users-list"),
                    HTTP_AUTHORIZATION="Bearer oidc-reader-token",
                )

                self.assertEqual(result.status_code, 401)

    @override_settings(
        DEALHOST_OIDC_INTROSPECTION_URL="https://identity.example.test/introspect",
        DEALHOST_OIDC_ISSUER="https://identity.example.test",
        DEALHOST_OIDC_AUDIENCE="archideal-production",
        DEALHOST_OIDC_CLIENT_ID="dealhost",
        DEALHOST_OIDC_CLIENT_SECRET="test-client-secret",
        DEALHOST_OIDC_READ_GROUPS=("archideal-readers",),
        DEALHOST_OIDC_ADMIN_GROUPS=("archideal-operators",),
        DEALHOST_OIDC_TIMEOUT_SECONDS=2.0,
    )
    @patch("apps.common.authentication.httpx.post")
    def test_iam_api_rejects_oidc_token_without_allowed_group(
        self,
        post: Mock,
    ) -> None:
        response = Mock()
        response.json.return_value = {
            "active": True,
            "iss": "https://identity.example.test",
            "aud": "archideal-production",
            "sub": "unprivileged-user",
            "groups": ["another-group"],
        }
        post.return_value = response

        result = self.client.get(
            reverse("iam-users-list"),
            HTTP_AUTHORIZATION="Bearer oidc-id-token",
        )

        self.assertEqual(result.status_code, 401)

    def test_iam_manage_requires_login(self) -> None:
        response = self.client.get(reverse("iam-management"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_login_page_is_available(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)

    def test_iam_api_rejects_common_password_on_user_creation(self) -> None:
        response = self.client.post(
            reverse("iam-users-list"),
            {"username": "new-user", "password": "password"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username="new-user").exists())

    def test_iam_api_rejects_common_password_on_password_change(self) -> None:
        user = get_user_model().objects.create_user(
            username="member",
            password="initial-test-password",  # nosec B106 - test fixture only.
        )
        response = self.client.post(
            reverse("iam-users-set-password", kwargs={"pk": user.pk}),
            {"password": "password"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password("initial-test-password"))

    def test_iam_manage_rejects_non_superuser_staff(self) -> None:
        user = get_user_model().objects.create_user(
            username="staff",
            password="secret",  # nosec B106 - test fixture password only.
            is_staff=True,
            is_superuser=False,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("iam-management"))

        self.assertEqual(response.status_code, 403)


@override_settings(
    DEALHOST_OIDC_ISSUER="https://identity.example.test/realms/archideal"
)
class OIDCAclIdentityProvisioningTests(APITestCase):
    endpoint_name = "iam-oidc-identities-list"
    issuer = "https://identity.example.test/realms/archideal"
    subject = "operator-123"

    def _post(self, data: dict | None = None):
        payload = {
            "issuer": self.issuer,
            "subject": self.subject,
            "display_name": "Ada Operator",
            "email": "ada@example.test",
        }
        if data is not None:
            payload = data
        return self.client.post(
            reverse(self.endpoint_name),
            payload,
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

    def test_provisioning_creates_passwordless_unprivileged_acl_user(self) -> None:
        response = self._post()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["created"])
        self.assertFalse(response.data["metadata_updated"])
        self.assertEqual(response.data["issuer"], self.issuer)
        self.assertEqual(response.data["subject"], self.subject)
        expected_username = derive_oidc_acl_username(self.issuer, self.subject)
        self.assertEqual(response.data["acl_username"], expected_username)
        self.assertNotIn("password", response.data)
        self.assertEqual(response["Cache-Control"], "no-store")

        identity = OIDCAclIdentity.objects.select_related("user").get()
        self.assertEqual(identity.user_id, response.data["user_id"])
        self.assertEqual(identity.user.username, expected_username)
        self.assertFalse(identity.user.has_usable_password())
        self.assertFalse(identity.user.is_staff)
        self.assertFalse(identity.user.is_superuser)

    def test_repeated_provisioning_is_explicitly_idempotent(self) -> None:
        first = self._post()
        second = self._post()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data["created"])
        self.assertFalse(second.data["metadata_updated"])
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(second.data["user_id"], first.data["user_id"])
        self.assertEqual(OIDCAclIdentity.objects.count(), 1)
        self.assertEqual(
            get_user_model().objects.filter(username__startswith="oidc:").count(), 1
        )

    def test_repeated_provisioning_refreshes_only_human_metadata(self) -> None:
        first = self._post()
        response = self._post(
            {
                "issuer": self.issuer,
                "subject": self.subject,
                "display_name": "Ada Lovelace",
                "email": "ada.lovelace@example.test",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertTrue(response.data["metadata_updated"])
        self.assertEqual(response.data["user_id"], first.data["user_id"])
        self.assertEqual(response.data["display_name"], "Ada Lovelace")
        self.assertEqual(response.data["email"], "ada.lovelace@example.test")

    def test_listing_exposes_recognizable_identity_without_secrets(self) -> None:
        created = self._post()

        response = self.client.get(
            reverse(self.endpoint_name),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["display_name"], "Ada Operator")
        self.assertEqual(response.data[0]["email"], "ada@example.test")
        self.assertEqual(response.data[0]["user_id"], created.data["user_id"])
        self.assertNotIn("password", response.data[0])
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_user_api_includes_backward_compatible_oidc_identity_summary(self) -> None:
        created = self._post()

        response = self.client.get(
            reverse("iam-users-detail", kwargs={"pk": created.data["user_id"]}),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], created.data["acl_username"])
        self.assertEqual(
            response.data["oidc_identity"],
            {
                "issuer": self.issuer,
                "subject": self.subject,
                "display_name": "Ada Operator",
                "email": "ada@example.test",
                "label": "Ada Operator",
            },
        )
        self.assertNotIn("password", response.data)

    def test_regular_user_api_representation_keeps_nullable_oidc_field(self) -> None:
        user = get_user_model().objects.create_user(username="local-user")

        response = self.client.get(
            reverse("iam-users-detail", kwargs={"pk": user.pk}),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["oidc_identity"])

    def test_provisioning_rejects_noncanonical_or_insecure_issuers(self) -> None:
        invalid_issuers = (
            "http://identity.example.test",
            "HTTPS://identity.example.test",
            "https://Identity.example.test",
            "https://identity.example.test:443",
            "https://user@identity.example.test",
            "https://identity.example.test/../issuer",
            "https://identity.example.test//issuer",
            "https://identity.example.test?tenant=one",
            "https://identity.example.test#fragment",
            " https://identity.example.test",
        )
        for issuer in invalid_issuers:
            with self.subTest(issuer=issuer):
                response = self._post({"issuer": issuer, "subject": self.subject})
                self.assertEqual(response.status_code, 400)

        self.assertFalse(OIDCAclIdentity.objects.exists())

    def test_provisioning_rejects_canonical_but_unapproved_issuer(self) -> None:
        response = self._post(
            {
                "issuer": "https://other-identity.example.test/realms/archideal",
                "subject": self.subject,
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["issuer"],
            ["The OIDC issuer is not approved for this deployment."],
        )
        self.assertFalse(OIDCAclIdentity.objects.exists())

    @override_settings(DEALHOST_OIDC_ISSUER="")
    def test_provisioning_fails_closed_without_approved_issuer(self) -> None:
        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["issuer"],
            [
                "OIDC identity provisioning is unavailable because no approved "
                "runtime issuer is configured."
            ],
        )
        self.assertFalse(OIDCAclIdentity.objects.exists())

    @override_settings(DEALHOST_OIDC_ISSUER="http://identity.example.test")
    def test_provisioning_fails_closed_with_invalid_approved_issuer(self) -> None:
        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["issuer"],
            [
                "OIDC identity provisioning is unavailable because the approved "
                "runtime issuer configuration is invalid."
            ],
        )
        self.assertFalse(OIDCAclIdentity.objects.exists())

    def test_provisioning_rejects_empty_padded_or_null_subject(self) -> None:
        for subject in ("", "   ", " operator-123", "operator-123 ", "bad\0sub"):
            with self.subTest(subject=subject):
                response = self._post({"issuer": self.issuer, "subject": subject})
                self.assertEqual(response.status_code, 400)

        self.assertFalse(OIDCAclIdentity.objects.exists())

    def test_provisioning_rejects_unknown_fields_including_secrets(self) -> None:
        response = self._post(
            {
                "issuer": self.issuer,
                "subject": self.subject,
                "password": "must-not-be-stored",
                "access_token": "must-not-be-stored",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["unknown_fields"],
            [
                "Unsupported field: access_token",
                "Unsupported field: password",
            ],
        )
        self.assertFalse(OIDCAclIdentity.objects.exists())

    def test_existing_username_collision_is_an_explicit_conflict(self) -> None:
        expected_username = derive_oidc_acl_username(self.issuer, self.subject)
        existing = get_user_model().objects.create_user(
            username=expected_username,
            password="existing-local-password",  # nosec B106 - test fixture only.
        )

        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "oidc_identity_conflict")
        self.assertFalse(OIDCAclIdentity.objects.exists())
        existing.refresh_from_db()
        self.assertTrue(existing.has_usable_password())

    def test_oidc_acl_user_password_username_and_delete_are_protected(self) -> None:
        created = self._post()
        user_id = created.data["user_id"]

        password_response = self.client.post(
            reverse("iam-users-set-password", kwargs={"pk": user_id}),
            {"password": "a-new-long-test-password"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )
        update_response = self.client.patch(
            reverse("iam-users-detail", kwargs={"pk": user_id}),
            {"username": "renamed"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )
        delete_response = self.client.delete(
            reverse("iam-users-detail", kwargs={"pk": user_id}),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(password_response.status_code, 409)
        self.assertEqual(update_response.status_code, 409)
        self.assertEqual(delete_response.status_code, 409)
        user = get_user_model().objects.get(pk=user_id)
        self.assertEqual(user.username, created.data["acl_username"])
        self.assertFalse(user.has_usable_password())

    def test_oidc_acl_user_can_keep_protected_fields_unchanged(self) -> None:
        created = self._post()

        response = self.client.patch(
            reverse("iam-users-detail", kwargs={"pk": created.data["user_id"]}),
            {
                "username": created.data["acl_username"],
                "is_staff": False,
                "is_superuser": False,
                "is_active": False,
            },
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_provisioning_requires_superuser_equivalent(self) -> None:
        anonymous = self.client.get(reverse(self.endpoint_name))
        readonly = self.client.get(
            reverse(self.endpoint_name),
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertIn(anonymous.status_code, {401, 403})
        self.assertEqual(readonly.status_code, 403)

    def test_deprovisioning_requires_superuser_equivalent(self) -> None:
        created = self._post()

        response = self.client.delete(
            reverse(
                "iam-oidc-identities-detail",
                kwargs={"pk": created.data["id"]},
            ),
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())
        self.assertTrue(
            get_user_model().objects.filter(pk=created.data["user_id"]).exists()
        )

    def test_deprovisioning_rejects_a_request_body(self) -> None:
        created = self._post()

        response = self.client.delete(
            reverse(
                "iam-oidc-identities-detail",
                kwargs={"pk": created.data["id"]},
            ),
            {"issuer": "https://other.example.test", "subject": "someone-else"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "delete_body_not_allowed")
        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())

    def test_deprovisioning_conflicts_with_direct_dataset_acl(self) -> None:
        created = self._post()
        dataset = Dataset.objects.create(name="Telemetry", slug="telemetry")
        dataset.users.add(created.data["user_id"])

        response = self.client.delete(
            reverse(
                "iam-oidc-identities-detail",
                kwargs={"pk": created.data["id"]},
            ),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "oidc_identity_conflict")
        self.assertIn("dataset_acl", response.data["detail"])
        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())
        self.assertTrue(
            get_user_model().objects.filter(pk=created.data["user_id"]).exists()
        )
        self.assertTrue(dataset.users.filter(pk=created.data["user_id"]).exists())

    def test_deprovisioning_conflicts_with_group_membership(self) -> None:
        created = self._post()
        user = get_user_model().objects.get(pk=created.data["user_id"])
        user.groups.add(Group.objects.create(name="dataset-readers"))

        response = self.client.delete(
            reverse(
                "iam-oidc-identities-detail",
                kwargs={"pk": created.data["id"]},
            ),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("groups", response.data["detail"])
        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())

    def test_deprovisioning_conflicts_with_direct_user_permission(self) -> None:
        created = self._post()
        user = get_user_model().objects.get(pk=created.data["user_id"])
        permission = Permission.objects.order_by("pk").first()
        self.assertIsNotNone(permission)
        user.user_permissions.add(permission)

        response = self.client.delete(
            reverse(
                "iam-oidc-identities-detail",
                kwargs={"pk": created.data["id"]},
            ),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("user_permissions", response.data["detail"])
        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())

    def test_deprovisioning_conflicts_with_incoherent_binding(self) -> None:
        created = self._post()
        user = get_user_model().objects.get(pk=created.data["user_id"])
        user.username = "tampered-local-user"
        user.save(update_fields=["username"])

        response = self.client.delete(
            reverse(
                "iam-oidc-identities-detail",
                kwargs={"pk": created.data["id"]},
            ),
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(response.status_code, 409)
        self.assertNotIn(self.subject, response.data["detail"])
        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())

    @patch("apps.iam.views.publish_event")
    def test_deprovisioning_deletes_both_records_and_is_repeat_safe(
        self,
        publish_event,
    ) -> None:
        created = self._post()
        endpoint = reverse(
            "iam-oidc-identities-detail",
            kwargs={"pk": created.data["id"]},
        )

        first = self.client.delete(
            endpoint,
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )
        second = self.client.delete(
            endpoint,
            HTTP_AUTHORIZATION="Bearer test-admin-token",
        )

        self.assertEqual(first.status_code, 204)
        self.assertEqual(first["Cache-Control"], "no-store")
        self.assertEqual(second.status_code, 404)
        self.assertEqual(second["Cache-Control"], "no-store")
        self.assertFalse(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())
        self.assertFalse(
            get_user_model().objects.filter(pk=created.data["user_id"]).exists()
        )
        publish_event.assert_called_once_with(
            event_type=IAM_OIDC_ACL_IDENTITY_DEPROVISIONED,
            data={
                "identity_id": created.data["id"],
                "user_id": created.data["user_id"],
                "acl_username": created.data["acl_username"],
                "actor": "dealhost-admin-token",
            },
            producer="apps.iam.OIDCAclIdentityViewSet",
        )
        audit_payload = publish_event.call_args.kwargs["data"]
        self.assertNotIn(self.subject, repr(audit_payload))
        self.assertNotIn(self.issuer, repr(audit_payload))

    @patch.object(
        get_user_model(),
        "delete",
        autospec=True,
        side_effect=RuntimeError("simulated user deletion failure"),
    )
    def test_deprovisioning_rolls_back_identity_when_user_delete_fails(
        self,
        _delete,
    ) -> None:
        created = self._post()

        with self.assertRaisesRegex(RuntimeError, "simulated user deletion failure"):
            self.client.delete(
                reverse(
                    "iam-oidc-identities-detail",
                    kwargs={"pk": created.data["id"]},
                ),
                HTTP_AUTHORIZATION="Bearer test-admin-token",
            )

        self.assertTrue(OIDCAclIdentity.objects.filter(pk=created.data["id"]).exists())
        self.assertTrue(
            get_user_model().objects.filter(pk=created.data["user_id"]).exists()
        )
