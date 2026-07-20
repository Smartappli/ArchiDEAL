from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RuntimeActiveLogMigrationTests(TransactionTestCase):
    migrate_from = [("hosting", "0009_runtime_deployment")]
    migrate_to = [("hosting", "0010_runtime_unique_active_log")]

    def test_migration_keeps_oldest_running_log_and_fails_only_duplicates(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        application = old_apps.get_model("hosting", "HostedApplication").objects.create(
            name="Migration runtime",
            slug="migration-runtime",
        )
        version = old_apps.get_model("hosting", "ApplicationVersion").objects.create(
            application_id=application.pk,
            version="1.0.0",
        )
        release = old_apps.get_model("hosting", "RuntimeRelease").objects.create(
            application_version_id=version.pk,
            manifest={},
            manifest_digest="a" * 64,
        )
        environment = old_apps.get_model("hosting", "RuntimeEnvironment").objects.create(
            slug="migration",
            name="Migration",
        )
        deployment = old_apps.get_model("hosting", "RuntimeDeployment").objects.create(
            application_id=application.pk,
            release_id=release.pk,
            environment_id=environment.pk,
        )
        operation_model = old_apps.get_model("hosting", "RuntimeOperation")
        queued = operation_model.objects.create(
            deployment_id=deployment.pk,
            operation_type="log_snapshot",
            status="queued",
            idempotency_key="migration-log-queued",
            request_hash="1" * 64,
        )
        oldest_running = operation_model.objects.create(
            deployment_id=deployment.pk,
            operation_type="log_snapshot",
            status="running",
            idempotency_key="migration-log-running-oldest",
            request_hash="2" * 64,
        )
        newer_running = operation_model.objects.create(
            deployment_id=deployment.pk,
            operation_type="log_snapshot",
            status="running",
            idempotency_key="migration-log-running-newer",
            request_hash="3" * 64,
        )
        mutation = operation_model.objects.create(
            deployment_id=deployment.pk,
            operation_type="configure",
            status="queued",
            idempotency_key="migration-configure",
            request_hash="4" * 64,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        migrated_operation = new_apps.get_model("hosting", "RuntimeOperation")

        self.assertEqual(
            migrated_operation.objects.get(pk=oldest_running.pk).status,
            "running",
        )
        for duplicate in (queued, newer_running):
            migrated = migrated_operation.objects.get(pk=duplicate.pk)
            self.assertEqual(migrated.status, "failed")
            self.assertEqual(
                migrated.error["code"],
                "duplicate_active_log_migrated",
            )
            self.assertEqual(migrated.progress, {"stage": "failed", "percent": 100})
            self.assertIsNotNone(migrated.finished_at)
        self.assertEqual(migrated_operation.objects.get(pk=mutation.pk).status, "queued")
