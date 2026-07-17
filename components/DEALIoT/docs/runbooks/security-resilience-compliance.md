# Security Resilience Compliance Runbook

This runbook translates NIS2, DORA and CRA into DEALIoT technical controls. It is a technical
evidence baseline, not a legal certification.

## Scope Decision

Record the legal and operational scope before production:

- NIS2 depends on the entity type, sector, size thresholds and national transposition.
- DORA applies when DEALIoT is operated by a financial entity or provides ICT services in scope for
  the financial sector.
- CRA applies when DEALIoT software or connected components are made available on the EU market as
  products with digital elements.

If the scope is uncertain, keep the controls enabled and mark the legal scope decision as pending.

## Evidence Topics

| Topic | Evidence |
|---|---|
| `security.asset.inventory` | assets, owners, dependencies, criticality and classifications |
| `security.incident.events` | incident severity, affected assets, reporting deadlines and status |
| `security.vulnerability.findings` | vulnerability source, CVE, asset, due date and remediation |
| `security.sbom.attestations` | SBOM, provenance, digest and signature evidence |
| `security.patch.events` | security update planning, deployment and rollback evidence |
| `resilience.backup.tests` | restore tests, RPO/RTO result and recovery evidence |
| `resilience.operational.risk` | ICT risk scenarios, mitigations and residual-risk decisions |
| `resilience.third_party.risk` | supplier criticality, contract, subcontracting and exit plan |
| `compliance.scope.decisions` | in-scope, out-of-scope or conditional regulatory decisions |
| `compliance.control.assessments` | control status, evidence, gaps, owner and next action |
| `compliance.reporting.channels` | authority, trigger, deadline, template and owner |
| `compliance.legal.dossier` | legal artefacts, approvals and release-gate status |
| `cra.product.lifecycle` | support period, update channel and vulnerability disclosure |

These topics store control evidence only. Do not place secrets, exploit details, raw telemetry or
personal data in them.

## Release Gates

Before a production release:

1. Critical services, topics, buckets, secrets and providers are registered in
   `security.asset.inventory`.
2. Released images and artifacts have SBOM and provenance records in
   `security.sbom.attestations`.
3. Critical vulnerabilities are patched, mitigated or formally accepted by an owner.
4. Incident channels, severity rules and reporting deadlines are documented.
5. Backup and restore tests prove the target RPO/RTO.
6. Critical third-party ICT providers have a security review and exit plan.
7. Legal scope decisions are recorded for DGA, Data Act, NIS2, DORA and CRA.
8. CRA product lifecycle and vulnerability disclosure are recorded if the platform is shipped as a
   product with digital elements.
9. Adjacent legal scope is recorded for GDPR, ePrivacy, AI Act, trade secrets, product legislation,
   open-data rules and EHDS where relevant.
10. Mandatory legal dossier artefacts are approved in `compliance.legal.dossier`.

## NIS2 Controls

- Maintain a cyber risk baseline with asset inventory, dependencies and owners.
- Operate incident handling, recovery and post-incident review.
- Test business continuity and backup restoration.
- Assess supply-chain and provider risk.
- Enforce production TLS, strong authentication, least privilege and cryptography.

## DORA Controls

Apply these controls when DORA scope is confirmed:

- maintain an ICT risk register and critical function dependency map;
- classify major ICT-related incidents and retain reporting evidence;
- run operational resilience tests, including restore and vulnerability tests;
- track ICT third-party providers, subcontracting, concentration risk and exit plans;
- keep evidence suitable for financial-sector oversight or customer assurance.

## CRA Controls

When DEALIoT is shipped as a product with digital elements:

- keep secure-by-design defaults and hardening evidence;
- maintain SBOM and provenance for product components;
- operate vulnerability handling and coordinated remediation;
- provide tested security updates and rollback plans;
- define external notification workflow for exploited vulnerabilities and incidents.
- define the product support period, security update channel and vulnerability disclosure URL.

## Adjacent Legal Checks

The compliance scope register must also capture:

- GDPR / RGPD when telemetry, GPS, media metadata or research data can identify people or
  operators;
- ePrivacy when terminal access, communications metadata or tracking identifiers are involved;
- AI Act before any AI system, model or decision support is deployed;
- Trade Secrets Directive safeguards when Data Act sharing exposes protected know-how;
- Radio Equipment Directive, GPSR and Product Liability when connected/radio products are placed
  on the EU market;
- Open Data Directive for public-sector information or public-funded research-data reuse;
- EHDS only if datasets contain personal electronic health data.

## Operating Rules

- Production plaintext protocols are not accepted.
- Security evidence topics are append-only or compacted according to the contract.
- Critical vulnerabilities block release unless mitigated or accepted by the accountable owner.
- Emergency changes must create `security.patch.events` records and post-change review evidence.
- Incident records must include affected assets, severity, status and reporting channel.
- Recovery tests must be repeated after major storage, Kafka, database or orchestration changes.
