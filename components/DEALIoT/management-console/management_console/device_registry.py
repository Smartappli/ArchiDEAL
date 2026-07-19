from __future__ import annotations

import hashlib
import importlib
import os
import re
from contextlib import contextmanager
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
CAPABILITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
ACTIVE_STATUSES = frozenset({"provisioning", "active", "suspended"})
ALL_STATUSES = ACTIVE_STATUSES | {"retired"}
WRITABLE_FIELDS = (
    "display_name",
    "kind",
    "status",
    "mqtt_topic",
    "capabilities",
    "settings",
    "labels",
)
DEVICE_COLUMNS = (
    "device_id, display_name, kind, status, mqtt_topic, capabilities, settings, labels, "
    "revision, created_at, updated_at, retired_at, created_by, updated_by"
)
REQUIRED_DEVICE_COLUMN_FINGERPRINT = {
    "device_id": ("varchar", 128, False),
    "display_name": ("varchar", 160, False),
    "kind": ("varchar", 64, False),
    "status": ("varchar", 24, False),
    "mqtt_topic": ("varchar", 512, True),
    "capabilities": ("jsonb", None, False),
    "settings": ("jsonb", None, False),
    "labels": ("jsonb", None, False),
    "revision": ("int8", None, False),
    "created_at": ("timestamptz", None, False),
    "updated_at": ("timestamptz", None, False),
    "retired_at": ("timestamptz", None, True),
    "created_by": ("varchar", 255, False),
    "updated_by": ("varchar", 255, False),
}
REQUIRED_DEVICE_CONSTRAINTS = {
    "devices_pkey": "p",
    "devices_device_id_format": "c",
    "devices_kind_format": "c",
    "devices_status_valid": "c",
    "devices_revision_positive": "c",
    "devices_retirement_consistent": "c",
}
REQUIRED_DEVICE_INDEXES = {
    "devices_pkey",
    "devices_status_device_id_idx",
    "devices_kind_device_id_idx",
    "devices_updated_at_idx",
}
SENSITIVE_KEY_COMPONENTS = frozenset(
    {
        "auth",
        "authorization",
        "bearer",
        "credential",
        "credentials",
        "passwd",
        "password",
        "pwd",
        "secret",
        "secrets",
        "token",
        "tokens",
    },
)
SENSITIVE_COMPACT_KEYS = frozenset(
    {
        "accesskey",
        "apikey",
        "bearertoken",
        "clientkey",
        "clientsecret",
        "privatekey",
        "refreshtoken",
        "signingkey",
    },
)
SENSITIVE_KEY_SEQUENCES = frozenset(
    {
        ("access", "key"),
        ("api", "key"),
        ("client", "key"),
        ("private", "key"),
        ("signing", "key"),
    },
)
MAX_PORT = 65535
MAX_CONNECT_TIMEOUT_SECONDS = 30
MAX_MQTT_TOPIC_LENGTH = 512
MAX_CAPABILITIES = 64
MAX_LABELS = 64
MAX_LABEL_KEY_LENGTH = 64
MAX_LABEL_VALUE_LENGTH = 256
MAX_PAGE_SIZE = 200
MAX_SEARCH_LENGTH = 160
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
MIGRATION_VERSION_PATTERN = re.compile(r"^[0-9]{4}_[A-Za-z0-9][A-Za-z0-9_-]*\.sql$")
MIGRATION_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DeviceRegistryError(Exception):
    """Base class for errors safe to translate at the HTTP boundary."""


class RegistryUnavailableError(DeviceRegistryError):
    """The registry cannot reach a configured and migrated PostgreSQL database."""


class DeviceValidationError(DeviceRegistryError):
    """A device payload or query parameter is invalid."""


class DeviceNotFoundError(DeviceRegistryError):
    """The requested active device does not exist."""


class DeviceConflictError(DeviceRegistryError):
    """A device with the same immutable identifier already exists."""


class RevisionConflictError(DeviceRegistryError):
    """The supplied revision does not match the persisted device."""


def database_is_configured() -> bool:
    return bool(os.getenv("DEALIOT_REGISTRY_DATABASE_HOST", "").strip())


