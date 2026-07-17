# Security Policy

Security reports for DEALData should be handled privately first.

## Supported Scope

Security reports are in scope when they affect:

- Core, Global Positioning System (GPS), sensor, or shared Django service behavior.
- WildFi HTTP ingestion, Kafka ingestion, idempotency, payload parsing, or data validation.
- Deployment files, CI workflows, dependency configuration, or supply-chain metadata.
- Documentation that could cause insecure production configuration.
- Secrets handling, authentication, authorization, database access, logging, or data publication controls.

## Reporting

Do not open a public issue for a vulnerability.

Use GitHub private vulnerability reporting when available, or contact the maintainers through the support channel listed in [SUPPORT.md](./SUPPORT.md) with:

- Affected component and version or commit Secure Hash Algorithm (SHA) identifier.
- Reproduction steps.
- Impact assessment.
- Suggested remediation if known.

## Response Targets

| Severity | Initial triage target | Fix target |
| --- | ---: | ---: |
| Critical | 2 business days | 7 business days |
| High | 5 business days | 14 business days |
| Medium | 10 business days | Next scheduled release |
| Low | 15 business days | Backlog or next minor release |

Targets are operational goals, not contractual service-level agreements (SLAs).

## Disclosure

Maintainers will coordinate disclosure after a fix or mitigation is available. Public advisories should include affected versions, impact, mitigation, and upgrade guidance.
