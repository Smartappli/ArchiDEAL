# Security Policy

## Supported Versions

Until stable release branches are published, security fixes are handled on the
default branch, `main`.

| Version | Supported |
| ------- | --------- |
| `main`  | Yes       |
| Older snapshots, forks, and unpublished branches | No |

## Reporting a Vulnerability

Do not open a public issue for a vulnerability.

Use GitHub private vulnerability reporting or a GitHub Security Advisory if it is
available for this repository. If a private GitHub reporting channel is not
available, contact the maintainers through the repository owner profile and ask
for a private disclosure channel without including exploit details.

Include the following information when reporting:

- Affected component, endpoint, workflow, manifest, or SDK.
- Steps to reproduce the issue.
- Expected and actual impact.
- Any logs, requests, payloads, or configuration details needed to validate the
  report.
- Whether the vulnerability is already being exploited or publicly disclosed.

## Response Expectations

Maintainers will triage security reports as quickly as practical. Confirmed
vulnerabilities will be fixed on the supported branch and released through the
normal project workflow.

## Security Baseline

Contributors should preserve the existing security posture:

- Do not commit secrets, API tokens, webhook secrets, database credentials, or
  private deployment configuration.
- Keep GitHub webhook signature validation intact.
- Keep administrative API operations protected by the configured admin tokens.
- Avoid exposing Django, Valkey, NATS, or APISIX admin endpoints publicly unless
  the deployment explicitly requires and protects that access.
- Update tests and documentation when changing authentication, authorization,
  route publication, dependency policy, or deployment settings.
