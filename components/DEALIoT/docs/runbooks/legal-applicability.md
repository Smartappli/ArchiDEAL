# Legal Applicability Runbook

This runbook records adjacent legal scope checks for DEALIoT. It is a technical evidence baseline,
not a legal opinion or certification.

## Default Decision

Treat DGA, Data Act, NIS2, DORA and CRA as the primary architecture tracks. In addition, every
dataset release, research project, product release and AI feature must record whether the following
texts are applicable, conditional or out of scope.

## Applicability Matrix

| Text | DEALIoT status | Trigger | Evidence |
|---|---|---|---|
| GDPR / RGPD | applicable | personal telemetry, GPS, media metadata or research datasets | `dataact.legal_basis.checks` |
| ePrivacy Directive | conditional | terminal access, electronic communications metadata or tracking identifiers | `compliance.scope.decisions` |
| AI Act | conditional | AI systems, models or decision support deployed by DEALIoT | `compliance.control.assessments` |
| Trade Secrets Directive | conditional | generated data includes protected know-how or confidential business data | `dataact.safeguards` |
| Radio Equipment Directive | conditional | radio gateways or devices placed on the EU market | `cra.product.lifecycle` |
| GPSR / Product Liability Directive | conditional | connected products, software or digital services supplied as products | `cra.product.lifecycle` |
| Cybersecurity Act | conditional | certification required by customers, procurement or sector rules | `compliance.control.assessments` |
| Open Data Directive | conditional | public-sector information or public-funded open research-data reuse | `governance.dataset.catalog` |
| EHDS | conditional | personal electronic health data appears in datasets | `governance.dataset.catalog` |

## Required Controls

Before production sharing or publication:

1. Register the dataset in `governance.dataset.catalog`.
2. Link the dataset to an approved or active DMP in `governance.data_management_plans`.
3. Record GDPR legal basis, minimisation, retention and recipient categories.
4. Record whether ePrivacy, AI Act, product, open-data or EHDS scope is in scope.
5. Apply Data Act safeguards before third-party access, including trade-secret controls.
6. Prefer derived, minimised, pseudonymised or aggregated datasets over raw GPS, raw payloads and
   media.
7. Record the required legal dossier artefact in `compliance.legal.dossier`.

## AI Gate

No model or AI-assisted decision support should be released until the platform records:

- AI system name, owner, purpose and consumer profile;
- input datasets and DMP identifiers;
- risk classification and prohibited-use check;
- training/evaluation lineage when the model is trained or fine-tuned;
- human oversight, monitoring and incident handling;
- privacy and security controls.

## Product Gate

If DEALIoT is distributed as software, a gateway image or a connected/radio product:

- record the product-market role and support period in `cra.product.lifecycle`;
- keep SBOM, provenance, vulnerability and patch evidence;
- define security update and vulnerability disclosure channels;
- keep product safety and defect-handling evidence where GPSR or Product Liability applies;
- assess Radio Equipment Directive scope for radio devices.

## Review Cadence

Review this matrix before:

- adding a new telemetry source, media type or connected product;
- creating a dataset release or research project;
- onboarding a third-party application or scientist;
- deploying AI or model-based analysis;
- shipping software, gateway images or radio devices outside internal labs.