def database_parameters() -> dict[str, Any]:
    names = {
        "host": "DEALIOT_REGISTRY_DATABASE_HOST",
        "dbname": "DEALIOT_REGISTRY_DATABASE_NAME",
        "user": "DEALIOT_REGISTRY_DATABASE_USER",
        "password": "DEALIOT_REGISTRY_DATABASE_PASSWORD",
    }
    values = {key: os.getenv(name, "").strip() for key, name in names.items()}
    missing = sorted(names[key] for key, value in values.items() if not value)
    if missing:
        raise RegistryUnavailableError("incomplete database configuration: " + ", ".join(missing))

    try:
        port = int(os.getenv("DEALIOT_REGISTRY_DATABASE_PORT", "5432"))
        connect_timeout = int(os.getenv("DEALIOT_REGISTRY_DATABASE_CONNECT_TIMEOUT", "3"))
    except ValueError as exc:
        raise RegistryUnavailableError("database port and timeout must be integers") from exc
    if not 1 <= port <= MAX_PORT or not 1 <= connect_timeout <= MAX_CONNECT_TIMEOUT_SECONDS:
        raise RegistryUnavailableError("database port or timeout is outside its allowed range")

    parameters: dict[str, Any] = {
        **values,
        "port": port,
        "connect_timeout": connect_timeout,
        "sslmode": os.getenv("DEALIOT_REGISTRY_DATABASE_SSLMODE", "prefer").strip() or "prefer",
        "application_name": "dealiot-management-console",
        "options": "-c search_path=pg_catalog,public",
    }
    sslrootcert = os.getenv("DEALIOT_REGISTRY_DATABASE_SSLROOTCERT", "").strip()
    if sslrootcert:
        parameters["sslrootcert"] = sslrootcert
    return parameters


@contextmanager
def database_connection() -> Iterator[Any]:
    try:
        psycopg = importlib.import_module("psycopg")
        dict_row = importlib.import_module("psycopg.rows").dict_row
    except ModuleNotFoundError as exc:
        raise RegistryUnavailableError("the PostgreSQL driver is not installed") from exc

    try:
        connection = psycopg.connect(**database_parameters(), row_factory=dict_row)
    except Exception as exc:
        raise RegistryUnavailableError("the PostgreSQL registry is unavailable") from exc
    try:
        with connection:
            yield connection
    except DeviceRegistryError:
        raise
    except psycopg.errors.UniqueViolation as exc:
        # The registry currently has one public uniqueness contract: device_id.
        # Keep concurrent creates on the documented 409 path rather than
        # classifying a database constraint race as an outage.
        raise DeviceConflictError("device_id already exists") from exc
    except psycopg.Error as exc:
        raise RegistryUnavailableError(
            "the PostgreSQL registry operation failed",
        ) from exc
    finally:
        connection.close()


def _jsonb(value: Any) -> Any:
    try:
        jsonb_type = importlib.import_module("psycopg.types.json").Jsonb
    except ModuleNotFoundError as exc:
        raise RegistryUnavailableError("the PostgreSQL driver is not installed") from exc
    return jsonb_type(value)


def required_migrations() -> dict[str, str]:
    migrations = {
        path.name: hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8"),
        ).hexdigest()
        for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    }
    if not migrations:
        raise RegistryUnavailableError("no DEALIoT registry migrations were packaged")
    return migrations


def required_migration_versions() -> tuple[str, ...]:
    return tuple(required_migrations())


