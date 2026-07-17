# OpenAIRE Metadata Export Runbook

This runbook defines how DEALIoT exports dataset metadata for OpenAIRE discovery. OpenAIRE is a
catalogue and graph that harvests metadata from trusted data sources; it is not a raw dataset file
upload target like Zenodo.

## Integration Model

DEALIoT creates an OpenAIRE/DataCite metadata package containing:

- a DataCite XML record aligned with the OpenAIRE Guidelines for Data Archives;
- a JSON manifest with dataset, DMP, legal gate and PROVIDE registration context.

The package can then be exposed by an OpenAIRE-compatible repository, OAI-PMH endpoint or data
source registered in OpenAIRE PROVIDE.

## Environment

| Variable | Purpose |
|---|---|
| `OPENAIRE_EXPORT_STAGING_DIR` | directory where metadata packages are written |
| `OPENAIRE_DATASET_LANDING_BASE_URL` | HTTPS base URL for dataset landing pages |
| `OPENAIRE_DEFAULT_CREATOR_NAME` | default creator name for DataCite metadata |
| `OPENAIRE_DEFAULT_CREATOR_AFFILIATION` | default creator affiliation |
| `OPENAIRE_DEFAULT_PUBLISHER` | default DataCite publisher |

## API

Create an OpenAIRE metadata package:

```bash
curl -X POST http://localhost:8090/api/datasets/openaire/export \
  -H "Content-Type: application/json" \
  --data '{"dataset_id":"dataset.telemetry.sensor-minimised"}'
```

Use a DOI or landing page when available:

```bash
curl -X POST http://localhost:8090/api/datasets/openaire/export \
  -H "Content-Type: application/json" \
  --data '{"dataset_id":"dataset.features.latest-state","doi":"10.5281/zenodo.12345"}'
```

## Release Gates

Before exposing records to OpenAIRE:

1. The dataset is registered in `governance.dataset.catalog`.
2. The dataset is linked to an active or approved DMP in `governance.data_management_plans`.
3. Metadata access rights match dataset classification.
4. Personal, restricted, internal or mixed datasets are not marked as open access.
5. GDPR, Data Act and DGA checks are complete where applicable.
6. OpenAIRE discovery is approved in `compliance.legal.dossier`.

## Evidence

Record export evidence in `governance.repository.exports` with:

- dataset and DMP identifiers;
- generated XML and manifest paths;
- identifier type, DOI or landing page;
- access right and legal approval status;
- OpenAIRE PROVIDE registration or OAI-PMH source when available.

## OpenAIRE PROVIDE

To make DEALIoT records discoverable in OpenAIRE, register the final repository or OAI-PMH source in
OpenAIRE PROVIDE. The code-generated package is the metadata payload; PROVIDE registration remains
an organisational step requiring a stable public source URL and repository owner approval.
