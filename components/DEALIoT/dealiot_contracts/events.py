from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

DLQ_TOPIC = "dlq.events"
STATE_LATEST_TOPIC = "state.latest"
RAW_SENSOR_TOPIC = "raw.sensor"
RAW_GPS_TOPIC = "raw.gps"
RAW_IMAGE2D_META_TOPIC = "raw.image2d.meta"
RAW_IMAGE3D_META_TOPIC = "raw.image3d.meta"
RAW_VIDEO2D_META_TOPIC = "raw.video2d.meta"
RAW_VIDEO3D_META_TOPIC = "raw.video3d.meta"
DGA_DATA_PRODUCTS_TOPIC = "governance.data.products"
DGA_ACCESS_REQUESTS_TOPIC = "governance.access.requests"
DGA_PERMISSION_EVENTS_TOPIC = "governance.permission.events"
DGA_INTERMEDIATION_LOG_TOPIC = "governance.intermediation.log"
DGA_TRANSFER_NOTICES_TOPIC = "governance.transfer.notices"
DGA_RESEARCH_PROJECTS_TOPIC = "governance.research.projects"
DGA_RESEARCH_OUTPUTS_TOPIC = "governance.research.outputs"
DGA_DATASET_CATALOG_TOPIC = "governance.dataset.catalog"
DGA_DATA_MANAGEMENT_PLANS_TOPIC = "governance.data_management_plans"
DGA_REPOSITORY_EXPORTS_TOPIC = "governance.repository.exports"
DATA_ACT_PRODUCT_CATALOG_TOPIC = "dataact.product.catalog"
DATA_ACT_USER_ACCESS_REQUESTS_TOPIC = "dataact.user.access.requests"
DATA_ACT_THIRD_PARTY_SHARING_TOPIC = "dataact.third_party.sharing"
DATA_ACT_USER_EXPORTS_TOPIC = "dataact.user.exports"
DATA_ACT_SAFEGUARDS_TOPIC = "dataact.safeguards"
DATA_ACT_LEGAL_BASIS_CHECKS_TOPIC = "dataact.legal_basis.checks"
SECURITY_ASSET_INVENTORY_TOPIC = "security.asset.inventory"
SECURITY_INCIDENT_EVENTS_TOPIC = "security.incident.events"
SECURITY_VULNERABILITY_FINDINGS_TOPIC = "security.vulnerability.findings"
SECURITY_SBOM_ATTESTATIONS_TOPIC = "security.sbom.attestations"
SECURITY_PATCH_EVENTS_TOPIC = "security.patch.events"
RESILIENCE_BACKUP_TESTS_TOPIC = "resilience.backup.tests"
RESILIENCE_OPERATIONAL_RISK_TOPIC = "resilience.operational.risk"
RESILIENCE_THIRD_PARTY_RISK_TOPIC = "resilience.third_party.risk"
COMPLIANCE_SCOPE_DECISIONS_TOPIC = "compliance.scope.decisions"
COMPLIANCE_CONTROL_ASSESSMENTS_TOPIC = "compliance.control.assessments"
COMPLIANCE_REPORTING_CHANNELS_TOPIC = "compliance.reporting.channels"
COMPLIANCE_LEGAL_DOSSIER_TOPIC = "compliance.legal.dossier"
CRA_PRODUCT_LIFECYCLE_TOPIC = "cra.product.lifecycle"
LATITUDE_MIN = -90
LATITUDE_MAX = 90
LONGITUDE_MIN = -180
LONGITUDE_MAX = 180
HEADING_MIN = 0
HEADING_MAX = 360
EVENT_ID_LENGTH = 64
SEMANTIC_VERSION_PARTS = 3

MEDIA_TOPICS = {
    RAW_IMAGE2D_META_TOPIC,
    RAW_IMAGE3D_META_TOPIC,
    RAW_VIDEO2D_META_TOPIC,
    RAW_VIDEO3D_META_TOPIC,
}

