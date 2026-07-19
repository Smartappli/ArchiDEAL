from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console import device_registry, migrate  # noqa: E402


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class FakeMigrationConnection:
    def __init__(
        self,
        known: list[dict[str, str]] | None = None,
        *,
        migration_privileges: dict[str, bool] | None = None,
        object_ownership: dict[str, bool] | None = None,
        runtime_privileges: dict[str, bool] | None = None,
    ) -> None:
        self.known = known or []
        self.migration_privileges = migration_privileges or {
            "has_usage": True,
            "has_create": True,
            "has_owner_rights": True,
        }
        self.runtime_privileges = runtime_privileges or {
            "has_schema_usage": True,
            "has_schema_create": False,
            "has_device_select": True,
            "has_device_insert": True,
            "has_device_update": True,
            "has_device_delete": False,
            "has_device_truncate": False,
            "has_device_references": False,
            "has_device_trigger": False,
            "has_migration_select": True,
            "has_migration_insert": False,
            "has_migration_update": False,
            "has_migration_delete": False,
            "has_migration_truncate": False,
            "owns_schema": False,
            "owns_devices": False,
            "owns_migrations": False,
        }
        self.object_ownership = object_ownership or {
            "objects_present": True,
            "has_owner_rights": True,
        }
        self.executions: list[tuple[str, object]] = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql: str, parameters: object = None) -> FakeCursor:
        self.executions.append((sql, parameters))
        if "has_owner_rights" in sql:
            if "objects_present" in sql:
                return FakeCursor([self.object_ownership])
            return FakeCursor([self.migration_privileges])
        if "has_device_select" in sql:
            return FakeCursor([self.runtime_privileges])
        if "SELECT version, checksum" in sql:
            return FakeCursor(self.known)
        return FakeCursor()


class FakeReadinessConnection:
    def __init__(
        self,
        *,
        schema_present: bool,
        migrations: dict[str, str] | list[tuple[str, str]],
    ) -> None:
        self.schema_present = schema_present
        self.migrations = list(migrations.items()) if isinstance(migrations, dict) else migrations
        self.columns = [
            {
                "column_name": name,
                "udt_name": fingerprint[0],
                "character_maximum_length": fingerprint[1],
                "is_nullable": "YES" if fingerprint[2] else "NO",
            }
            for name, fingerprint in device_registry.REQUIRED_DEVICE_COLUMN_FINGERPRINT.items()
        ]
        self.constraints = [
            {"conname": name, "contype": constraint_type}
            for name, constraint_type in device_registry.REQUIRED_DEVICE_CONSTRAINTS.items()
        ]
        self.indexes = [{"indexname": name} for name in device_registry.REQUIRED_DEVICE_INDEXES]
        self.runtime_privileges = {
            "has_schema_usage": True,
            "has_schema_create": False,
            "has_device_select": True,
            "has_device_insert": True,
            "has_device_update": True,
            "has_device_delete": False,
            "has_device_truncate": False,
            "has_device_references": False,
            "has_device_trigger": False,
            "has_migration_select": True,
            "has_migration_insert": False,
            "has_migration_update": False,
            "has_migration_delete": False,
            "has_migration_truncate": False,
            "owns_schema": False,
            "owns_devices": False,
            "owns_migrations": False,
        }

    def execute(self, sql: str, parameters: object = None) -> FakeCursor:
        del parameters
        if "to_regclass" in sql:
            table = "public.devices" if self.schema_present else None
            migrations = "public.dealiot_schema_migrations" if self.schema_present else None
            return FakeCursor(
                [{"devices_table": table, "migrations_table": migrations}],
            )
        if "information_schema.columns" in sql:
            return FakeCursor(self.columns)
        if "pg_catalog.pg_constraint" in sql:
            return FakeCursor(self.constraints)
        if "pg_catalog.pg_indexes" in sql:
            return FakeCursor(self.indexes)
        if "SELECT revision FROM public.devices WHERE FALSE" in sql:
            return FakeCursor()
        if "has_device_select" in sql:
            return FakeCursor([self.runtime_privileges])
        if "SELECT version, checksum" in sql:
            self.assert_ordered_query(sql)
            return FakeCursor(
                [
                    {"version": version, "checksum": checksum}
                    for version, checksum in self.migrations
                ],
            )
        message = f"unexpected readiness query: {sql}"
        raise AssertionError(message)

    @staticmethod
    def assert_ordered_query(sql: str) -> None:
        if "ORDER BY applied_at ASC, version ASC" not in sql:
            raise AssertionError("readiness must inspect migrations in their applied order")


