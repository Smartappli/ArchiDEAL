from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from management_console.catalog import DATA_MANAGEMENT_PLANS, DATASETS

OPENAIRE_PROVIDE_URL = "https://provide.openaire.eu/"
OPENAIRE_GUIDELINES_URL = "https://guidelines.openaire.eu/en/latest/data/index.html"
OPENAIRE_EXPORT_EVIDENCE_TOPIC = "governance.repository.exports"
DATACITE_NS = "http://datacite.org/schema/kernel-4"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NON_OPEN_CLASSIFICATIONS = {"internal", "restricted", "personal", "sensitive", "mixed"}


class OpenAIREExportError(RuntimeError):
    def __init__(self, status: int, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.error_code = error_code
        self.detail = detail


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def find_dataset(dataset_id: str) -> dict[str, Any]:
    for dataset in DATASETS:
        if dataset["dataset_id"] == dataset_id:
            return dataset
    raise OpenAIREExportError(
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


def safe_filename(dataset_id: str, suffix: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", dataset_id).strip("-")
    return f"{safe_name or 'dataset'}{suffix}"


def default_creators(payload: dict[str, Any]) -> list[dict[str, str]]:
    creators = payload.get("creators")
    if isinstance(creators, list) and creators:
        valid_creators = [
            creator for creator in creators if isinstance(creator, dict) and creator.get("name")
        ]
        if valid_creators:
            return valid_creators

    return [
        {
            "name": os.getenv("OPENAIRE_DEFAULT_CREATOR_NAME", "DEALIoT Consortium"),
            "affiliation": os.getenv("OPENAIRE_DEFAULT_CREATOR_AFFILIATION", "DEALIoT"),
        }
    ]


def landing_page_for_dataset(dataset_id: str, payload: dict[str, Any]) -> str | None:
    landing_page = payload.get("landing_page_url")
    if isinstance(landing_page, str) and landing_page:
        return landing_page

    base_url = os.getenv("OPENAIRE_DATASET_LANDING_BASE_URL", "").rstrip("/")
    if base_url:
        return f"{base_url}/{dataset_id}"
    return None


def identifier_for_dataset(dataset_id: str, payload: dict[str, Any]) -> tuple[str, str]:
    doi = payload.get("doi")
    if isinstance(doi, str) and doi.strip():
        return doi.strip().removeprefix("https://doi.org/"), "DOI"

    landing_page = landing_page_for_dataset(dataset_id, payload)
    if landing_page:
        parsed = urlparse(landing_page)
        if parsed.scheme != "https":
            raise OpenAIREExportError(
                HTTPStatus.BAD_REQUEST,
                "invalid_landing_page_url",
                "OpenAIRE landing_page_url must use HTTPS.",
            )
        return landing_page, "URL"

    return dataset_id, "Other"


def access_right_for_dataset(dataset: dict[str, Any], payload: dict[str, Any]) -> str:
    requested = payload.get("access_right")
    if isinstance(requested, str) and requested in {"open", "restricted", "closed"}:
        return requested
    if dataset.get("classification") == "public" and dataset.get("access_mode") == "open":
        return "open"
    return "restricted"


def validate_release_gate(dataset: dict[str, Any], access_right: str) -> None:
    if access_right == "open" and dataset.get("classification") in NON_OPEN_CLASSIFICATIONS:
        raise OpenAIREExportError(
            HTTPStatus.CONFLICT,
            "open_metadata_release_blocked",
            "OpenAIRE open-access metadata is blocked for non-public datasets.",
        )


def publication_year(payload: dict[str, Any]) -> str:
    value = payload.get("publication_year")
    if isinstance(value, str) and re.fullmatch(r"\d{4}", value):
        return value
    return str(datetime.now(UTC).year)


def rights_metadata(access_right: str) -> tuple[str, str]:
    if access_right == "open":
        return "Open Access", "info:eu-repo/semantics/openAccess"
    if access_right == "closed":
        return "Closed Access", "info:eu-repo/semantics/closedAccess"
    return "Restricted Access", "info:eu-repo/semantics/restrictedAccess"


def openaire_description(dataset: dict[str, Any], dmp: dict[str, Any] | None) -> str:
    dmp_text = dmp["dmp_id"] if dmp is not None else "missing"
    return (
        f"DEALIoT metadata export for {dataset['dataset_id']}. "
        f"Classification: {dataset['classification']}. "
        f"Access mode: {dataset['access_mode']}. "
        f"Linked Data Management Plan: {dmp_text}. "
        "This record is intended for OpenAIRE discovery and must not override "
        "dataset catalogue, DMP, GDPR, Data Act or DGA release gates."
    )


def build_openaire_metadata(
    dataset: dict[str, Any],
    dmp: dict[str, Any] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    access_right = access_right_for_dataset(dataset, payload)
    validate_release_gate(dataset, access_right)
    identifier, identifier_type = identifier_for_dataset(dataset["dataset_id"], payload)
    rights, rights_uri = rights_metadata(access_right)
    return {
        "schema": "OpenAIRE Guidelines for Data Archives / DataCite",
        "identifier": identifier,
        "identifier_type": identifier_type,
        "creators": default_creators(payload),
        "title": payload.get("title") or dataset["title"],
        "publisher": payload.get("publisher")
        or os.getenv("OPENAIRE_DEFAULT_PUBLISHER", "DEALIoT Consortium"),
        "publication_year": publication_year(payload),
        "subjects": [
            "DEALIoT",
            "IoT",
            "research data",
            dataset["dataset_type"],
            dataset["classification"],
        ],
        "resource_type": "Dataset",
        "resource_type_general": "Dataset",
        "language": payload.get("language") or "en",
        "formats": payload.get("formats") or ["application/json"],
        "rights": rights,
        "rights_uri": rights_uri,
        "description": payload.get("description") or openaire_description(dataset, dmp),
        "related_identifiers": [
            {
                "identifier": dataset.get("dmp_id", ""),
                "identifier_type": "Local",
                "relation_type": "IsDocumentedBy",
            }
        ],
        "access_right": access_right,
        "landing_page_url": landing_page_for_dataset(dataset["dataset_id"], payload),
    }


def xml_escape_text(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_escape_attr(value: Any) -> str:
    return xml_escape_text(value).replace('"', "&quot;")


def xml_attrs(attributes: dict[str, Any] | None = None) -> str:
    if not attributes:
        return ""
    return "".join(
        f' {name}="{xml_escape_attr(value)}"'
        for name, value in attributes.items()
        if value is not None
    )


def xml_text_element(
    name: str,
    value: Any,
    attributes: dict[str, Any] | None = None,
    *,
    indent: int = 1,
) -> str:
    spaces = "  " * indent
    return f"{spaces}<{name}{xml_attrs(attributes)}>{xml_escape_text(value)}</{name}>"


def datacite_xml_bytes(metadata: dict[str, Any]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        (
            f'<resource xmlns="{DATACITE_NS}" xmlns:xsi="{XSI_NS}" '
            f'xsi:schemaLocation="{DATACITE_NS} '
            'https://schema.datacite.org/meta/kernel-4/metadata.xsd">'
        ),
        xml_text_element(
            "identifier",
            metadata["identifier"],
            {"identifierType": metadata["identifier_type"]},
        ),
        "  <creators>",
    ]
    for creator in metadata["creators"]:
        lines.append("    <creator>")
        lines.append(xml_text_element("creatorName", creator["name"], indent=3))
        affiliation = creator.get("affiliation")
        if affiliation:
            lines.append(xml_text_element("affiliation", affiliation, indent=3))
        lines.append("    </creator>")

    lines.extend(
        [
            "  </creators>",
            "  <titles>",
            xml_text_element("title", metadata["title"], indent=2),
            "  </titles>",
            xml_text_element("publisher", metadata["publisher"]),
            xml_text_element("publicationYear", metadata["publication_year"]),
            "  <subjects>",
        ]
    )
    lines.extend(xml_text_element("subject", subject, indent=2) for subject in metadata["subjects"])

    lines.extend(
        [
            "  </subjects>",
            xml_text_element("language", metadata["language"]),
            xml_text_element(
                "resourceType",
                metadata["resource_type"],
                {"resourceTypeGeneral": metadata["resource_type_general"]},
            ),
            "  <dates>",
            xml_text_element(
                "date",
                datetime.now(UTC).date().isoformat(),
                {"dateType": "Issued"},
                indent=2,
            ),
            "  </dates>",
            "  <formats>",
        ]
    )
    lines.extend(
        xml_text_element("format", item_format, indent=2) for item_format in metadata["formats"]
    )

    lines.extend(
        [
            "  </formats>",
            "  <rightsList>",
            xml_text_element(
                "rights",
                metadata["rights"],
                {"rightsURI": metadata["rights_uri"]},
                indent=2,
            ),
            "  </rightsList>",
            "  <descriptions>",
            xml_text_element(
                "description",
                metadata["description"],
                {"descriptionType": "Abstract"},
                indent=2,
            ),
            "  </descriptions>",
        ]
    )

    related = [
        item
        for item in metadata["related_identifiers"]
        if item["identifier"] and item["identifier_type"] and item["relation_type"]
    ]
    if related:
        lines.append("  <relatedIdentifiers>")
        lines.extend(
            (
                xml_text_element(
                    "relatedIdentifier",
                    item["identifier"],
                    {
                        "relatedIdentifierType": item["identifier_type"],
                        "relationType": item["relation_type"],
                    },
                    indent=2,
                )
            )
            for item in related
        )
        lines.append("  </relatedIdentifiers>")

    lines.append("</resource>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_openaire_manifest(
    dataset: dict[str, Any],
    dmp: dict[str, Any] | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "manifest_type": "dealiot.openaire.metadata_export",
        "generated_at": now_iso(),
        "catalogue": "OpenAIRE",
        "export_mode": "metadata_package_for_provide_or_oai_pmh",
        "direct_upload_supported": False,
        "guidelines": OPENAIRE_GUIDELINES_URL,
        "provide_registration_url": OPENAIRE_PROVIDE_URL,
        "evidence_topic": OPENAIRE_EXPORT_EVIDENCE_TOPIC,
        "dataset": dataset,
        "data_management_plan": dmp,
        "metadata": metadata,
        "release_gates": [
            "dataset catalogue record approved",
            "Data Management Plan active or approved",
            "metadata access right reflects the dataset classification",
            "GDPR legal basis and DPIA reviewed where personal data is present",
            "Data Act, DGA and legal dossier gates reviewed before public discovery",
        ],
    }


def openaire_export_dir() -> Path:
    return Path(os.getenv("OPENAIRE_EXPORT_STAGING_DIR", "./openaire-exports")).resolve()


def export_dataset_to_openaire(payload: dict[str, Any]) -> dict[str, Any]:
    dataset_id = payload.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise OpenAIREExportError(
            HTTPStatus.BAD_REQUEST,
            "missing_dataset_id",
            "dataset_id is required.",
        )

    dataset = find_dataset(dataset_id)
    dmp = linked_dmp(dataset)
    metadata = build_openaire_metadata(dataset, dmp, payload)
    export_dir = openaire_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    xml_path = export_dir / safe_filename(dataset_id, ".openaire-datacite.xml")
    manifest_path = export_dir / safe_filename(dataset_id, ".openaire-manifest.json")
    xml_path.write_bytes(datacite_xml_bytes(metadata))
    manifest_path.write_text(
        json.dumps(build_openaire_manifest(dataset, dmp, metadata), sort_keys=True, indent=2),
        encoding="utf-8",
    )

    return {
        "status": "metadata_package_created",
        "catalogue": "OpenAIRE",
        "dataset_id": dataset_id,
        "dmp_id": dataset.get("dmp_id"),
        "direct_upload_supported": False,
        "export_mode": "metadata_package_for_provide_or_oai_pmh",
        "metadata_standard": "OpenAIRE Guidelines for Data Archives / DataCite",
        "identifier": metadata["identifier"],
        "identifier_type": metadata["identifier_type"],
        "access_right": metadata["access_right"],
        "files": [str(xml_path), str(manifest_path)],
        "provide_registration_url": OPENAIRE_PROVIDE_URL,
        "evidence_topic": OPENAIRE_EXPORT_EVIDENCE_TOPIC,
    }


def openaire_export_payload() -> dict[str, Any]:
    return {
        "catalogue": "OpenAIRE",
        "direct_upload_supported": False,
        "export_mode": "metadata_package_for_provide_or_oai_pmh",
        "metadata_standard": "OpenAIRE Guidelines for Data Archives / DataCite",
        "guidelines": OPENAIRE_GUIDELINES_URL,
        "provide_registration_url": OPENAIRE_PROVIDE_URL,
        "staging_dir": str(openaire_export_dir()),
        "evidence_topic": OPENAIRE_EXPORT_EVIDENCE_TOPIC,
        "default_policy": (
            "OpenAIRE discovery is metadata-first; register an OpenAIRE-compatible "
            "repository or OAI-PMH data source in OpenAIRE PROVIDE."
        ),
        "release_gate": "dataset catalogue, DMP and legal dossier approval required",
    }
