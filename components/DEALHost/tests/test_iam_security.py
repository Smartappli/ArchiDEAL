from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase


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
