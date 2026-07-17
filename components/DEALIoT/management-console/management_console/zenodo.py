from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast
from urllib import error, request
from urllib.parse import quote, urlparse

from management_console.catalog import DATA_MANAGEMENT_PLANS, DATASETS

ZENODO_PRODUCTION_API = "https://zenodo.org/api"
ZENODO_SANDBOX_API = "https://sandbox.zenodo.org/api"
ZENODO_EXPORT_EVIDENCE_TOPIC = "governance.repository.exports"
DEFAULT_TIMEOUT_SECONDS = 15.0
NON_OPEN_CLASSIFICATIONS = {"internal", "restricted", "personal", "sensitive", "mixed"}


class ZenodoExportError(RuntimeError):
    def __init__(self, status: int, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.error_code = error_code
        self.detail = detail


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def truthy_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def request_timeout_seconds() -> float:
    value = os.getenv("ZENODO_TIMEOUT_SECONDS", "")
    if not value:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, min(float(value), 120.0))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def zenodo_api_base_url() -> str:
    configured = os.getenv("ZENODO_API_BASE_URL")
    if configured:
        return configured.rstrip("/")
    if truthy_env("ZENODO_USE_SANDBOX", default=True):
        return ZENODO_SANDBOX_API
    return ZENODO_PRODUCTION_API


def is_zenodo_sandbox(api_base_url: str) -> bool:
    return urlparse(api_base_url).hostname == "sandbox.zenodo.org"


def validate_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ZenodoExportError(
            HTTPStatus.BAD_GATEWAY,
            "invalid_zenodo_response_url",
            "Zenodo response included a non-HTTPS or malformed URL.",
        )


def find_dataset(dataset_id: str) -> dict[str, Any]:
    for dataset in DATASETS:
        if dataset["dataset_id"] == dataset_id:
            return dataset
    raise ZenodoExportError(
        HTTPStatus.NOT_FOUND,
        "dataset_not_found",
        f"Unknown dataset_id: {dataset_id}",
    )


def linked_dmp(dataset: dict[str, Any]) -> dict[str, Any] | None:
    dmp_id = dataset.get("dmp_id")
    for dmp in DATA_MANAGEMENT_PLANS:
        if dmp["dmp_id"] == dmp_id:
            return dmp
    return None


def default_creators(payload: dict[str, Any]) -> list[dict[str, str]]:
    creators = payload.get("creators")
    if isinstance(creators, list) and creators:
        valid_creators = [
            creator for creator in creators if isinstance(creator, dict) and creator.get("name")
        ]
        if valid_creators:
            return valid_creators

    name = os.getenv("ZENODO_DEFAULT_CREATOR_NAME", "DEALIoT Consortium")
    affiliation = os.getenv("ZENODO_DEFAULT_CREATOR_AFFILIATION", "DEALIoT")
    return [{"name": name, "affiliation": affiliation}]


def access_right_for_dataset(dataset: dict[str, Any], payload: dict[str, Any]) -> str:
    requested = payload.get("access_right")
    if isinstance(requested, str) and requested in {"open", "restricted", "embargoed"}:
        return requested
    if dataset.get("access_mode") == "open" and dataset.get("classification") == "public":
        return "open"
    if dataset.get("access_mode") == "embargoed":
        return "embargoed"
    return "restricted"


def validate_release_gate(
    dataset: dict[str, Any],
    payload: dict[str, Any],
    access_right: str,
) -> None:
    if access_right == "open" and dataset.get("classification") in NON_OPEN_CLASSIFICATIONS:
        raise ZenodoExportError(
            HTTPStatus.CONFLICT,
            "open_release_blocked",
            "Open Zenodo release is blocked for non-public or personal datasets.",
        )
    if payload.get("publish") and not payload.get("legal_review_approved"):
        raise ZenodoExportError(
            HTTPStatus.CONFLICT,
            "legal_review_required",
            "Publishing to Zenodo requires legal_review_approved=true.",
        )


def zenodo_description(dataset: dict[str, Any], dmp: dict[str, Any] | None) -> str:
    dmp_text = dmp["dmp_id"] if dmp is not None else "missing"
    return (
        f"DEALIoT dataset export for {dataset['dataset_id']}. "
        f"Classification: {dataset['classification']}. "
        f"Access mode: {dataset['access_mode']}. "
        f"Linked Data Management Plan: {dmp_text}. "
        "This export must follow the dataset catalogue, DMP, GDPR legal-basis, "
        "Data Act and DGA release gates before publication."
    )


