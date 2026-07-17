# Zenodo Publication Approval Template

Use this template before publishing a Zenodo record. Draft creation may happen before approval;
publication must remain blocked until this checklist is approved.

| Check | Status |
|---|---|
| Dataset exists in `governance.dataset.catalog` |  |
| DMP exists in `governance.data_management_plans` |  |
| Dataset is derived, minimised, aggregated or otherwise approved for release |  |
| GDPR legal basis, DPIA decision and retention are reviewed |  |
| Data Act entitlement and safeguards are reviewed where applicable |  |
| DGA research protocol, ethics and disclosure review are complete |  |
| Licence, access right and embargo are approved |  |
| Files are staged only under `ZENODO_EXPORT_STAGING_DIR` |  |
| `legal_review_approved=true` is recorded before publication |  |
| Export evidence is recorded in `governance.repository.exports` |  |

Record the approved artefact in `compliance.legal.dossier` with
`artifact_type=zenodo_approval`.
