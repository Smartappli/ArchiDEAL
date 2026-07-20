from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.hosting.models import RuntimeEnvironment


class ProvisionRuntimeEnvironmentCommandTests(TestCase):
    def run_command(self, *args: str) -> str:
        stdout = StringIO()
        call_command("provision_runtime_environment", *args, stdout=stdout)
        return stdout.getvalue()

    def test_provisions_enabled_production_environment(self) -> None:
        output = self.run_command()

        environment = RuntimeEnvironment.objects.get(pk="production")
        self.assertEqual(environment.name, "Production")
        self.assertEqual(environment.orchestrator, "kubernetes")
        self.assertTrue(environment.enabled)
        self.assertEqual(environment.revision, 1)
        self.assertEqual(
            environment.capabilities,
            {
                "start_stop": True,
                "restart": True,
                "scaling": {
                    "fixed": {"min_replicas": 1, "max_replicas": 10},
                    "autoscaling": {
                        "enabled": True,
                        "min_replicas": 1,
                        "max_replicas": 10,
                    },
                },
                "logs": {"max_lines": 1000, "max_bytes": 262144},
                "domains": False,
                "network_egress": False,
            },
        )
        self.assertEqual(
            environment.policy,
            {
                "requires_image_digest": True,
                "allowed_registries": ["ghcr.io/smartappli/"],
                "allowed_secret_refs": [],
                "stateless_only": True,
            },
        )
        self.assertIn("'production' created at revision 1", output)

    def test_repeated_provisioning_is_a_database_noop(self) -> None:
        self.run_command()
        first = RuntimeEnvironment.objects.get(pk="production")
        first_updated_at = first.updated_at

        output = self.run_command()

        second = RuntimeEnvironment.objects.get(pk="production")
        self.assertEqual(second.revision, 1)
        self.assertEqual(second.updated_at, first_updated_at)
        self.assertIn("'production' unchanged at revision 1", output)

    def test_reconciles_drift_and_increments_revision_once(self) -> None:
        RuntimeEnvironment.objects.create(
            slug="production",
            name="Unsafe production",
            orchestrator="kubernetes",
            enabled=False,
            capabilities={"domains": True, "network_egress": True},
            policy={"requires_image_digest": False},
            revision=7,
        )

        output = self.run_command()

        environment = RuntimeEnvironment.objects.get(pk="production")
        self.assertEqual(environment.name, "Production")
        self.assertTrue(environment.enabled)
        self.assertFalse(environment.capabilities["domains"])
        self.assertFalse(environment.capabilities["network_egress"])
        self.assertTrue(environment.policy["requires_image_digest"])
        self.assertEqual(environment.revision, 8)
        self.assertIn("'production' updated at revision 8", output)

        second_output = self.run_command()
        environment.refresh_from_db()
        self.assertEqual(environment.revision, 8)
        self.assertIn("'production' unchanged at revision 8", second_output)

    def test_provisions_an_explicit_canonical_secret_allowlist(self) -> None:
        self.run_command(
            "--allowed-secret-ref",
            "dealapp-api",
            "--allowed-secret-ref",
            "dealapp-database",
        )

        environment = RuntimeEnvironment.objects.get(pk="production")
        self.assertEqual(
            environment.policy["allowed_secret_refs"],
            ["dealapp-api", "dealapp-database"],
        )

        output = self.run_command(
            "--allowed-secret-ref",
            "dealapp-database",
            "--allowed-secret-ref",
            "dealapp-api",
        )
        environment.refresh_from_db()
        self.assertEqual(environment.revision, 1)
        self.assertIn("'production' unchanged at revision 1", output)

    def test_rejects_invalid_or_duplicate_secret_references(self) -> None:
        invalid_values = (
            ("--allowed-secret-ref", "other/secret"),
            (
                "--allowed-secret-ref",
                "dealapp-database",
                "--allowed-secret-ref",
                "dealapp-database",
            ),
        )
        for arguments in invalid_values:
            with self.subTest(arguments=arguments), self.assertRaises(CommandError):
                self.run_command(*arguments)

        self.assertFalse(RuntimeEnvironment.objects.exists())

    def test_preserves_other_runtime_environments(self) -> None:
        other = RuntimeEnvironment.objects.create(
            slug="staging",
            name="Staging",
            enabled=False,
        )

        self.run_command()

        other.refresh_from_db()
        self.assertEqual(other.name, "Staging")
        self.assertFalse(other.enabled)
        self.assertEqual(RuntimeEnvironment.objects.count(), 2)
