from __future__ import annotations

import io
import sys
import tempfile
import unittest
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Self
from unittest.mock import patch
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "management-console"))

from management_console import zenodo  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes = b"{}") -> None:
        self.body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ZenodoExportUnitTests(unittest.TestCase):
    def test_zenodo_configuration_defaults_to_sandbox_and_clamps_timeout(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(zenodo.zenodo_api_base_url(), zenodo.ZENODO_SANDBOX_API)
            self.assertEqual(zenodo.request_timeout_seconds(), zenodo.DEFAULT_TIMEOUT_SECONDS)
            self.assertTrue(zenodo.is_zenodo_sandbox(zenodo.zenodo_api_base_url()))

        with patch.dict("os.environ", {"ZENODO_USE_SANDBOX": "false"}, clear=True):
            self.assertEqual(zenodo.zenodo_api_base_url(), zenodo.ZENODO_PRODUCTION_API)
            self.assertFalse(zenodo.is_zenodo_sandbox(zenodo.zenodo_api_base_url()))

        with patch.dict(
            "os.environ",
            {"ZENODO_API_BASE_URL": "https://repo.example/api/", "ZENODO_TIMEOUT_SECONDS": "0"},
            clear=True,
        ):
            self.assertEqual(zenodo.zenodo_api_base_url(), "https://repo.example/api")
            self.assertEqual(zenodo.request_timeout_seconds(), 1.0)

        with patch.dict("os.environ", {"ZENODO_TIMEOUT_SECONDS": "invalid"}, clear=True):
            self.assertEqual(zenodo.request_timeout_seconds(), zenodo.DEFAULT_TIMEOUT_SECONDS)

        self.assertFalse(zenodo.is_zenodo_sandbox("https://sandbox.zenodo.org.evil.test/api"))
        self.assertFalse(zenodo.is_zenodo_sandbox("https://repo.test/sandbox.zenodo.org/api"))

    def test_metadata_maps_restricted_and_blocks_unsafe_open_release(self) -> None:
        dataset = zenodo.find_dataset("dataset.telemetry.sensor-minimised")
        dmp = zenodo.linked_dmp(dataset)
        metadata = zenodo.build_zenodo_metadata(
            dataset,
            dmp,
            {
                "creators": [{"name": "Researcher", "affiliation": "Lab"}],
                "communities": [{"identifier": "dealiot"}],
            },
        )

        self.assertEqual(metadata["metadata"]["upload_type"], "dataset")
        self.assertEqual(metadata["metadata"]["access_right"], "restricted")
        self.assertIn("access_conditions", metadata["metadata"])
        self.assertEqual(metadata["metadata"]["creators"][0]["name"], "Researcher")
        self.assertEqual(metadata["metadata"]["communities"][0]["identifier"], "dealiot")

        with self.assertRaises(zenodo.ZenodoExportError) as blocked:
            zenodo.build_zenodo_metadata(dataset, dmp, {"access_right": "open"})
        self.assertEqual(blocked.exception.error_code, "open_release_blocked")

        open_dataset = dict(dataset, classification="public", access_mode="open")
        metadata = zenodo.build_zenodo_metadata(open_dataset, dmp, {"access_right": "open"})
        self.assertEqual(metadata["metadata"]["license"], "cc-by-4.0")

        embargoed = dict(dataset, access_mode="embargoed")
        self.assertEqual(zenodo.access_right_for_dataset(embargoed, {}), "embargoed")
        self.assertIsNone(zenodo.linked_dmp({"dmp_id": "missing"}))

    def test_publish_requires_legal_review_and_manifest_contains_release_gates(self) -> None:
        dataset = zenodo.find_dataset("dataset.features.latest-state")
        dmp = zenodo.linked_dmp(dataset)

        with self.assertRaises(zenodo.ZenodoExportError) as blocked:
            zenodo.build_zenodo_metadata(dataset, dmp, {"publish": True})
        self.assertEqual(blocked.exception.error_code, "legal_review_required")

        manifest = zenodo.build_zenodo_manifest(dataset, dmp)
        self.assertEqual(manifest["repository"], "Zenodo")
        self.assertEqual(manifest["dataset"]["dataset_id"], "dataset.features.latest-state")
        self.assertIn("raw GPS", " ".join(manifest["release_gates"]))
        self.assertEqual(
            zenodo.manifest_filename("dataset/features latest"),
            "dataset-features-latest.zenodo-manifest.json",
        )

    def test_staged_files_are_restricted_to_configured_directory(self) -> None:
        self.assertEqual(zenodo.staged_files_from_payload({"staged_files": None}), [])
        self.assertEqual(zenodo.staged_files_from_payload({"staged_files": []}), [])

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            allowed = base / "dataset.json"
            allowed.write_text("{}", encoding="utf-8")

            with patch.dict("os.environ", {"ZENODO_EXPORT_STAGING_DIR": tmpdir}, clear=True):
                files = zenodo.staged_files_from_payload({"staged_files": ["dataset.json"]})
                self.assertEqual(files, [allowed.resolve()])

                with self.assertRaises(zenodo.ZenodoExportError) as blocked:
                    zenodo.staged_files_from_payload({"staged_files": ["../outside.json"]})
                self.assertEqual(blocked.exception.error_code, "invalid_staged_file")

                with self.assertRaises(zenodo.ZenodoExportError) as invalid_item:
                    zenodo.staged_files_from_payload({"staged_files": [None]})
                self.assertEqual(invalid_item.exception.error_code, "invalid_staged_file")

            with self.assertRaises(zenodo.ZenodoExportError):
                zenodo.staged_files_from_payload({"staged_files": "dataset.json"})

            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(zenodo.ZenodoExportError) as missing:
                    zenodo.staged_files_from_payload({"staged_files": ["dataset.json"]})
                self.assertEqual(missing.exception.error_code, "missing_staging_dir")

    def test_export_requires_token_dataset_and_https_base_url(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertRaises(zenodo.ZenodoExportError) as missing_token,
        ):
            zenodo.export_dataset_to_zenodo({"dataset_id": "dataset.features.latest-state"})
        self.assertEqual(missing_token.exception.error_code, "missing_zenodo_token")

        with (
            patch.dict("os.environ", {"ZENODO_ACCESS_TOKEN": "token"}, clear=True),
            self.assertRaises(zenodo.ZenodoExportError) as missing_id,
        ):
            zenodo.export_dataset_to_zenodo({})
        self.assertEqual(missing_id.exception.error_code, "missing_dataset_id")

        with (
            patch.dict("os.environ", {"ZENODO_ACCESS_TOKEN": "token"}, clear=True),
            self.assertRaises(zenodo.ZenodoExportError) as missing_dataset,
        ):
            zenodo.export_dataset_to_zenodo({"dataset_id": "missing"})
        self.assertEqual(missing_dataset.exception.error_code, "dataset_not_found")

        with (
            patch.dict(
                "os.environ",
                {
                    "ZENODO_ACCESS_TOKEN": "token",
                    "ZENODO_API_BASE_URL": "http://zenodo.example/api",
                },
                clear=True,
            ),
            self.assertRaises(zenodo.ZenodoExportError) as invalid_url,
        ):
            zenodo.export_dataset_to_zenodo({"dataset_id": "dataset.features.latest-state"})
        self.assertEqual(invalid_url.exception.error_code, "invalid_zenodo_api_base_url")

    def test_export_creates_draft_uploads_manifest_files_and_can_publish(self) -> None:
        created = {
            "id": 10,
            "links": {
                "self": "https://sandbox.zenodo.org/api/deposit/depositions/10",
                "bucket": "https://sandbox.zenodo.org/api/files/bucket",
                "publish": "https://sandbox.zenodo.org/api/deposit/depositions/10/actions/publish",
            },
        }
        updated = {
            "id": 10,
            "record_id": 20,
            "links": {"html": "https://sandbox.zenodo.org/records/20"},
        }
        published = {
            "id": 10,
            "record_id": 20,
            "doi": "10.5281/zenodo.20",
            "record_url": "https://sandbox.zenodo.org/records/20",
            "links": {"html": "https://sandbox.zenodo.org/records/20"},
        }
        calls: list[tuple[str, str, dict[str, object] | None]] = []
        uploads: list[tuple[str, str, bytes, str]] = []

        def fake_json_request(
            method: str,
            url: str,
            _token: str,
            payload: dict[str, object] | None = None,
        ) -> dict[str, object]:
            calls.append((method, url, payload))
            if method == "POST" and url.endswith("/deposit/depositions"):
                return created
            if method == "PUT":
                return updated
            if method == "POST" and url.endswith("/actions/publish"):
                return published
            message = f"Unexpected request: {method} {url}"
            raise AssertionError(message)

        def fake_bytes_request(
            method: str,
            url: str,
            _token: str,
            body: bytes,
            content_type: str,
        ) -> dict[str, object]:
            uploads.append((method, url, body, content_type))
            return {"filename": Path(url).name}

        with tempfile.TemporaryDirectory() as tmpdir:
            staged = Path(tmpdir) / "features.json"
            staged.write_text('{"rows": 1}', encoding="utf-8")
            with (
                patch.dict(
                    "os.environ",
                    {
                        "ZENODO_ACCESS_TOKEN": "token",
                        "ZENODO_EXPORT_STAGING_DIR": tmpdir,
                    },
                    clear=True,
                ),
                patch("management_console.zenodo._json_request", side_effect=fake_json_request),
                patch("management_console.zenodo._bytes_request", side_effect=fake_bytes_request),
            ):
                result = zenodo.export_dataset_to_zenodo(
                    {
                        "dataset_id": "dataset.features.latest-state",
                        "staged_files": ["features.json"],
                        "publish": True,
                        "legal_review_approved": True,
                    }
                )

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["doi"], "10.5281/zenodo.20")
        self.assertEqual(len(uploads), 2)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[-1][0], "POST")
        self.assertIn(b"dealiot.zenodo.dataset_export", uploads[0][2])

    def test_export_rejects_zenodo_response_without_bucket(self) -> None:
        with (
            patch.dict("os.environ", {"ZENODO_ACCESS_TOKEN": "token"}, clear=True),
            patch(
                "management_console.zenodo._json_request",
                return_value={"id": 10, "links": {}},
            ),
            self.assertRaises(zenodo.ZenodoExportError) as missing_bucket,
        ):
            zenodo.export_dataset_to_zenodo({"dataset_id": "dataset.features.latest-state"})

        self.assertEqual(missing_bucket.exception.error_code, "missing_zenodo_bucket")

    def test_export_rejects_malformed_zenodo_link_urls(self) -> None:
        with (
            patch.dict("os.environ", {"ZENODO_ACCESS_TOKEN": "token"}, clear=True),
            patch(
                "management_console.zenodo._json_request",
                return_value={"id": 10, "links": {"bucket": "file:///tmp/zenodo-bucket"}},
            ),
            self.assertRaises(zenodo.ZenodoExportError) as invalid_url,
        ):
            zenodo.export_dataset_to_zenodo({"dataset_id": "dataset.features.latest-state"})

        self.assertEqual(invalid_url.exception.error_code, "invalid_zenodo_response_url")

    def test_http_helpers_parse_success_http_error_and_network_error(self) -> None:
        with patch(
            "management_console.zenodo.request.urlopen",
            return_value=FakeResponse(b'{"ok":true}'),
        ):
            result = zenodo._json_request(  # noqa: SLF001
                "GET",
                "https://zenodo.example/api",
                "token",
            )
        self.assertEqual(result, {"ok": True})

        with patch(
            "management_console.zenodo.request.urlopen",
            return_value=FakeResponse(b'{"file":"ok"}'),
        ):
            result = zenodo._bytes_request(  # noqa: SLF001
                "PUT",
                "https://zenodo.example/api/files/data.json",
                "token",
                b"{}",
                "application/json",
            )
        self.assertEqual(result, {"file": "ok"})

        uploaded: list[tuple[str, str, bytes, str]] = []

        def fake_bytes_request(
            method: str,
            url: str,
            _token: str,
            body: bytes,
            content_type: str,
        ) -> dict[str, str]:
            uploaded.append((method, url, body, content_type))
            return {"url": url}

        with patch("management_console.zenodo._bytes_request", side_effect=fake_bytes_request):
            result = zenodo.upload_file_to_bucket(
                "https://zenodo.example/api/files",
                "token",
                "data file.json",
                b"{}",
            )
        self.assertIn("data%20file.json", result["url"])

        rejected = error.HTTPError(
            "https://zenodo.example",
            400,
            "bad",
            hdrs=Message(),
            fp=io.BytesIO(b"bad request"),
        )
        req = request.Request("https://zenodo.example", method="GET")
        with (
            patch("management_console.zenodo.request.urlopen", side_effect=rejected),
            self.assertRaises(zenodo.ZenodoExportError) as http_error,
        ):
            zenodo._parse_json_response(req)  # noqa: SLF001
        self.assertEqual(http_error.exception.status, 400)
        self.assertEqual(http_error.exception.error_code, "zenodo_http_error")

        with (
            patch("management_console.zenodo.request.urlopen", side_effect=OSError("offline")),
            self.assertRaises(zenodo.ZenodoExportError) as network_error,
        ):
            zenodo._parse_json_response(req)  # noqa: SLF001
        self.assertEqual(network_error.exception.status, HTTPStatus.BAD_GATEWAY)

    def test_zenodo_export_payload_exposes_safe_defaults(self) -> None:
        with patch.dict("os.environ", {"ZENODO_ACCESS_TOKEN": "token"}, clear=True):
            payload = zenodo.zenodo_export_payload()
        self.assertTrue(payload["token_configured"])
        self.assertEqual(payload["default_mode"], "draft")
        self.assertIn("legal_review_approved", payload["publish_gate"])


if __name__ == "__main__":
    unittest.main()