def build_zenodo_metadata(
    dataset: dict[str, Any],
    dmp: dict[str, Any] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    access_right = access_right_for_dataset(dataset, payload)
    validate_release_gate(dataset, payload, access_right)

    metadata: dict[str, Any] = {
        "title": payload.get("title") or dataset["title"],
        "upload_type": "dataset",
        "description": payload.get("description") or zenodo_description(dataset, dmp),
        "creators": default_creators(payload),
        "publication_date": payload.get("publication_date") or datetime.now(UTC).date().isoformat(),
        "access_right": access_right,
        "keywords": [
            "DEALIoT",
            "IoT",
            "research data",
            dataset["dataset_type"],
            dataset["classification"],
        ],
        "notes": (
            "Generated by the DEALIoT management console. "
            f"Evidence topic: {ZENODO_EXPORT_EVIDENCE_TOPIC}."
        ),
    }
    if access_right == "open":
        metadata["license"] = payload.get("license") or os.getenv(
            "ZENODO_DEFAULT_LICENSE",
            "cc-by-4.0",
        )
    else:
        metadata["access_conditions"] = payload.get("access_conditions") or (
            "Files are restricted until dataset catalogue, DMP, privacy, Data Act and DGA "
            "release checks are approved."
        )
    if isinstance(payload.get("communities"), list):
        metadata["communities"] = payload["communities"]
    return {"metadata": metadata}


def manifest_filename(dataset_id: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", dataset_id).strip("-")
    return f"{safe_name or 'dataset'}.zenodo-manifest.json"


def build_zenodo_manifest(dataset: dict[str, Any], dmp: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "manifest_type": "dealiot.zenodo.dataset_export",
        "generated_at": now_iso(),
        "repository": "Zenodo",
        "evidence_topic": ZENODO_EXPORT_EVIDENCE_TOPIC,
        "dataset": dataset,
        "data_management_plan": dmp,
        "release_gates": [
            "dataset catalogue record approved",
            "Data Management Plan active or approved",
            "GDPR legal basis and DPIA reviewed where personal data is present",
            "Data Act user entitlement and third-party safeguards reviewed",
            "DGA research protocol, ethics status and disclosure review completed",
            "raw GPS, media or personal datasets are not released openly by default",
        ],
    }


def _json_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_https_url(url)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, method=method, headers=headers)  # noqa: S310
    return _parse_json_response(req)


def _bytes_request(
    method: str,
    url: str,
    token: str,
    body: bytes,
    content_type: str,
) -> dict[str, Any]:
    validate_https_url(url)
    req = request.Request(  # noqa: S310
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        },
    )
    return _parse_json_response(req)


def _parse_json_response(req: request.Request) -> dict[str, Any]:
    try:
        validate_https_url(req.full_url)
        # URL is validated immediately above; urllib is kept to avoid an extra runtime dependency.
        with request.urlopen(req, timeout=request_timeout_seconds()) as response:  # noqa: S310  # nosec B310
            response_body = response.read().decode("utf-8")
            return json.loads(response_body) if response_body else {}
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise ZenodoExportError(exc.code, "zenodo_http_error", body_text) from exc
    except OSError as exc:
        raise ZenodoExportError(
            HTTPStatus.BAD_GATEWAY,
            "zenodo_unreachable",
            str(exc),
        ) from exc


def staged_files_from_payload(payload: dict[str, Any]) -> list[Path]:
    staged_files = payload.get("staged_files", [])
    if staged_files in (None, ""):
        return []
    if not isinstance(staged_files, list):
        raise ZenodoExportError(
            HTTPStatus.BAD_REQUEST,
            "invalid_staged_files",
            "staged_files must be a list of file names relative to ZENODO_EXPORT_STAGING_DIR.",
        )
    if not staged_files:
        return []

    staging_dir = os.getenv("ZENODO_EXPORT_STAGING_DIR")
    if not staging_dir:
        raise ZenodoExportError(
            HTTPStatus.CONFLICT,
            "missing_staging_dir",
            "Set ZENODO_EXPORT_STAGING_DIR before uploading dataset files.",
        )

    base_dir = Path(staging_dir).resolve()
    resolved_files: list[Path] = []
    for relative_name in staged_files:
        if not isinstance(relative_name, str) or not relative_name.strip():
            raise ZenodoExportError(
                HTTPStatus.BAD_REQUEST,
                "invalid_staged_file",
                "Each staged file must be a non-empty relative path.",
            )
        candidate = (base_dir / relative_name).resolve()
        if not candidate.is_relative_to(base_dir) or not candidate.is_file():
            raise ZenodoExportError(
                HTTPStatus.BAD_REQUEST,
                "invalid_staged_file",
                f"Staged file is outside the export directory or missing: {relative_name}",
            )
        resolved_files.append(candidate)
    return resolved_files


