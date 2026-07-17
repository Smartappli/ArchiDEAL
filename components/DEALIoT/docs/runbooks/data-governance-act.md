# Data Governance Act Runbook

This runbook translates the Data Governance Act into controls for DEALIoT operations. It is a
technical control baseline, not a legal determination that DEALIoT is or is not a regulated data
intermediation service.

DEALIoT's default data collection purpose is scientific research. External access must therefore be
project-bound, purpose-bound, and backed by research governance evidence before data is shared.
There may also be an intermediation role between collected data and the applications or scientists
that process it. In that mode, applications and researchers must consume mediated data products,
not unrestricted raw topics or buckets.

## Scope Decision

Before enabling external data sharing, record whether DEALIoT is acting as:

- an internal data platform only,
- a data holder exposing product or operational data,
- a data intermediation service between data holders/data subjects and data users,
- a recognised data altruism organisation.

If the deployment offers data intermediation services in the EU, complete the notification process
with the competent authority before operating that service and keep the notification evidence
outside the repository.

If data is contributed voluntarily for objectives of general interest, evaluate whether the
deployment should use a data altruism workflow. In that case, make consent or permission granular,
withdrawable, and tied to the research objective.

## DGA Architecture Controls

DEALIoT uses a dedicated governance plane for DGA evidence:

| Topic | Evidence |
|---|---|
| `governance.data.products` | data product catalogue, purpose, category, format and access mode |
| `governance.access.requests` | fair, transparent and non-discriminatory request decisions |
| `governance.permission.events` | data holder permissions, data subject consent and withdrawals |
| `governance.intermediation.log` | data intermediation activity log |
| `governance.transfer.notices` | unauthorised access, transfer or use notifications |
| `governance.research.projects` | research protocol, objective, ethics status and access model |
| `governance.research.outputs` | publications, derived datasets, models and disclosure review |
| `governance.dataset.catalog` | shareable dataset catalogue, classification, access mode and FAIR metadata |
| `governance.data_management_plans` | Data Management Plan for datasets, retention, sharing and preservation |
| `compliance.scope.decisions` | DGA role and notification scope decision |
| `compliance.reporting.channels` | competent authority, notification template and owner |
| `compliance.legal.dossier` | DGA notification, neutrality and sharing-term approval evidence |

These topics must not contain raw telemetry or media. Store only the minimum metadata required to
prove governance decisions and operate the intermediation service.

## Intermediation Model

The intermediation gateway sits between collected data and consumers:

1. Raw MQTT, media and database-derived data lands in restricted ingestion/storage zones.
2. Data products are registered in `governance.data.products`.
3. Applications, pipelines or scientists submit access requests in `governance.access.requests`.
4. The governance layer checks permissions, consent, research protocol and ethics status.
5. Delivery uses derived topics, minimised exports or controlled object access by default.
6. Every access, share, conversion, withdrawal and publication review is logged.

Default consumer policy:

| Consumer | Default access | Raw access |
|---|---|---|
| Operational applications | derived features and latest state | denied by default |
| Analytics applications | derived data, minimised sensor fields | exceptional and scoped |
| Internal scientists | project-bound derived or minimised datasets | requires protocol and ethics status |
| External researchers | approved research access package | restricted and contract-bound |

## Operating Rules

- Do not use mediated data for the platform operator's own purposes.
- Keep research data product access mediated through documented access requests.
- Do not allow applications or scientists to subscribe directly to raw topics unless an explicit
  exception is approved and logged.
- Publish clear allowed purposes, prohibited purposes, formats, retention and third-country rules.
- Share data in the received format by default; only convert data for interoperability, legal
  requirements, or explicit request/approval.
- Record consent or permission before making personal or non-personal data available to a data user.
- Provide a withdrawal path and log the withdrawal event.
- Keep an activity log for each catalogue view, access request, permission check, data share,
  retrieval, conversion and withdrawal.
- Register each research project before access, including principal investigator, institution,
  objective of general interest, data products, permission model and ethics status.
- Register each shareable dataset and link it to a Data Management Plan before release.
- Prefer derived, aggregated or pseudonymised research datasets over raw GPS, raw payloads and media.
- Perform disclosure review before publishing datasets, reports, dashboards, models or derived
  features.
- Notify affected data holders without delay after unauthorised access, transfer or use of
  non-personal data.
- Keep external data-sharing endpoints behind production TLS, authentication and least-privilege
  topic/object permissions.

## Release Gate

Before production data sharing:

1. Confirm the DGA role and notification status.
2. Record the scope decision in `compliance.scope.decisions`.
3. Review all research data products in the management console.
4. Confirm each product has research purpose, access mode, retention, format and transfer policy.
5. Confirm each active project has protocol and ethics status.
6. Test permission grant, withdrawal and denial workflows.
7. Test unauthorised transfer notice handling.
8. Export the governance evidence topics and attach them to the release record.
9. Approve DGA legal dossier artefacts in `compliance.legal.dossier`.
