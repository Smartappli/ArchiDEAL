from __future__ import annotations

import json
import sys
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console import openaire  # noqa: E402


class OpenAIREExportUnitTests(unittest.TestCase):
    def test_builds_restricted_datacite_metadata_and_xml(self) -> None:
        dataset = openaire.find_dataset("dataset.telemetry.sensor-minimised")
        dmp = openaire.linked_dmp(dataset)
        metadata = openaire.build_openaire_metadata(
            dataset,
            dmp,
            {
                "creators": [{"name": "Researcher", "affiliation": "Lab"}],
                "doi": "https://doi.org/10.5281/zenodo.123",
            },
        )

        self.assertEqual(metadata["identifier"], "10.5281/zenodo.123")
        self.assertEqual(metadata["identifier_type"], "DOI")
        self.assertEqual(metadata["access_right"], "restricted")
        self.assertEqual(metadata["creators"][0]["name"], "Researcher")

        xml_bytes = openaire.datacite_xml_bytes(metadata)
        self.assertIn(b"<resource", xml_bytes)
        self.assertIn(b'identifierType="DOI"', xml_bytes)
        self.assertIn(b"Restricted Access", xml_bytes)
        self.assertIn(b"IsDocumentedBy", xml_bytes)

    def test_blocks_open_access_for_non_public_dataset_and_validates_landing_page(self) -> None:
        dataset = openaire.find_dataset("dataset.features.latest-state")
        dmp = openaire.linked_dmp(dataset)

        with self.assertRaises(openaire.OpenAIREExportError) as blocked:
            openaire.build_openaire_metadata(dataset, dmp, {"access_right": "open"})
        self.assertEqual(blocked.exception.error_code, "open_metadata_release_blocked")

        with self.assertRaises(openaire.OpenAIREExportError) as invalid:
            openaire.build_openaire_metadata(
                dataset,
                dmp,
                {"landing_page_url": "http://example.org/dataset"},
            )
        self.assertEqual(invalid.exception.status, HTTPStatus.BAD_REQUEST)

    def test_export_writes_manifest_and_datacite_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                "os.environ",
                {
                    "OPENAIRE_EXPORT_STAGING_DIR": tmpdir,
                    "OPENAIRE_DATASET_LANDING_BASE_URL": "https://example.org/datasets",
                },
                clear=True,
            ):
                result = openaire.export_dataset_to_openaire(
                    {"dataset_id": "dataset.features.latest-state"}
                )

            self.assertEqual(result["status"], "metadata_package_created")
            self.assertFalse(result["direct_upload_supported"])
            self.assertEqual(result["identifier_type"], "URL")
            self.assertEqual(len(result["files"]), 2)
            xml_path = Path(result["files"][0])
            manifest_path = Path(result["files"][1])
            self.assertTrue(xml_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertIn("openaire-datacite", xml_path.name)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["catalogue"], "OpenAIRE")
            self.assertFalse(manifest["direct_upload_supported"])
            self.assertIn("OpenAIRE", manifest["metadata"]["schema"])

    def test_export_requires_dataset_id_and_known_dataset(self) -> None:
        with self.assertRaises(openaire.OpenAIREExportError) as missing_id:
            openaire.export_dataset_to_openaire({})
        self.assertEqual(missing_id.exception.error_code, "missing_dataset_id")

        with self.assertRaises(openaire.OpenAIREExportError) as missing_dataset:
            openaire.export_dataset_to_openaire({"dataset_id": "missing"})
        self.assertEqual(missing_dataset.exception.error_code, "dataset_not_found")

    def test_payload_exposes_provide_registration_context(self) -> None:
        with patch.dict("os.environ", {"OPENAIRE_EXPORT_STAGING_DIR": "exports"}, clear=True):
            payload = openaire.openaire_export_payload()

        self.assertEqual(payload["catalogue"], "OpenAIRE")
        self.assertFalse(payload["direct_upload_supported"])
        self.assertIn("PROVIDE", payload["default_policy"])
        self.assertIn("DataCite", payload["metadata_standard"])


if __name__ == "__main__":
    unittest.main()