def upload_file_to_bucket(
    bucket_url: str,
    token: str,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    target_url = f"{bucket_url.rstrip('/')}/{quote(filename)}"
    return _bytes_request("PUT", target_url, token, content, "application/octet-stream")


def export_dataset_to_zenodo(payload: dict[str, Any]) -> dict[str, Any]:
    dataset_id = payload.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ZenodoExportError(
            HTTPStatus.BAD_REQUEST,
            "missing_dataset_id",
            "dataset_id is required.",
        )

    token = os.getenv("ZENODO_ACCESS_TOKEN")
    if not token:
        raise ZenodoExportError(
            HTTPStatus.CONFLICT,
            "missing_zenodo_token",
            "Set ZENODO_ACCESS_TOKEN before exporting to Zenodo.",
        )

    dataset = find_dataset(dataset_id)
    dmp = linked_dmp(dataset)
    metadata = build_zenodo_metadata(dataset, dmp, payload)
    staged_files = staged_files_from_payload(payload)
    base_url = zenodo_api_base_url()
    parsed_base = urlparse(base_url)
    if parsed_base.scheme != "https":
        raise ZenodoExportError(
            HTTPStatus.BAD_REQUEST,
            "invalid_zenodo_api_base_url",
            "ZENODO_API_BASE_URL must use HTTPS.",
        )

    deposition = _json_request("POST", f"{base_url}/deposit/depositions", token, {})
    deposition_id = deposition.get("id")
    deposition_links = deposition.get("links")
    links = cast("dict[str, Any]", deposition_links) if isinstance(deposition_links, dict) else {}
    self_url = links.get("self") or f"{base_url}/deposit/depositions/{deposition_id}"
    bucket_url = links.get("bucket")
    if not bucket_url:
        raise ZenodoExportError(
            HTTPStatus.BAD_GATEWAY,
            "missing_zenodo_bucket",
            "Zenodo response did not include a bucket upload URL.",
        )

    updated = _json_request("PUT", self_url, token, metadata)
    manifest = json.dumps(
        build_zenodo_manifest(dataset, dmp),
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    uploaded_files = [
        upload_file_to_bucket(
            bucket_url,
            token,
            manifest_filename(dataset_id),
            manifest,
        )
    ]
    uploaded_files.extend(
        (
            upload_file_to_bucket(
                bucket_url,
                token,
                staged_file.name,
                staged_file.read_bytes(),
            )
        )
        for staged_file in staged_files
    )

    published: dict[str, Any] | None = None
    if payload.get("publish"):
        publish_url = links.get("publish") or f"{self_url}/actions/publish"
        published = _json_request("POST", publish_url, token)

    latest = published or updated
    latest_links_value = latest.get("links")
    latest_links = (
        cast("dict[str, Any]", latest_links_value)
        if isinstance(latest_links_value, dict)
        else links
    )
    return {
        "status": "published" if published is not None else "draft_created",
        "repository": "Zenodo",
        "sandbox": is_zenodo_sandbox(base_url),
        "dataset_id": dataset_id,
        "dmp_id": dataset.get("dmp_id"),
        "deposition_id": latest.get("id", deposition_id),
        "record_id": latest.get("record_id"),
        "doi": latest.get("doi"),
        "record_url": latest.get("record_url") or latest_links.get("html"),
        "links": latest_links,
        "uploaded_files": uploaded_files,
        "publish_requested": bool(payload.get("publish")),
        "legal_review_approved": bool(payload.get("legal_review_approved")),
        "evidence_topic": ZENODO_EXPORT_EVIDENCE_TOPIC,
    }


def zenodo_export_payload() -> dict[str, Any]:
    base_url = zenodo_api_base_url()
    return {
        "repository": "Zenodo",
        "api_base_url": base_url,
        "sandbox": is_zenodo_sandbox(base_url),
        "token_configured": bool(os.getenv("ZENODO_ACCESS_TOKEN")),
        "staging_dir_configured": bool(os.getenv("ZENODO_EXPORT_STAGING_DIR")),
        "evidence_topic": ZENODO_EXPORT_EVIDENCE_TOPIC,
        "default_mode": "draft",
        "publish_gate": "legal_review_approved=true required before publish",
        "file_gate": "only files under ZENODO_EXPORT_STAGING_DIR can be uploaded",
        "open_release_gate": "open release blocked for internal, restricted or personal datasets",
    }