def check_readiness() -> None:
    """Validate known migrations while tolerating an ordered forward-applied suffix.

    A previous application image may remain healthy during an expand/contract rollback when the
    database already contains migrations from a newer image.  Only migrations strictly after the
    complete packaged prefix are tolerated; every migration known to this image must still be
    present, ordered and checksum-identical.
    """
    expected = required_migrations()
    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('public.devices')::text AS devices_table,
                   to_regclass('public.dealiot_schema_migrations')::text
                       AS migrations_table
            """,
        ).fetchone()
        if row is None or row["devices_table"] is None or row["migrations_table"] is None:
            raise RegistryUnavailableError("the DEALIoT registry schema is missing")
        column_rows = connection.execute(
            """
            SELECT column_name, udt_name, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'devices'
            """,
        ).fetchall()
        constraint_rows = connection.execute(
            """
            SELECT constraint_record.conname, constraint_record.contype
            FROM pg_catalog.pg_constraint AS constraint_record
            JOIN pg_catalog.pg_class AS table_record
              ON table_record.oid = constraint_record.conrelid
            JOIN pg_catalog.pg_namespace AS schema_record
              ON schema_record.oid = table_record.relnamespace
            WHERE schema_record.nspname = 'public' AND table_record.relname = 'devices'
            """,
        ).fetchall()
        index_rows = connection.execute(
            """
            SELECT indexname
            FROM pg_catalog.pg_indexes
            WHERE schemaname = 'public' AND tablename = 'devices'
            """,
        ).fetchall()
        # This is also an effective SELECT privilege check, not only a catalogue lookup.
        connection.execute("SELECT revision FROM public.devices WHERE FALSE").fetchall()
        rows = connection.execute(
            """
            SELECT version, checksum
            FROM public.dealiot_schema_migrations
            ORDER BY applied_at ASC, version ASC
            """,
        ).fetchall()

        if os.getenv("MANAGEMENT_CONSOLE_PRODUCTION_MODE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            privileges = connection.execute(
                """
                SELECT has_schema_privilege(current_user, 'public', 'USAGE')
                           AS has_schema_usage,
                       has_schema_privilege(current_user, 'public', 'CREATE')
                           AS has_schema_create,
                       has_table_privilege(current_user, 'public.devices', 'SELECT')
                           AS has_device_select,
                       has_table_privilege(current_user, 'public.devices', 'INSERT')
                           AS has_device_insert,
                       has_table_privilege(current_user, 'public.devices', 'UPDATE')
                           AS has_device_update,
                       has_table_privilege(current_user, 'public.devices', 'DELETE')
                           AS has_device_delete,
                       has_table_privilege(current_user, 'public.devices', 'TRUNCATE')
                           AS has_device_truncate,
                       has_table_privilege(current_user, 'public.devices', 'REFERENCES')
                           AS has_device_references,
                       has_table_privilege(current_user, 'public.devices', 'TRIGGER')
                           AS has_device_trigger,
                       has_table_privilege(
                           current_user,
                           'public.dealiot_schema_migrations',
                           'SELECT'
                       ) AS has_migration_select,
                       has_table_privilege(
                           current_user,
                           'public.dealiot_schema_migrations',
                           'INSERT'
                       ) AS has_migration_insert,
                       has_table_privilege(
                           current_user,
                           'public.dealiot_schema_migrations',
                           'UPDATE'
                       ) AS has_migration_update,
                       has_table_privilege(
                           current_user,
                           'public.dealiot_schema_migrations',
                           'DELETE'
                       ) AS has_migration_delete,
                       has_table_privilege(
                           current_user,
                           'public.dealiot_schema_migrations',
                           'TRUNCATE'
                       ) AS has_migration_truncate,
                       pg_has_role(current_user, schema_record.nspowner, 'USAGE')
                           AS owns_schema,
                       pg_has_role(current_user, devices_record.relowner, 'USAGE')
                           AS owns_devices,
                       pg_has_role(current_user, migrations_record.relowner, 'USAGE')
                           AS owns_migrations
                FROM pg_catalog.pg_namespace AS schema_record
                JOIN pg_catalog.pg_class AS devices_record
                  ON devices_record.relnamespace = schema_record.oid
                 AND devices_record.relname = 'devices'
                JOIN pg_catalog.pg_class AS migrations_record
                  ON migrations_record.relnamespace = schema_record.oid
                 AND migrations_record.relname = 'dealiot_schema_migrations'
                WHERE schema_record.nspname = 'public'
                """,
            ).fetchone()
            expected_privileges = {
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
            if privileges is None or any(
                bool(privileges[name]) is not expected
                for name, expected in expected_privileges.items()
            ):
                raise RegistryUnavailableError(
                    "the DEALIoT registry runtime database privileges are not least-privilege",
                )

    columns = {
        str(column["column_name"]): (
            str(column["udt_name"]),
            column["character_maximum_length"],
            str(column["is_nullable"]) == "YES",
        )
        for column in column_rows
    }
    invalid_columns = [
        name
        for name, fingerprint in REQUIRED_DEVICE_COLUMN_FINGERPRINT.items()
        if columns.get(name) != fingerprint
    ]
    constraints = {
        str(constraint["conname"]): str(constraint["contype"]) for constraint in constraint_rows
    }
    invalid_constraints = [
        name
        for name, constraint_type in REQUIRED_DEVICE_CONSTRAINTS.items()
        if constraints.get(name) != constraint_type
    ]
    indexes = {str(index["indexname"]) for index in index_rows}
    invalid_indexes = sorted(REQUIRED_DEVICE_INDEXES - indexes)
    invalid_structure = invalid_columns + invalid_constraints + invalid_indexes
    if invalid_structure:
        raise RegistryUnavailableError(
            "the DEALIoT registry schema fingerprint is invalid: " + ", ".join(invalid_structure),
        )
    applied_rows = [
        (str(applied_row["version"]), str(applied_row["checksum"])) for applied_row in rows
    ]
    applied = dict(applied_rows)
    missing = sorted(set(expected) - set(applied))
    if missing:
        raise RegistryUnavailableError(
            "the DEALIoT registry schema is behind: " + ", ".join(missing),
        )
    changed = sorted(
        version for version, checksum in expected.items() if applied[version] != checksum
    )
    if changed:
        raise RegistryUnavailableError(
            "the DEALIoT registry migration checksum changed: " + ", ".join(changed),
        )

    expected_versions = list(expected)
    applied_versions = [version for version, _checksum in applied_rows]
    if applied_versions[: len(expected_versions)] != expected_versions:
        raise RegistryUnavailableError(
            "the DEALIoT registry migration order does not match the packaged migration prefix",
        )

    forward_rows = applied_rows[len(expected_versions) :]
    forward_versions = [version for version, _checksum in forward_rows]
    malformed = [
        version
        for version, checksum in forward_rows
        if not MIGRATION_VERSION_PATTERN.fullmatch(version)
        or not MIGRATION_CHECKSUM_PATTERN.fullmatch(checksum)
    ]
    if malformed:
        raise RegistryUnavailableError(
            "the DEALIoT registry has invalid forward migration metadata: " + ", ".join(malformed),
        )
    if forward_versions != sorted(forward_versions) or any(
        version <= expected_versions[-1] for version in forward_versions
    ):
        raise RegistryUnavailableError(
            "the DEALIoT registry forward migrations are not a strictly ordered suffix",
        )


def _required_string(payload: dict[str, Any], name: str, maximum: int) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        message = f"{name} must be a non-empty string"
        raise DeviceValidationError(message)
    normalized = value.strip()
    if len(normalized) > maximum:
        message = f"{name} exceeds {maximum} characters"
        raise DeviceValidationError(message)
    return normalized


def validate_device_id(value: Any) -> str:
    if not isinstance(value, str) or not DEVICE_ID_PATTERN.fullmatch(value):
        raise DeviceValidationError(
            "device_id must match [A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        )
    return value


def _validate_kind(value: Any) -> str:
    if not isinstance(value, str) or not KIND_PATTERN.fullmatch(value):
        raise DeviceValidationError("kind must be a lowercase device type identifier")
    return value


def _validate_status(value: Any) -> str:
    if value not in ACTIVE_STATUSES:
        raise DeviceValidationError(
            "status must be one of provisioning, active or suspended; use DELETE to retire",
        )
    return str(value)


def _validate_mqtt_topic(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DeviceValidationError("mqtt_topic must be a string or null")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_MQTT_TOPIC_LENGTH or "\x00" in normalized:
        raise DeviceValidationError("mqtt_topic must contain between 1 and 512 safe characters")
    return normalized


def _validate_capabilities(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_CAPABILITIES:
        raise DeviceValidationError("capabilities must be an array containing at most 64 values")
    capabilities: list[str] = []
    for capability in value:
        if not isinstance(capability, str) or not CAPABILITY_PATTERN.fullmatch(capability):
            raise DeviceValidationError("capabilities contain an invalid identifier")
        if capability not in capabilities:
            capabilities.append(capability)
    return capabilities


def _reject_sensitive_keys(value: Any, path: str = "settings") -> None:
    if isinstance(value, dict):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                message = f"{path} keys must be strings"
                raise DeviceValidationError(message)
            snake_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw_key)
            normalized_key = re.sub(r"[^a-z0-9]+", "_", snake_key.casefold()).strip("_")
            key_components = tuple(part for part in normalized_key.split("_") if part)
            adjacent_pairs = set(pairwise(key_components))
            if (
                set(key_components) & SENSITIVE_KEY_COMPONENTS
                or normalized_key.replace("_", "") in SENSITIVE_COMPACT_KEYS
                or adjacent_pairs & SENSITIVE_KEY_SEQUENCES
            ):
                message = f"{path}.{raw_key} must be stored in a secret manager"
                raise DeviceValidationError(message)
            _reject_sensitive_keys(nested, f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_keys(nested, f"{path}[{index}]")


def _validate_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        message = f"{name} must be a JSON object"
        raise DeviceValidationError(message)
    _reject_sensitive_keys(value, name)
    return value


def _validate_labels(value: Any) -> dict[str, str]:
    labels = _validate_object(value, "labels")
    if len(labels) > MAX_LABELS:
        raise DeviceValidationError("labels must contain at most 64 entries")
    for key, label_value in labels.items():
        if (
            len(key) > MAX_LABEL_KEY_LENGTH
            or not isinstance(label_value, str)
            or len(label_value) > MAX_LABEL_VALUE_LENGTH
        ):
            raise DeviceValidationError("label keys and values exceed their allowed format")
    return labels


def _validate_fields(payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    permitted_identity = set() if partial else {"device_id"}
    unknown = sorted(set(payload) - set(WRITABLE_FIELDS) - permitted_identity)
    if unknown:
        raise DeviceValidationError("unknown fields: " + ", ".join(unknown))

    validated: dict[str, Any] = {}
    validators = {
        "display_name": lambda value: _required_string({"value": value}, "value", 160),
        "kind": _validate_kind,
        "status": _validate_status,
        "mqtt_topic": _validate_mqtt_topic,
        "capabilities": _validate_capabilities,
        "settings": lambda value: _validate_object(value, "settings"),
        "labels": _validate_labels,
    }
    for name, validator in validators.items():
        if name in payload:
            validated[name] = validator(payload[name])

    if partial:
        if not validated:
            raise DeviceValidationError("PATCH must contain at least one writable field")
    else:
        validated["device_id"] = validate_device_id(payload.get("device_id"))
        for required in ("display_name", "kind"):
            if required not in validated:
                message = f"{required} is required"
                raise DeviceValidationError(message)
        validated.setdefault("status", "provisioning")
        validated.setdefault("mqtt_topic", None)
        validated.setdefault("capabilities", [])
        validated.setdefault("settings", {})
        validated.setdefault("labels", {})
    return validated


def validate_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _validate_fields(payload, partial=False)


def validate_patch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _validate_fields(payload, partial=True)


def _serialize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def serialize_device(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": row["device_id"],
        "display_name": row["display_name"],
        "kind": row["kind"],
        "status": row["status"],
        "mqtt_topic": row["mqtt_topic"],
        "capabilities": row["capabilities"],
        "settings": row["settings"],
        "labels": row["labels"],
        "revision": row["revision"],
        "created_at": _serialize_timestamp(row["created_at"]),
        "updated_at": _serialize_timestamp(row["updated_at"]),
        "retired_at": _serialize_timestamp(row["retired_at"]),
        "created_by": row["created_by"],
        "updated_by": row["updated_by"],
    }


def _actor(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DeviceValidationError("the authenticated principal has no stable subject")
    return normalized[:255]


def create_device(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    values = validate_create_payload(payload)
    principal = _actor(actor)
    sql = """
        INSERT INTO public.devices (
            device_id, display_name, kind, status, mqtt_topic, capabilities, settings, labels,
            created_by, updated_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (device_id) DO NOTHING
        RETURNING
            device_id, display_name, kind, status, mqtt_topic, capabilities, settings, labels,
            revision, created_at, updated_at, retired_at, created_by, updated_by
    """
    parameters = (
        values["device_id"],
        values["display_name"],
        values["kind"],
        values["status"],
        values["mqtt_topic"],
        _jsonb(values["capabilities"]),
        _jsonb(values["settings"]),
        _jsonb(values["labels"]),
        principal,
        principal,
    )
    with database_connection() as connection:
        row = connection.execute(sql, parameters).fetchone()
    if row is None:
        raise DeviceConflictError(values["device_id"])
    return serialize_device(row)


def get_device(device_id: str) -> dict[str, Any]:
    identifier = validate_device_id(device_id)
    with database_connection() as connection:
        row = connection.execute(
            # The only interpolation is the module-owned, fixed column list.
            f"SELECT {DEVICE_COLUMNS} FROM public.devices "  # noqa: S608
            "WHERE device_id = %s AND retired_at IS NULL",
            (identifier,),
        ).fetchone()
    if row is None:
        raise DeviceNotFoundError(identifier)
    return serialize_device(row)


def list_devices(
    *,
    status: str | None = None,
    kind: str | None = None,
    query: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise DeviceValidationError("limit must be between 1 and 200")
    clauses = ["retired_at IS NULL"]
    parameters: list[Any] = []
    if status is not None:
        clauses.append("status = %s")
        parameters.append(_validate_status(status))
    if kind is not None:
        clauses.append("kind = %s")
        parameters.append(_validate_kind(kind))
    if query is not None:
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > MAX_SEARCH_LENGTH:
            raise DeviceValidationError("q must contain between 1 and 160 characters")
        clauses.append(
            "(device_id ILIKE %s ESCAPE '\\' OR display_name ILIKE %s ESCAPE '\\')",
        )
        escaped_query = (
            normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        search = f"%{escaped_query}%"
        parameters.extend((search, search))
    if cursor is not None:
        clauses.append("device_id > %s")
        parameters.append(validate_device_id(cursor))
    parameters.append(limit + 1)
    sql = (
        f"SELECT {DEVICE_COLUMNS} FROM public.devices WHERE {' AND '.join(clauses)} "  # noqa: S608
        "ORDER BY device_id ASC LIMIT %s"
    )
    with database_connection() as connection:
        rows = connection.execute(sql, parameters).fetchall()
    has_more = len(rows) > limit
    selected = rows[:limit]
    return {
        "devices": [serialize_device(row) for row in selected],
        "next_cursor": selected[-1]["device_id"] if has_more and selected else None,
    }


def _assert_existing_revision(connection: Any, device_id: str, revision: int) -> None:
    row = connection.execute(
        "SELECT revision FROM public.devices WHERE device_id = %s AND retired_at IS NULL",
        (device_id,),
    ).fetchone()
    if row is None:
        raise DeviceNotFoundError(device_id)
    message = f"expected revision {row['revision']}, received {revision}"
    raise RevisionConflictError(message)


def update_device(
    device_id: str,
    payload: dict[str, Any],
    actor: str,
    revision: int,
) -> dict[str, Any]:
    identifier = validate_device_id(device_id)
    values = validate_patch_payload(payload)
    principal = _actor(actor)
    assignments: list[str] = []
    parameters: list[Any] = []
    for name in WRITABLE_FIELDS:
        if name not in values:
            continue
        assignments.append(f"{name} = %s")
        value = values[name]
        is_json = name in {"capabilities", "settings", "labels"}
        parameters.append(_jsonb(value) if is_json else value)
    assignments.extend(("revision = revision + 1", "updated_at = now()", "updated_by = %s"))
    parameters.extend((principal, identifier, revision))
    sql = (
        f"UPDATE public.devices SET {', '.join(assignments)} "  # noqa: S608
        "WHERE device_id = %s AND revision = %s AND retired_at IS NULL "
        f"RETURNING {DEVICE_COLUMNS}"
    )
    with database_connection() as connection:
        row = connection.execute(sql, parameters).fetchone()
        if row is None:
            _assert_existing_revision(connection, identifier, revision)
    return serialize_device(row)


def retire_device(device_id: str, actor: str, revision: int) -> int:
    identifier = validate_device_id(device_id)
    principal = _actor(actor)
    with database_connection() as connection:
        row = connection.execute(
            """
            UPDATE public.devices
            SET status = 'retired', retired_at = now(), updated_at = now(),
                updated_by = %s, revision = revision + 1
            WHERE device_id = %s AND revision = %s AND retired_at IS NULL
            RETURNING revision
            """,
            (principal, identifier, revision),
        ).fetchone()
        if row is None:
            _assert_existing_revision(connection, identifier, revision)
    return int(row["revision"])
