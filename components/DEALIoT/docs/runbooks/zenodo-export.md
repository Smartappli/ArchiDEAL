# Zenodo Dataset Export Runbook

This runbook defines how DEALIoT exports datasets to Zenodo. The export creates a Zenodo draft by
default and uploads a dataset/DMP manifest before any dataset files.

## Environment

| Variable | Purpose |
|---|---|
| `ZENODO_ACCESS_TOKEN` | Zenodo or Zenodo Sandbox token with `deposit:write`; `deposit:actions` is required only for publishing |
| `ZENODO_USE_SANDBOX` | defaults to `true`; set to `false` only after production approval |
| `ZENODO_API_BASE_URL` | optional explicit API base URL, must be HTTPS |
| `ZENODO_EXPORT_STAGING_DIR` | optional directory containing files allowed for upload |
| `ZENODO_DEFAULT_CREATOR_NAME` | default creator name for Zenodo metadata |
| `ZENODO_DEFAULT_CREATOR_AFFILIATION` | default creator affiliation |
| `ZENODO_DEFAULT_LICENSE` | default open-data licence, default `cc-by-4.0` |

## API

Create a draft:

```bash
curl -X POST http://localhost:8090/api/datasets/zenodo/export \
  -H "Content-Type: application/json" \
  --data '{"dataset_id":"dataset.telemetry.sensor-minimised"}'
```

Publish only after legal approval:

```bash
curl -X POST http://localhost:8090/api/datasets/zenodo/export \
  -H "Content-Type: application/json" \
  --data '{"dataset_id":"dataset.telemetry.sensor-minimised","publish":true,"legal_review_approved":true}'
```

## Release Gates

Before publishing a Zenodo record:

1. The dataset is registered in `governance.dataset.catalog`.
2. The dataset is linked to an active or approved DMP in `governance.data_management_plans`.
3. GDPR legal basis, DPIA need, retention and recipient categories are reviewed.
4. Data Act entitlement, third-party safeguards and trade-secret controls are reviewed.
5. DGA research protocol, ethics status and disclosure review are recorded.
6. Open release is blocked for internal, restricted, personal, sensitive or mixed datasets.
7. Publication requires `legal_review_approved=true`.
8. The publication approval is recorded in `compliance.legal.dossier`.

## Evidence

Each export must be recorded in `governance.repository.exports` with:

- dataset and DMP identifiers;
- Zenodo deposition or record identifier;
- DOI and record URL when available;
- access right, sandbox flag and uploaded file names;
- legal review status and release gates;
- failure reason if the export is blocked or rejected.

## File Handling

The console uploads a JSON manifest for every export. Dataset files are optional and must be staged
under `ZENODO_EXPORT_STAGING_DIR`. The API rejects path traversal and files outside that directory.

Do not stage raw GPS, raw payloads, media or personal datasets for open publication unless the legal
release review has explicitly approved that publication mode.
