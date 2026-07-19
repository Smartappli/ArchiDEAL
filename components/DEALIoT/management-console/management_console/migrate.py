from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from management_console.device_registry import database_connection

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
DATABASE_ROLE_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def _preflight_migration_privileges(connection: Any) -> None:
    row = connection.execute(
        """
        SELECT has_schema_privilege(current_user, 'public', 'USAGE') AS has_usage,
               has_schema_privilege(current_user, 'public', 'CREATE') AS has_create,
               pg_has_role(current_user, nspowner, 'USAGE') AS has_owner_rights
        FROM pg_catalog.pg_namespace
        WHERE nspname = 'public'
        """,
    ).fetchone()
    if row is None:
        raise RuntimeError("DEALIoT registry schema public is missing")
    if not row["has_usage"] or not row["has_create"] or not row["has_owner_rights"]:
        raise RuntimeError(
            "DEALIoT registry migrator must own (or inherit ownership of) schema public "
            "and have USAGE, CREATE privileges",
        )


def _grant_runtime_privileges(connection: Any, runtime_role: str) -> None:
    if not DATABASE_ROLE_PATTERN.fullmatch(runtime_role):
        raise RuntimeError("DEALIoT registry runtime role has an invalid identifier")

    # The identifier is interpolated only after the strict PostgreSQL-role
    # validation above. Keeping the grants in the migration transaction makes
    # a production release fail closed if least-privilege setup is incomplete.
    quoted_role = f'"{runtime_role}"'
    ownership = connection.execute(
        """
        SELECT count(*) = 2 AS objects_present,
               bool_and(pg_has_role(current_user, table_record.relowner, 'USAGE'))
                   AS has_owner_rights
        FROM pg_catalog.pg_class AS table_record
        JOIN pg_catalog.pg_namespace AS schema_record
          ON schema_record.oid = table_record.relnamespace
        WHERE schema_record.nspname = 'public'
          AND table_record.relname IN ('devices', 'dealiot_schema_migrations')
          AND table_record.relkind IN ('r', 'p')
        """,
    ).fetchone()
    if ownership is None or not ownership["objects_present"] or not ownership["has_owner_rights"]:
        raise RuntimeError(
            "DEALIoT registry migrator must own (or inherit ownership of) registry tables",
        )
    # A direct REVOKE on the runtime role is not sufficient when privileges are
    # inherited through PostgreSQL's PUBLIC pseudo-role. Remove the ambient
    # grants first, reset direct grants, then make the runtime contract explicit.
    connection.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM PUBLIC")
    connection.execute(
        f"REVOKE ALL PRIVILEGES ON SCHEMA public FROM {quoted_role}",
    )
    connection.execute(
        f"GRANT USAGE ON SCHEMA public TO {quoted_role}",
    )
    connection.execute(
        "REVOKE ALL PRIVILEGES ON TABLE public.devices, "
        "public.dealiot_schema_migrations FROM PUBLIC",
    )
    connection.execute(
        "REVOKE ALL PRIVILEGES ON TABLE public.devices, "
        f"public.dealiot_schema_migrations FROM {quoted_role}",
    )
    connection.execute(
        f"GRANT SELECT, INSERT, UPDATE ON TABLE public.devices TO {quoted_role}",
    )
    connection.execute(
        f"GRANT SELECT ON TABLE public.dealiot_schema_migrations TO {quoted_role}",
    )
    _verify_runtime_privileges(connection, runtime_role)


