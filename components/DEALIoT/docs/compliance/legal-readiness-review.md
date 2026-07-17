# DEALIoT Legal Readiness Review

This review records the legal-readiness position of the DEALIoT architecture. It is not a legal
opinion, certification or regulatory filing. Final compliance still requires validation by the
accountable legal, DPO, security and product owners.

## Overall Position

DEALIoT now has a technical evidence baseline for DGA, Data Act, NIS2, DORA and CRA:

- dataset catalogue and Data Management Plans are integrated;
- intermediation, research, access and permission evidence topics are present;
- Data Act access, third-party sharing and safeguards are tracked;
- NIS2/DORA/CRA security and resilience evidence topics are present;
- legal scope decisions and reporting channels are explicit;
- a legal dossier register and release gates are exposed in the management console;
- Zenodo publication is draft-first and blocked without legal approval.

The architecture is not yet legally complete because operating evidence, contracts, notices,
authority channels, approvals and final role decisions must still be recorded.

The legal dossier to close those gaps is defined in
`docs/compliance/legal-compliance-dossier.md` and recorded in `compliance.legal.dossier`.
The repository-side finalisation position is recorded in
`docs/compliance/legal-finalization-report.md`.

## Primary Regulations

| Regulation | Legal position | Implemented evidence | Remaining legal gap |
|---|---|---|---|
| DGA | conditional | data intermediation plane, access requests, permissions, activity logs, research controls | confirm role as data intermediation service or internal governance layer, notification path and neutrality procedures |
| Data Act | partial | connected-product catalogue, user access, third-party sharing, safeguards, legal-basis checks | final user notices, contractual terms, trade-secret procedure and production fulfilment workflow |
| NIS2 | partial | asset inventory, incident events, vulnerabilities, SBOM, continuity and reporting topics | entity classification, Member State transposition mapping and competent authority contact |
| DORA | conditional | ICT risk, third-party risk, resilience evidence and reporting path | applies only for financial entities or ICT third-party provider scope |
| CRA | partial | SBOM, vulnerability, patch and product lifecycle evidence | product classification, conformity assessment, support period and external reporting channel |

## Adjacent Regulations

| Text | Applicability | Legal action before production |
|---|---|---|
| GDPR / RGPD | likely in scope | controller/processor roles, DPIA decision, legal basis, data-subject rights, retention and breach workflow |
| ePrivacy | conditional | assess terminal-equipment access, communications metadata and Member State consent rules |
| AI Act | conditional | create AI system inventory and risk classification before deploying models or decision support |
| Trade Secrets Directive | conditional | apply confidentiality, proportionality and purpose limitation to Data Act releases |
| Radio Equipment Directive | conditional | assess if radio devices or gateways are placed on the EU market |
| GPSR / Product Liability Directive | conditional | product safety file, defect handling, support and update evidence |
| Cybersecurity Act | conditional | certification mapping if required by customers, procurement or sector rules |
| Open Data Directive | conditional | only for public-sector information or public-funded open research-data reuse |
| EHDS | conditional | only if personal electronic health data appears in datasets |

## Zenodo Publication Gate

Zenodo export is legally acceptable only as a controlled publication workflow:

1. Create a draft record first.
2. Upload the dataset/DMP manifest.
3. Stage files only under `ZENODO_EXPORT_STAGING_DIR`.
4. Block open release for internal, restricted, personal, sensitive or mixed datasets.
5. Publish only when `legal_review_approved=true` is recorded.
6. Record repository export evidence in `governance.repository.exports`.

## Legal Blockers Before Go-Live

- Formalise controller, joint-controller and processor roles.
- Complete DPIA and ethics review for research use cases where required.
- Finalise user-facing Data Act notices and third-party sharing terms.
- Decide whether the DGA intermediation rules apply as a regulated service.
- Record NIS2 entity classification and national reporting route.
- Record DORA out-of-scope or in-scope decision for financial-sector use.
- Complete CRA product classification and support/vulnerability disclosure commitments.
- Define retention enforcement for Kafka, object storage, database, backups and Zenodo exports.
- Run a table-top incident exercise covering GDPR, NIS2, CRA and DORA reporting paths.
- Approve the legal dossier artefacts that gate production, third-party sharing, AI deployment,
  product-market release and Zenodo publication.

## Current Conclusion

The current repository supports compliance evidence collection and release gating. It should be
treated as a legally reviewable baseline, not as proof of full compliance. Production use and Zenodo
publication remain blocked until the listed legal and operational decisions are recorded.