class FakeCreateConflictConnection:
    def execute(self, sql: str, parameters: object = None) -> FakeCursor:
        del parameters
        if "ON CONFLICT (device_id) DO NOTHING" not in sql:
            raise AssertionError("create must keep its conflict-safe insert")
        return FakeCursor()


class FakeListConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, object]] = []

    def execute(self, sql: str, parameters: object = None) -> FakeCursor:
        self.executions.append((sql, parameters))
        return FakeCursor()


class DeviceRegistryUnitTests(unittest.TestCase):
    def test_create_validation_normalizes_defaults(self) -> None:
        payload = device_registry.validate_create_payload(
            {
                "device_id": "field.sensor-01",
                "display_name": " Field sensor ",
                "kind": "sensor",
            }
        )

        self.assertEqual(payload["display_name"], "Field sensor")
        self.assertEqual(payload["status"], "provisioning")
        self.assertEqual(payload["capabilities"], [])
        self.assertEqual(payload["settings"], {})
        self.assertEqual(payload["labels"], {})

    def test_duplicate_create_maps_to_device_conflict(self) -> None:
        @contextmanager
        def connection():
            yield FakeCreateConflictConnection()

        with (
            patch(
                "management_console.device_registry.database_connection",
                return_value=connection(),
            ),
            patch(
                "management_console.device_registry._jsonb",
                side_effect=lambda value: value,
            ),
            self.assertRaises(device_registry.DeviceConflictError),
        ):
            device_registry.create_device(
                {
                    "device_id": "field-01",
                    "display_name": "Field device",
                    "kind": "sensor",
                },
                "operator-1",
            )

    def test_validation_rejects_retired_create_unknown_fields_and_secrets(self) -> None:
        base = {
            "device_id": "field-01",
            "display_name": "Field device",
            "kind": "sensor",
        }
        invalid_payloads = (
            {**base, "status": "retired"},
            {**base, "unknown": True},
            {**base, "settings": {"network": {"access_token": "do-not-store"}}},
        )
        for payload in invalid_payloads:
            with (
                self.subTest(payload=payload),
                self.assertRaises(device_registry.DeviceValidationError),
            ):
                device_registry.validate_create_payload(payload)

    def test_settings_and_labels_reject_common_secret_key_variants(self) -> None:
        base = {
            "device_id": "field-01",
            "display_name": "Field device",
            "kind": "sensor",
        }
        secret_keys = (
            "auth",
            "api_key",
            "api-key",
            "apiKey",
            "Authorization",
            "bearerToken",
            "clientPwd",
            "db_password",
            "passwd",
            "signing_key",
        )
        for container in ("settings", "labels"):
            for key in secret_keys:
                with (
                    self.subTest(container=container, key=key),
                    self.assertRaises(device_registry.DeviceValidationError),
                ):
                    device_registry.validate_create_payload(
                        {**base, container: {key: "must-not-be-persisted"}},
                    )

        accepted = device_registry.validate_create_payload(
            {**base, "labels": {"author": "operator", "authority": "field-team"}},
        )
        self.assertEqual(
            accepted["labels"],
            {"author": "operator", "authority": "field-team"},
        )

    def test_list_search_treats_sql_wildcards_as_literal_characters(self) -> None:
        fake = FakeListConnection()

        @contextmanager
        def connection():
            yield fake

        with patch(
            "management_console.device_registry.database_connection",
            return_value=connection(),
        ):
            result = device_registry.list_devices(query=r"50%_off\archive")

        self.assertEqual(result, {"devices": [], "next_cursor": None})
        sql, parameters = fake.executions[0]
        self.assertIn("ILIKE %s ESCAPE '\\'", sql)
        self.assertEqual(
            parameters,
            [r"%50\%\_off\\archive%", r"%50\%\_off\\archive%", 51],
        )

    def test_patch_validation_requires_writable_content(self) -> None:
        with self.assertRaises(device_registry.DeviceValidationError):
            device_registry.validate_patch_payload({})
        with self.assertRaises(device_registry.DeviceValidationError):
            device_registry.validate_patch_payload({"device_id": "immutable"})

        self.assertEqual(
            device_registry.validate_patch_payload({"status": "active"}),
            {"status": "active"},
        )

    def test_database_parameters_are_explicit_and_bounded(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertRaises(device_registry.RegistryUnavailableError),
        ):
            device_registry.database_parameters()

        environment = {
            "DEALIOT_REGISTRY_DATABASE_HOST": "registry-db",
            "DEALIOT_REGISTRY_DATABASE_NAME": "dealiot_registry",
            "DEALIOT_REGISTRY_DATABASE_USER": "dealiot_registry",
            "DEALIOT_REGISTRY_DATABASE_PASSWORD": "unit-password",
            "DEALIOT_REGISTRY_DATABASE_SSLMODE": "disable",
        }
        with patch.dict("os.environ", environment, clear=True):
            parameters = device_registry.database_parameters()
        self.assertEqual(parameters["host"], "registry-db")
        self.assertEqual(parameters["port"], 5432)
        self.assertEqual(parameters["connect_timeout"], 3)
        self.assertEqual(parameters["options"], "-c search_path=pg_catalog,public")

    def test_readiness_requires_registry_tables_and_all_packaged_migrations(self) -> None:
        @contextmanager
        def connection(fake: FakeReadinessConnection):
            yield fake

        expected = device_registry.required_migrations()
        with patch(
            "management_console.device_registry.database_connection",
            return_value=connection(
                FakeReadinessConnection(schema_present=True, migrations=expected),
            ),
        ):
            device_registry.check_readiness()

        for fake in (
            FakeReadinessConnection(schema_present=False, migrations=expected),
            FakeReadinessConnection(schema_present=True, migrations={}),
        ):
            with (
                self.subTest(fake=fake),
                patch(
                    "management_console.device_registry.database_connection",
                    return_value=connection(fake),
                ),
                self.assertRaises(device_registry.RegistryUnavailableError),
            ):
                device_registry.check_readiness()

    def test_readiness_accepts_only_an_ordered_forward_migration_suffix(self) -> None:
        @contextmanager
        def connection(fake: FakeReadinessConnection):
            yield fake

        expected = {
            "0001_registry.sql": "1" * 64,
            "0002_additive.sql": "2" * 64,
        }
        future = [*expected.items(), ("0003_forward.sql", "3" * 64)]
        with (
            patch(
                "management_console.device_registry.required_migrations",
                return_value=expected,
            ),
            patch(
                "management_console.device_registry.database_connection",
                return_value=connection(
                    FakeReadinessConnection(schema_present=True, migrations=future),
                ),
            ),
        ):
            device_registry.check_readiness()

        invalid_histories = (
            (
                [("0001_registry.sql", "1" * 64), ("0003_forward.sql", "3" * 64)],
                "schema is behind",
            ),
            (
                [("0001_registry.sql", "0" * 64), ("0002_additive.sql", "2" * 64)],
                "checksum changed",
            ),
            (
                [
                    ("0001_registry.sql", "1" * 64),
                    ("0003_forward.sql", "3" * 64),
                    ("0002_additive.sql", "2" * 64),
                ],
                "migration order",
            ),
            (
                [*expected.items(), ("0003_forward.sql", "not-a-checksum")],
                "invalid forward migration metadata",
            ),
            (
                [*expected.items(), ("0000_late.sql", "3" * 64)],
                "strictly ordered suffix",
            ),
        )
        for migrations, message in invalid_histories:
            fake = FakeReadinessConnection(schema_present=True, migrations=migrations)
            with (
                self.subTest(message=message),
                patch(
                    "management_console.device_registry.required_migrations",
                    return_value=expected,
                ),
                patch(
                    "management_console.device_registry.database_connection",
                    return_value=connection(fake),
                ),
                self.assertRaisesRegex(device_registry.RegistryUnavailableError, message),
            ):
                device_registry.check_readiness()

    def test_readiness_rejects_checksum_drift_for_packaged_migration(self) -> None:
        @contextmanager
        def connection(fake: FakeReadinessConnection):
            yield fake

        expected = device_registry.required_migrations()
        changed = dict(expected)
        changed[next(iter(changed))] = "0" * 64

        for migrations, message in ((changed, "checksum changed"),):
            fake = FakeReadinessConnection(
                schema_present=True,
                migrations=migrations,
            )
            with (
                self.subTest(message=message),
                patch(
                    "management_console.device_registry.database_connection",
                    return_value=connection(fake),
                ),
                self.assertRaisesRegex(device_registry.RegistryUnavailableError, message),
            ):
                device_registry.check_readiness()

    def test_readiness_rejects_schema_drift_and_production_privilege_escalation(self) -> None:
        @contextmanager
        def connection(fake: FakeReadinessConnection):
            yield fake

        expected = device_registry.required_migrations()
        missing_index = [
            {"indexname": name}
            for name in device_registry.REQUIRED_DEVICE_INDEXES
            if name != "devices_updated_at_idx"
        ]
        invalid_fingerprint = FakeReadinessConnection(
            schema_present=True,
            migrations=expected,
        )
        invalid_fingerprint.indexes = missing_index
        with (
            patch(
                "management_console.device_registry.database_connection",
                return_value=connection(invalid_fingerprint),
            ),
            self.assertRaisesRegex(
                device_registry.RegistryUnavailableError,
                "schema fingerprint is invalid: devices_updated_at_idx",
            ),
        ):
            device_registry.check_readiness()

        escalated = FakeReadinessConnection(
            schema_present=True,
            migrations=expected,
        )
        escalated.runtime_privileges = {
            **escalated.runtime_privileges,
            "has_schema_create": True,
            "has_device_truncate": True,
        }
        with (
            patch.dict("os.environ", {"MANAGEMENT_CONSOLE_PRODUCTION_MODE": "true"}),
            patch(
                "management_console.device_registry.database_connection",
                return_value=connection(escalated),
            ),
            self.assertRaisesRegex(
                device_registry.RegistryUnavailableError,
                "runtime database privileges are not least-privilege",
            ),
        ):
            device_registry.check_readiness()

    def test_migration_runner_applies_once_and_rejects_checksum_drift(self) -> None:
        with (
            tempfile.TemporaryDirectory() as empty_directory,
            patch.object(migrate, "MIGRATIONS_DIR", Path(empty_directory)),
            self.assertRaisesRegex(RuntimeError, "no DEALIoT registry migrations"),
        ):
            migrate.apply_migrations(FakeMigrationConnection())

        with tempfile.TemporaryDirectory() as directory:
            migration_path = Path(directory) / "0001_registry.sql"
            migration_path.write_text("CREATE TABLE test_devices (id text);\n", encoding="utf-8")
            connection = FakeMigrationConnection()
            with patch.object(migrate, "MIGRATIONS_DIR", Path(directory)):
                applied = migrate.apply_migrations(connection)
            self.assertEqual(applied, ["0001_registry.sql"])
            insert = next(
                parameters
                for sql, parameters in connection.executions
                if "INSERT INTO public.dealiot_schema_migrations" in sql
            )

            changed = FakeMigrationConnection(
                [{"version": "0001_registry.sql", "checksum": "0" * 64}]
            )
            with (
                patch.object(migrate, "MIGRATIONS_DIR", Path(directory)),
                self.assertRaisesRegex(RuntimeError, "checksum changed"),
            ):
                migrate.apply_migrations(changed)

            current = FakeMigrationConnection(
                [{"version": "0001_registry.sql", "checksum": insert[1]}]
            )
            with patch.object(migrate, "MIGRATIONS_DIR", Path(directory)):
                self.assertEqual(migrate.apply_migrations(current), [])

    def test_migration_runner_grants_only_runtime_dml_privileges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            migration_path = Path(directory) / "0001_registry.sql"
            migration_path.write_text("CREATE TABLE devices (id text);\n", encoding="utf-8")
            connection = FakeMigrationConnection()
            with patch.object(migrate, "MIGRATIONS_DIR", Path(directory)):
                migrate.apply_migrations(
                    connection,
                    runtime_role="dealiot_registry_app",
                )

        statements = "\n".join(sql for sql, _parameters in connection.executions)
        self.assertIn(
            "REVOKE ALL PRIVILEGES ON SCHEMA public FROM PUBLIC",
            statements,
        )
        self.assertIn(
            'GRANT SELECT, INSERT, UPDATE ON TABLE public.devices TO "dealiot_registry_app"',
            statements,
        )
        self.assertIn(
            'GRANT SELECT ON TABLE public.dealiot_schema_migrations TO "dealiot_registry_app"',
            statements,
        )
        self.assertIn(
            'REVOKE ALL PRIVILEGES ON SCHEMA public FROM "dealiot_registry_app"',
            statements,
        )
        self.assertIn(
            "REVOKE ALL PRIVILEGES ON TABLE public.devices, "
            'public.dealiot_schema_migrations FROM "dealiot_registry_app"',
            statements,
        )
        self.assertNotIn("GRANT CREATE", statements)
        self.assertNotIn("GRANT SELECT, INSERT, UPDATE, DELETE", statements)

        with self.assertRaisesRegex(RuntimeError, "invalid identifier"):
            migrate.apply_migrations(
                FakeMigrationConnection(),
                runtime_role='app"; DROP TABLE devices; --',
            )

        inherited_create = FakeMigrationConnection(
            runtime_privileges={
                **FakeMigrationConnection().runtime_privileges,
                "has_schema_create": True,
                "has_device_truncate": True,
            },
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(migrate, "MIGRATIONS_DIR", Path(directory)),
        ):
            migration_path = Path(directory) / "0001_registry.sql"
            migration_path.write_text("CREATE TABLE devices (id text);\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not least-privilege"):
                migrate.apply_migrations(
                    inherited_create,
                    runtime_role="dealiot_registry_app",
                )

    def test_migration_runner_fails_before_ddl_without_public_schema_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            migration_path = Path(directory) / "0001_registry.sql"
            migration_path.write_text("CREATE TABLE devices (id text);\n", encoding="utf-8")
            connection = FakeMigrationConnection(
                migration_privileges={
                    "has_usage": True,
                    "has_create": True,
                    "has_owner_rights": False,
                },
            )
            with (
                patch.object(migrate, "MIGRATIONS_DIR", Path(directory)),
                self.assertRaisesRegex(RuntimeError, "must own .* schema public"),
            ):
                migrate.apply_migrations(connection)

        statements = [sql for sql, _parameters in connection.executions]
        self.assertFalse(any("CREATE TABLE" in sql for sql in statements))
        self.assertFalse(any("0001_registry.sql" in sql for sql in statements))

    def test_migration_runner_rejects_registry_tables_owned_by_another_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            migration_path = Path(directory) / "0001_registry.sql"
            migration_path.write_text("CREATE TABLE devices (id text);\n", encoding="utf-8")
            connection = FakeMigrationConnection(
                object_ownership={
                    "objects_present": True,
                    "has_owner_rights": False,
                },
            )
            with (
                patch.object(migrate, "MIGRATIONS_DIR", Path(directory)),
                self.assertRaisesRegex(RuntimeError, "must own .* registry tables"),
            ):
                migrate.apply_migrations(
                    connection,
                    runtime_role="dealiot_registry_app",
                )

        statements = "\n".join(sql for sql, _parameters in connection.executions)
        self.assertNotIn("REVOKE ALL PRIVILEGES", statements)


if __name__ == "__main__":
    unittest.main()