REQUIRED_FIELDS: dict[str, set[str]] = {
    RAW_SENSOR_TOPIC: {"device_id", "timestamp", "payload"},
    RAW_GPS_TOPIC: {"device_id", "timestamp", "latitude", "longitude"},
    RAW_IMAGE2D_META_TOPIC: {
        "device_id",
        "timestamp",
        "bucket",
        "object_key",
        "object_uri",
        "format",
    },
    RAW_IMAGE3D_META_TOPIC: {
        "device_id",
        "timestamp",
        "bucket",
        "object_key",
        "object_uri",
        "format",
    },
    RAW_VIDEO2D_META_TOPIC: {
        "device_id",
        "timestamp",
        "bucket",
        "object_key",
        "object_uri",
        "format",
    },
    RAW_VIDEO3D_META_TOPIC: {
        "device_id",
        "timestamp",
        "bucket",
        "object_key",
        "object_uri",
        "format",
    },
}

MEDIA_ALLOWED_FIELDS: dict[str, set[str]] = {
    RAW_IMAGE2D_META_TOPIC: {
        "bucket",
        "camera_id",
        "checksum",
        "content_type",
        "device_id",
        "format",
        "height",
        "ingested_at",
        "event_id",
        "occurred_at",
        "schema_version",
        "mqtt_topic",
        "object_key",
        "object_uri",
        "qos",
        "retain",
        "size_bytes",
        "source",
        "tags",
        "timestamp",
        "width",
    },
    RAW_IMAGE3D_META_TOPIC: {
        "bucket",
        "capture_type",
        "checksum",
        "content_type",
        "coordinate_frame",
        "device_id",
        "format",
        "ingested_at",
        "event_id",
        "occurred_at",
        "schema_version",
        "mqtt_topic",
        "object_key",
        "object_uri",
        "point_count",
        "qos",
        "retain",
        "sensor_id",
        "size_bytes",
        "source",
        "tags",
        "timestamp",
    },
    RAW_VIDEO2D_META_TOPIC: {
        "bucket",
        "camera_id",
        "checksum",
        "codec",
        "content_type",
        "device_id",
        "duration_ms",
        "format",
        "frame_count",
        "frame_rate",
        "height",
        "ingested_at",
        "event_id",
        "occurred_at",
        "schema_version",
        "mqtt_topic",
        "object_key",
        "object_uri",
        "qos",
        "retain",
        "size_bytes",
        "source",
        "tags",
        "timestamp",
        "width",
    },
    RAW_VIDEO3D_META_TOPIC: {
        "bucket",
        "checksum",
        "codec",
        "content_type",
        "device_id",
        "duration_ms",
        "format",
        "frame_count",
        "frame_rate",
        "height",
        "ingested_at",
        "event_id",
        "occurred_at",
        "schema_version",
        "mqtt_topic",
        "object_key",
        "object_uri",
        "qos",
        "representation",
        "retain",
        "rig_id",
        "size_bytes",
        "source",
        "tags",
        "timestamp",
        "views",
        "width",
    },
}

STRING_FIELDS = {
    "bucket",
    "camera_id",
    "capture_type",
    "checksum",
    "codec",
    "content_type",
    "coordinate_frame",
    "device_id",
    "event_id",
    "format",
    "ingested_at",
    "mqtt_topic",
    "object_key",
    "object_uri",
    "occurred_at",
    "representation",
    "rig_id",
    "schema_version",
    "sensor_id",
    "source",
    "timestamp",
}

INTEGER_FIELDS = {
    "duration_ms",
    "frame_count",
    "height",
    "point_count",
    "qos",
    "size_bytes",
    "views",
    "width",
}

