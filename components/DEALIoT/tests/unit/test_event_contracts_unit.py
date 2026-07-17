from __future__ import annotations

import json
import unittest
from pathlib import Path

from dealiot_contracts import DLQ_TOPIC, build_dlq_event, event_time, validate_event


class EventContractsUnitTests(unittest.TestCase):
    def test_apicurio_raw_schemas_share_the_envelope_contract(self) -> None:
        bootstrap_dir = Path(__file__).resolve().parents[2] / "apicurio" / "bootstrap"
        for schema_path in bootstrap_dir.glob("raw.*.json"):
            with self.subTest(schema=schema_path.name):
                artifact = json.loads(schema_path.read_text(encoding="utf-8"))
                schema = json.loads(artifact["firstVersion"]["content"]["content"])
                properties = schema["properties"]
                self.assertEqual(properties["event_id"]["pattern"], "^[0-9a-f]{64}$")
                self.assertEqual(
                    properties["schema_version"]["pattern"],
                    r"^[0-9]+\.[0-9]+\.[0-9]+$",
                )

    def test_shared_envelope_fixtures_match_python_validation(self) -> None:
        fixtures_path = (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "fixtures"
            / "event-envelope-cases.json"
        )
        cases = json.loads(fixtures_path.read_text(encoding="utf-8"))

        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    validate_event(case["topic"], case["event"]),
                    case["expected_errors"],
                )

    def test_validates_required_media_metadata(self) -> None:
        event = {
            "device_id": "cam-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bucket": "media-raw-2d-images",
            "object_key": "cam-1/frame.jpg",
            "object_uri": "s3://media-raw-2d-images/cam-1/frame.jpg",
            "format": "jpg",
            "size_bytes": 10,
        }

        self.assertEqual(validate_event("raw.image2d.meta", event), [])

    def test_rejects_extra_media_fields_and_invalid_ranges(self) -> None:
        event = {
            "device_id": "cam-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bucket": "media-raw-2d-images",
            "object_key": "cam-1/frame.jpg",
            "object_uri": "s3://media-raw-2d-images/cam-1/frame.jpg",
            "format": "jpg",
            "size_bytes": -1,
            "frame": 12,
        }

        errors = validate_event("raw.image2d.meta", event)

        self.assertIn("field not allowed by raw.image2d.meta: frame", errors)
        self.assertIn("size_bytes must be non-negative", errors)

    def test_builds_dlq_event(self) -> None:
        dlq = build_dlq_event(
            source="unit-test",
            intended_topic="raw.sensor",
            errors=["bad payload"],
            raw_event={"device_id": "dev-1", "source_topic": "mqtt/topic"},
        )

        self.assertEqual(DLQ_TOPIC, "dlq.events")
        self.assertIsInstance(dlq["timestamp"], str)
        self.assertEqual(dlq["source_topic"], "mqtt/topic")
        self.assertEqual(dlq["errors"], ["bad payload"])

    def test_event_time_prefers_event_timestamp_over_ingestion_timestamp(self) -> None:
        self.assertEqual(
            event_time(
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "ingested_at": "2026-01-01T00:00:01+00:00",
                }
            ),
            "2026-01-01T00:00:00+00:00",
        )

    def test_event_time_returns_empty_string_when_timestamp_is_missing(self) -> None:
        self.assertEqual(event_time({}), "")

    def test_unknown_topic_has_no_contract_errors(self) -> None:
        self.assertEqual(validate_event("unknown.topic", {"payload": "opaque"}), [])

    def test_rejects_invalid_contract_types_and_gps_ranges(self) -> None:
        event = {
            "device_id": 123,
            "timestamp": 456,
            "ingested_at": 789,
            "latitude": 91.0,
            "longitude": -181.0,
            "heading_deg": 361.0,
            "speed_m_s": "fast",
            "payload": "not-an-object",
            "tags": ["not", "an", "object"],
            "retain": "false",
        }

        errors = validate_event("raw.gps", event)

        self.assertIn("field must be a string: device_id", errors)
        self.assertIn("field must be a string: timestamp", errors)
        self.assertIn("field must be a string: ingested_at", errors)
        self.assertIn("field must be numeric: speed_m_s", errors)
        self.assertIn("field must be an object: payload", errors)
        self.assertIn("field must be an object: tags", errors)
        self.assertIn("field must be a boolean: retain", errors)
        self.assertIn("latitude out of range: -90..90", errors)
        self.assertIn("longitude out of range: -180..180", errors)
        self.assertIn("heading_deg out of range: 0..360", errors)


if __name__ == "__main__":
    unittest.main()
