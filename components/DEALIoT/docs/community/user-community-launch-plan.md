# User Community Launch Plan

This plan turns DEALIoT adoption assets into a repeatable user community motion. The goal is not to maximize vanity metrics; it is to help real evaluators reach a working pilot, report friction, and convert repeated questions into maintained documentation or product improvements.

## Community Promise

DEALIoT users should be able to:

- Understand whether the platform fits their IoT, hosting, or data-governance use case.
- Run a local validation path without private support.
- Ask public questions without exposing secrets or customer data.
- Propose integrations, pilots, and documentation improvements through structured channels.
- See how feedback becomes issues, roadmap decisions, tests, docs, or explicit non-goals.

## Primary User Segments

| Segment | First value | Community entry point |
|---|---|---|
| Evaluators | Decide whether the architecture is worth a pilot | Q&A discussion and demo pilot playbook |
| Pilot teams | Validate one data source and one outcome in 30 days | Demo request issue and validation scorecard |
| Operators | Understand deployment, monitoring, and support boundaries | Support policy, runbooks, and production-readiness docs |
| Device and integration partners | Add producers, connectors, exports, or deployment patterns | Partner guide and integration proposal |
| Data stewards | Validate sharing, publication, and compliance evidence flows | Legal/compliance docs and DealData discussions |

## Channels

| Channel | Purpose | Public/private | Response target |
|---|---|---|---|
| GitHub Discussions: Q&A | Usage questions, evaluation blockers, operational questions | Public | First response within 3 business days |
| GitHub Discussions: Ideas | Product and integration proposals before issue creation | Public | Triage weekly |
| GitHub Discussions: Show and tell | Demo results, screenshots, lessons learned, approved adopter stories | Public | Acknowledge weekly |
| GitHub Discussions: Contributor help | Contribution scoping, validation guidance, first issue help | Public | First response within 5 business days |
| GitHub Issues | Confirmed bugs, scoped docs gaps, accepted feature work, demo requests | Public | Triage weekly |
| Email `contact@smartappli.com` | Private pilots, managed hosting, sensitive deployment context | Private | Best effort unless contracted |
| Security advisory | Vulnerabilities and sensitive security reports | Private | Follow `SECURITY.md` |

## 30-Day Launch Motion

| Day range | Action | Output |
|---|---|---|
| 1-3 | Publish community entry points in README, SUPPORT, website, issue templates, and discussion templates | Users can find the right channel |
| 4-7 | Publish the first launch discussion, then seed Q&A, pilot, and integration topics | First visitors see useful examples and a clear call for feedback |
| 8-14 | Run one public walkthrough using the local smoke test and pilot playbook | Reusable recording notes and FAQ items |
| 15-21 | Triage every new question into answer, doc patch, issue, or explicit non-goal | Feedback does not disappear |
| 22-30 | Publish a short community status note with metrics, blockers, and next topics | Momentum is visible and measurable |

## Weekly Operating Cadence

| Day | Activity | Checklist |
|---|---|---|
| Monday | Intake triage | Label new issues, answer quick questions, identify blockers |
| Wednesday | Documentation conversion | Turn repeated answers into README, runbook, FAQ, or test updates |
| Friday | Community pulse | Summarize open pilot blockers, accepted ideas, and next actions |

## Decision Rules

- A question becomes documentation when it repeats twice or blocks a pilot.
- A discussion becomes an issue only when the expected behavior and acceptance criteria are clear.
- A feature request needs a user segment, operational impact, data-contract impact, and test path.
- A public adopter story requires written approval and sanitized data.
- Managed hosting commitments require explicit DealHost scope, SLOs, access model, and escalation path.

## Launch Checklist

- [x] Community plan documented.
- [x] Public launch, use-case, popularity, and funnel assets are documented.
- [x] GitHub star growth plan documented.
- [x] User onboarding documented.
- [x] Feedback loop documented.
- [x] Community rituals documented.
- [x] GitHub issue templates cover demo, docs, feature, bug, adopter story, and user feedback.
- [x] GitHub discussion templates cover Q&A, ideas, show-and-tell, pilot reports, and contributor help.
- [x] GitHub discussion templates cover launch announcements.
- [x] Developer community playbook, contributor onboarding, and community governance are documented.
- [x] Seed discussion drafts are documented.
- [x] First GitHub Discussion title and body are documented.
- [x] Community labels are defined in `.github/labels.yml`.
- [x] README links to community entry points.
- [x] SUPPORT explains where users should ask.
- [x] Website adoption section links to the community plan.
- [ ] Repository administrator enables GitHub Discussions if it is not already enabled.
- [ ] Repository maintainer publishes the first launch discussion from `docs/community/first-github-discussion.md`.
- [ ] Repository maintainer publishes the seeded discussions from `docs/community/seed-discussions.md`.

## Metrics

Track these monthly:

- Time from first user question to first maintainer response.
- Time from clone to first successful smoke test for new evaluators.
- Number of questions converted into documentation or tests.
- Number of demo requests with one concrete data source and one success metric.
- Number of pilot scorecards completed.
- Number of public or private adopter stories approved for reference.

## Anti-Patterns

- Do not present unvalidated interest as adoption.
- Do not move sensitive support context into public threads.
- Do not accept vague feature requests without user impact and acceptance criteria.
- Do not create a chat channel that bypasses issues, discussions, and documentation.
- Do not promise production operations in public support channels.