NUMBER_FIELDS = {"altitude_m", "frame_rate", "heading_deg", "latitude", "longitude", "speed_m_s"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def event_time(record: dict[str, Any]) -> str:
    value = record.get("timestamp") or record.get("ingested_at")
    if value is None:
        return ""
    return str(value)


def build_dlq_event(
    *,
    source: str,
    intended_topic: str,
    errors: list[str],
    raw_event: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "source": source,
        "intended_topic": intended_topic,
        "source_topic": raw_event.get("source_topic")
        or raw_event.get("mqtt_topic")
        or raw_event.get("object_uri", ""),
        "device_id": str(raw_event.get("device_id", "unknown")),
        "errors": errors,
        "raw_event": raw_event,
    }


def validate_event(topic: str, event: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    required = REQUIRED_FIELDS.get(topic)
    if required is None:
        return errors

    errors.extend(
        f"missing required field: {field}"
        for field in sorted(required)
        if field not in event or event[field] in (None, "")
    )

    if topic in MEDIA_TOPICS:
        allowed = MEDIA_ALLOWED_FIELDS[topic]
        errors.extend(
            f"field not allowed by {topic}: {field}" for field in sorted(set(event) - allowed)
        )

    _validate_types(event, errors)
    _validate_ranges(event, errors)
    _validate_envelope(event, errors)
    return errors


def _validate_envelope(event: dict[str, Any], errors: list[str]) -> None:
    event_id = event.get("event_id")
    if event_id is not None and (
        not isinstance(event_id, str)
        or len(event_id) != EVENT_ID_LENGTH
        or any(character not in "0123456789abcdef" for character in event_id)
    ):
        errors.append("event_id must be a 64-character hexadecimal SHA-256 digest")

    schema_version = event.get("schema_version")
    if schema_version is not None and (
        not isinstance(schema_version, str)
        or len(schema_version.split(".")) != SEMANTIC_VERSION_PARTS
        or not all(part.isdigit() for part in schema_version.split("."))
    ):
        errors.append("schema_version must use semantic version format")


def _validate_types(event: dict[str, Any], errors: list[str]) -> None:
    errors.extend(
        f"field must be a string: {field}"
        for field in sorted(STRING_FIELDS & set(event))
        if event[field] is not None and not isinstance(event[field], str)
    )

    errors.extend(
        f"field must be an integer: {field}"
        for field in sorted(INTEGER_FIELDS & set(event))
        if event[field] is not None and not isinstance(event[field], int)
    )

    errors.extend(
        f"field must be numeric: {field}"
        for field in sorted(NUMBER_FIELDS & set(event))
        if event[field] is not None and not isinstance(event[field], int | float)
    )

    if "payload" in event and not isinstance(event["payload"], dict):
        errors.append("field must be an object: payload")
    if "tags" in event and not isinstance(event["tags"], dict):
        errors.append("field must be an object: tags")
    if "retain" in event and not isinstance(event["retain"], bool):
        errors.append("field must be a boolean: retain")


def _validate_ranges(event: dict[str, Any], errors: list[str]) -> None:
    latitude = event.get("latitude")
    if isinstance(latitude, int | float) and not LATITUDE_MIN <= latitude <= LATITUDE_MAX:
        errors.append("latitude out of range: -90..90")

    longitude = event.get("longitude")
    if isinstance(longitude, int | float) and not LONGITUDE_MIN <= longitude <= LONGITUDE_MAX:
        errors.append("longitude out of range: -180..180")

    heading = event.get("heading_deg")
    if isinstance(heading, int | float) and not HEADING_MIN <= heading <= HEADING_MAX:
        errors.append("heading_deg out of range: 0..360")

    non_negative = [
        "duration_ms",
        "frame_count",
        "point_count",
        "size_bytes",
        "speed_m_s",
    ]
    errors.extend(
        f"{field} must be non-negative"
        for field in non_negative
        if isinstance(event.get(field), int | float) and event[field] < 0
    )

    positive = ["frame_rate", "height", "views", "width"]
    errors.extend(
        f"{field} must be positive"
        for field in positive
        if isinstance(event.get(field), int | float) and event[field] <= 0
    )
