# Security And Compliance

## Security Baseline

Production requires:

- TLS or private encrypted connectivity for all external dependencies.
- Kafka `SASL_SSL` or mTLS.
- MQTT TLS and broker ACLs.
- Kubernetes default-deny NetworkPolicies.
- Pod Security `restricted` labels on runtime namespaces.
- Service-account token automount disabled by default.
- Container capabilities dropped.
- `allowPrivilegeEscalation: false`.
- `runAsNonRoot: true`.
- Runtime secrets supplied out of band.
- Immutable image tags.
- SBOM and provenance generation for published images.

## Network Policy Model

Production starts with `default-deny-all`, then opens:

- DNS egress.
- Namespace-internal runtime traffic.
- Private dependency egress for Kafka, MQTT TLS, S3 TLS, PostgreSQL, Redis, and HTTPS.
- Airflow API ingress from namespaces labeled `dealiot.io/ingress=allowed`.
- Management Console ingress from namespaces labeled `dealiot.io/ingress=allowed`.

Patch broad private CIDRs to environment-specific ranges before go-live.

## Compliance Evidence Topics

The platform stores operational evidence in Kafka topics for:

- Data Governance Act controls.
- Data Act user access, sharing, safeguards, and legal basis checks.
- Security asset inventory, incidents, vulnerabilities, SBOM, and patch events.
- Resilience backup tests, operational risk, and third-party risk.
- Legal scope decisions, control assessments, reporting channels, and legal dossiers.
- CRA product lifecycle evidence.

Do not store raw secrets, exploit details, or unnecessary personal data in evidence topics.

## Release Gates

Before production go-live:

1. Asset inventory and owners are recorded.
2. ROPA, DPIA, privacy notices, retention schedule, DPA checks, and incident playbook are approved where applicable.
3. Critical vulnerabilities are remediated or formally accepted.
4. Restore tests prove RPO/RTO targets.
5. Third-party and ICT supplier risks are recorded.
6. Dataset releases have DMP and legal review evidence.
7. Zenodo/OpenAIRE publication approval is recorded where relevant.
8. Image signature admission policy is configured at cluster level.

## Relevant Repository Docs

- `docs/runbooks/security-hardening.md`
- `docs/runbooks/security-resilience-compliance.md`
- `docs/compliance/legal-compliance-dossier.md`
- `docs/compliance/legal-readiness-review.md`
- `docs/compliance/templates/`
