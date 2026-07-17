# Dataset Catalogue And Data Management Plan Runbook

This runbook defines the minimum dataset catalogue and Data Management Plan (DMP) controls for
DEALIoT research and data-sharing workflows. It is a technical baseline; legal and ethics decisions
must still be recorded by the accountable owner.

## Evidence Topics

| Topic | Evidence |
|---|---|
| `governance.dataset.catalog` | dataset identity, owner, source, access mode, licence, retention and FAIR metadata |
| `governance.data_management_plans` | project DMP, datasets, legal basis, access, sharing, retention and preservation plan |
| `governance.research.projects` | research objective, investigator, ethics status and permission model |
| `governance.research.outputs` | dataset publications, models, reports and disclosure review |
| `governance.repository.exports` | repository and Zenodo export evidence, DOI and publication gate |
| `compliance.legal.dossier` | legal release artefacts, retention schedule and publication approval |

Do not store raw data in these topics. They contain metadata and governance evidence only.

## Dataset Catalogue Minimum Fields

Each dataset that can be shared, exported, analysed externally or published must have:

- dataset identifier and title;
- owner and steward;
- source data products and source topics;
- classification, including whether personal data is in scope;
- schema references and metadata standard;
- access mode and licence/reuse policy;
- retention and preservation policy;
- linked DMP identifier.

## DMP Minimum Fields

Each research project or data-sharing programme must have a DMP covering:

- datasets used or produced;
- FAIR metadata and interoperability standards;
- legal basis, permission or consent model;
- ethics review status where applicable;
- access and sharing policy;
- retention, preservation and disposal plan;
- security controls, including pseudonymisation and least privilege;
- roles, responsibilities, review date and cost owner.

## Release Gate

Before releasing a dataset to an application, third party, scientist or repository:

1. Register the dataset in `governance.dataset.catalog`.
2. Link it to an approved or active DMP in `governance.data_management_plans`.
3. Confirm legal basis and Data Act entitlement where applicable.
4. Prefer derived, minimised or aggregated datasets over raw GPS, raw payloads and media.
5. Complete disclosure review before publication.
6. Create a Zenodo draft only after catalogue and DMP checks.
7. Create OpenAIRE metadata packages only after catalogue, DMP and metadata rights checks.
8. Log export or sharing evidence in the Data Act, DGA or repository export topics.
9. Keep the legal dossier gate approved for the target release mode.
