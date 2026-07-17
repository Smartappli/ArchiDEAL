# Community Governance

This governance model keeps the DEALIoT community useful while the project is still early.

## Principles

- Evidence over hype: adoption claims need approved proof.
- Small contributions first: contributors should be able to start with docs, fixtures, tests, or scoped issues.
- Production safety: popularity must not weaken security, reliability, or compliance boundaries.
- Public knowledge by default: repeated answers become docs, tests, templates, or explicit non-goals.
- Private data stays private: pilots, datasets, incidents, and partner details require approval before publication.

## Roles

| Role | Responsibility | Boundary |
|---|---|---|
| Maintainer | Review changes, triage issues, protect scope and quality | Does not provide emergency production support publicly |
| Regular contributor | Submit repeated high-quality patches and help with scoped triage | Does not approve releases or security-sensitive changes |
| Community helper | Answer questions, point to docs, improve templates | Does not make roadmap commitments |
| Evaluator | Run quick checks, pilots, and scorecards | Sanitizes data before public sharing |
| Partner | Provides fixtures, integration context, and owner for a track | Must keep vendor-specific behavior optional |

## Decision Process

- Bugs: accepted when reproduction, expected behavior, and impact are clear.
- Features: discussed first unless the scope and acceptance criteria are obvious.
- Integrations: require fixture, topic or API contract, documentation, and tests.
- Adoption claims: require approved scorecard, public-safe story, or listed adopter reference.
- Governance or support changes: require maintainer review and documentation updates.

## Recognition

Recognize public contributions through:

- Release notes.
- `show-and-tell` discussions.
- Contributor mentions in relevant docs when appropriate.
- `ADOPTERS.md` only for approved adopter references.

Do not publish company, dataset, pilot, or personal details without explicit approval.

## Escalation

- Security issues follow `SECURITY.md`.
- Conduct issues follow `CODE_OF_CONDUCT.md`.
- Managed operations or private pilots go through `contact@smartappli.com`.
- Public disagreements should be resolved by documenting facts, impact, tradeoffs, and a maintainer decision.
