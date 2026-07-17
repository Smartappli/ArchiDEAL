from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.hosting.models import Dataset


class HostingDashboardDatasetsTests(TestCase):
    def test_dashboard_shows_only_accessible_datasets_for_logged_user(self):
        group = Group.objects.create(name="analysts")
        user = User.objects.create_user(
            username="alice",
            password="secret",  # nosec B106 - test fixture password only.
        )
        user.groups.add(group)

        direct_dataset = Dataset.objects.create(
            name="Direct",
            slug="direct",
            enabled=True,
        )
        direct_dataset.users.add(user)

        group_dataset = Dataset.objects.create(name="Group", slug="group", enabled=True)
        group_dataset.groups.add(group)

        private_dataset = Dataset.objects.create(
            name="Private",
            slug="private",
            enabled=True,
        )
        hidden_dataset = Dataset.objects.create(
            name="Hidden",
            slug="hidden",
            enabled=False,
        )
        hidden_dataset.users.add(user)

        self.client.login(
            username="alice",
            password="secret",  # nosec B106 - test fixture password only.
        )
        response = self.client.get(reverse("hosting-management"))

        self.assertEqual(response.status_code, 200)
        datasets = list(response.context["datasets"])
        self.assertIn(direct_dataset, datasets)
        self.assertIn(group_dataset, datasets)
        self.assertNotIn(private_dataset, datasets)
        self.assertNotIn(hidden_dataset, datasets)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("hosting-management"))
        self.assertEqual(response.status_code, 302)
