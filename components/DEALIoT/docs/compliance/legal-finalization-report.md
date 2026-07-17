# DEALIoT Legal Finalization Report

Date: 2026-05-31

This report closes the repository-side legal compliance work. It does not approve production use,
certify compliance or replace DPO/legal review. It states what is finalised in the architecture and
what still requires real organisational approval.

## Finalised In The Repository

| Area | Status | Evidence |
|---|---|---|
| Dataset catalogue | finalised | `governance.dataset.catalog` and management console dataset view |
| Data Management Plan | finalised | `governance.data_management_plans` and DMP controls |
| Zenodo export | finalised | draft-first export, manifest upload and legal publication gate |
| OpenAIRE export | finalised | DataCite/OpenAIRE metadata package and external discovery gate |
| DGA/Data Act intermediation | finalised | access, permission, intermediation, research and sharing evidence topics |
| NIS2/DORA/CRA evidence plane | finalised | security, resilience, incident, vulnerability, SBOM and reporting topics |
| Legal dossier | finalised | `compliance.legal.dossier` schema, templates and UI |
| Legal release gates | finalised | production, dataset, third-party, AI, product and incident gates |
| Tests and coverage | finalised | automated tests enforce topic, schema, API, UI and deployment contract presence |

## Still Requiring Human Legal Approval

These items cannot be completed from source code because they depend on actual deployment facts,
organisational roles, jurisdictions, contracts and signatures:

| Decision | Owner | Evidence to record |
|---|---|---|
| Controller, joint-controller and processor roles | DPO / legal | `compliance.legal.dossier` |
| DPIA/AIPD requirement and outcome | DPO / privacy | `compliance.legal.dossier` |
| Privacy, device and Data Act notices | legal / product | `compliance.legal.dossier` |
| Data subject rights and retention operating procedure | DPO / data stewardship | `compliance.legal.dossier` |
| DGA regulated intermediation or internal-platform role | legal / governance | `compliance.scope.decisions` |
| NIS2 entity classification and national route | legal / security | `compliance.scope.decisions` |
| DORA financial-sector scope | legal / platform risk | `compliance.scope.decisions` |
| CRA product classification and conformity path | product security / legal | `cra.product.lifecycle` |
| AI Act inventory and risk class | AI governance / legal | `compliance.legal.dossier` |
| Competent authority contacts and reporting templates | legal / security | `compliance.reporting.channels` |
| Third-party sharing, Zenodo publication and OpenAIRE discovery approval | legal / research governance | `compliance.legal.dossier` |

## Final Operating Position

The repository is finalised as a compliance-ready architecture. Production, external sharing,
regulated intermediation, AI deployment, product-market release, Zenodo publication and OpenAIRE
discovery remain blocked until the corresponding approval records are completed and approved.
