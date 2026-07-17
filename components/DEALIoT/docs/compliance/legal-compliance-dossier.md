# DEALIoT Legal Compliance Dossier

This dossier defines the legal artefacts that must exist before DEALIoT moves from a technical
evidence baseline to controlled production, data sharing or publication. It is not a legal opinion,
certification or regulatory filing. Final decisions must be approved by the accountable legal,
DPO, security, product and research owners.

## Evidence Topic

Record approved legal artefacts in `compliance.legal.dossier`. Link operational evidence to:

- `compliance.scope.decisions` for applicability and role decisions;
- `compliance.reporting.channels` for authority contacts and deadlines;
- `compliance.control.assessments` for control status and residual gaps;
- `dataact.legal_basis.checks` for personal-data release checks;
- `governance.dataset.catalog`, `governance.data_management_plans` and
  `governance.repository.exports` for dataset, DMP and repository publication evidence.

## Mandatory Artefacts

| Artefact | Regulation | Required before | Minimum decision |
|---|---|---|---|
| ROPA register | GDPR | production go-live | processing purposes, roles, categories, recipients, transfers and retention are recorded |
| DPIA/AIPD | GDPR | high-risk collection or research use | required/not required decision and mitigations are approved |
| Privacy and device notices | GDPR, ePrivacy, Data Act | data collection | notices explain purposes, rights, generated data, recipients and retention |
| Data subject rights procedure | GDPR | production go-live | request intake, ownership, deadline and refusal paths are defined |
| Processor and sharing terms | GDPR, DGA, Data Act | third-party sharing | roles, processor clauses, purpose limits and safeguards are binding |
| DGA role notification | DGA | mediated data service | intermediation role, neutrality, no own reuse and authority route are recorded |
| NIS2 entity classification | NIS2 | production go-live | essential/important/out-of-scope status and national route are recorded |
| DORA scope decision | DORA | financial-sector use | in-scope/out-of-scope role is recorded before customer commitment |
| CRA conformity file | CRA | EU market release | product role, support period and vulnerability handling are recorded |
| AI inventory | AI Act | AI deployment | risk class, purpose, dataset lineage and oversight are recorded |
| Retention schedule | GDPR, DGA, Data Act | production go-live | topics, buckets, databases, backups and exports have deletion rules |
| Incident notification playbook | GDPR, NIS2, DORA, CRA | production go-live | triggers, owners, templates, channels and exercise evidence exist |
| Zenodo publication approval | GDPR, DGA, Data Act, Open Data | publication | catalogue, DMP, licence, access right and legal approval are linked |
| OpenAIRE discovery approval | GDPR, DGA, Data Act, Open Data | external discovery | catalogue, DMP, landing page, metadata rights and legal approval are linked |

## Release Gates

- Production go-live is blocked until ROPA, DPIA decision, notices, rights procedure, retention
  schedule and incident playbook are approved.
- Dataset sharing is blocked until catalogue, DMP, legal-basis check, sharing terms and access
  policy are recorded.
- Zenodo publication is draft-only until `legal_review_approved=true` is recorded.
- OpenAIRE discovery is metadata-only and blocked until access rights match classification.
- Third-party sharing is blocked until recipient identity, user authority, signed terms and
  safeguards are approved.
- AI deployment is blocked until the AI inventory, risk class and oversight record exist.
- Product market release is blocked until CRA and adjacent product-law scope decisions are recorded.

## Operating Rule

Every new telemetry source, dataset, research project, external application, scientist access path,
AI feature, product release or repository publication must create or update a legal dossier record.
If the dossier status is `draft`, `needs_review` or `blocked`, the release gate remains closed.

## Finalization Rule

The repository-side legal control architecture is complete when all required topics, schemas,
templates, UI views, API payloads and tests are present. Production compliance is complete only
when the corresponding `compliance.legal.dossier`, `compliance.scope.decisions` and
`compliance.reporting.channels` records are approved with real organisation details.