def _verify_runtime_privileges(connection: Any, runtime_role: str) -> None:
    row = connection.execute(
        """
        SELECT has_schema_privilege(%s, 'public', 'USAGE') AS has_schema_usage,
               has_schema_privilege(%s, 'public', 'CREATE') AS has_schema_create,
               has_table_privilege(%s, 'public.devices', 'SELECT') AS has_device_select,
               has_table_privilege(%s, 'public.devices', 'INSERT') AS has_device_insert,
               has_table_privilege(%s, 'public.devices', 'UPDATE') AS has_device_update,
               has_table_privilege(%s, 'public.devices', 'DELETE') AS has_device_delete,
               has_table_privilege(%s, 'public.devices', 'TRUNCATE') AS has_device_truncate,
               has_table_privilege(%s, 'public.devices', 'REFERENCES')
                   AS has_device_references,
               has_table_privilege(%s, 'public.devices', 'TRIGGER') AS has_device_trigger,
               has_table_privilege(%s, 'public.dealiot_schema_migrations', 'SELECT')
                   AS has_migration_select,
               has_table_privilege(%s, 'public.dealiot_schema_migrations', 'INSERT')
                   AS has_migration_insert,
               has_table_privilege(%s, 'public.dealiot_schema_migrations', 'UPDATE')
                   AS has_migration_update,
               has_table_privilege(%s, 'public.dealiot_schema_migrations', 'DELETE')
                   AS has_migration_delete,
               has_table_privilege(%s, 'public.dealiot_schema_migrations', 'TRUNCATE')
                   AS has_migration_truncate,
               pg_has_role(%s, schema_record.nspowner, 'USAGE') AS owns_schema,
               pg_has_role(%s, devices_record.relowner, 'USAGE') AS owns_devices,
               pg_has_role(%s, migrations_record.relowner, 'USAGE') AS owns_migrations
        FROM pg_catalog.pg_namespace AS schema_record
        JOIN pg_catalog.pg_class AS devices_record
          ON devices_record.relnamespace = schema_record.oid
         AND devices_record.relname = 'devices'
        JOIN pg_catalog.pg_class AS migrations_record
          ON migrations_record.relnamespace = schema_record.oid
         AND migrations_record.relname = 'dealiot_schema_migrations'
        WHERE schema_record.nspname = 'public'
        """,
        (runtime_role,) * 17,
    ).fetchone()
    expected = {
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
    if row is None or any(bool(row[name]) is not value for name, value in expected.items()):
        message = f"DEALIoT registry runtime role {runtime_role} is not least-privilege"
        raise RuntimeError(message)


def apply_migrations(
    connection: Any,
    *,
    runtime_role: str | None = None,
) -> list[str]:
    applied: list[str] = []
    files = migration_files()
    if not files:
        raise RuntimeError("no DEALIoT registry migrations were packaged")
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('dealiot-registry-migrations'))")
        _preflight_migration_privileges(connection)
        # Migration SQL is intentionally schema-local. Pin its resolution so a role-level
        # search_path cannot redirect unqualified objects to an attacker-controlled schema.
        connection.execute("SET LOCAL search_path TO public, pg_catalog")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public.dealiot_schema_migrations (
                version varchar(255) PRIMARY KEY,
                checksum char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        rows = connection.execute(
            "SELECT version, checksum FROM public.dealiot_schema_migrations",
        ).fetchall()
        known = {row["version"]: row["checksum"] for row in rows}
        for path in files:
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if path.name in known:
                if known[path.name] != checksum:
                    message = f"migration checksum changed: {path.name}"
                    raise RuntimeError(message)
                continue
            connection.execute(sql)
            connection.execute(
                """
                INSERT INTO public.dealiot_schema_migrations (version, checksum)
                VALUES (%s, %s)
                """,
                (path.name, checksum),
            )
            applied.append(path.name)
        if runtime_role:
            _grant_runtime_privileges(connection, runtime_role)
    return applied


def main() -> None:
    runtime_role = os.getenv("DEALIOT_REGISTRY_RUNTIME_DATABASE_USER", "").strip()
    with database_connection() as connection:
        applied = apply_migrations(connection, runtime_role=runtime_role or None)
    if applied:
        print("Applied DEALIoT registry migrations: " + ", ".join(applied))
    else:
        print("DEALIoT registry schema is current.")


if __name__ == "__main__":
    main()
