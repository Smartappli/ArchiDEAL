# Internal Champion Kit

This kit helps a technical or product champion explain DEALIoT inside an organization and convert interest into a measurable pilot.

## One-Sentence Pitch

DEALIoT gives teams a reproducible path from field telemetry to governed, observable, production-ready data flows.

## 5-Minute Sponsor Brief

Use this structure:

1. Problem: field data is fragmented, hard to replay, hard to govern, or hard to operate.
2. Proposed pilot: one data source, one event contract, one useful output, one decision owner.
3. Proof path: local smoke test, 30-day pilot, validation scorecard, production gap list.
4. Risk control: no public secrets, no certification claims, no broad platform commitment before scoring.
5. Decision needed: approve a small pilot or reject the architecture early.

## Stakeholder Map

| Stakeholder | Question | Artifact |
|---|---|---|
| Engineering lead | Can we run and debug it? | Quick evaluation path, smoke test, runbooks |
| Platform owner | Can this be operated safely? | Production readiness, deployment guardrails |
| Data owner | Can data be governed and shared? | DEALData docs, compliance evidence topics |
| Sponsor | What value appears in 30 days? | Pilot playbook and validation scorecard |
| Partner | Can we integrate cleanly? | Integration partner guide and fixture requirement |

## Objection Handling

| Objection | Response |
|---|---|
| This looks large. | Start with one data source and one output; do not deploy the full production target first. |
| We already have MQTT. | DEALIoT focuses on contracts, replay, DLQ, processing, observability, and governance after MQTT. |
| We use a cloud IoT service. | Use DEALIoT when portability, open contracts, and governed evidence matter more than vendor speed. |
| Compliance is not certified. | The repository provides evidence workflows and audit support, not a substitute for formal certification. |
| We need proof. | Run the quick evaluation path and score the pilot before any adoption claim. |

## Internal Email Template

```text
Subject: Proposal: 30-day DEALIoT pilot around one field data source

I propose a small DEALIoT evaluation, not a broad platform migration.

Pilot scope:
- Data source:
- Event contract:
- First useful output:
- Decision owner:
- Production concern to inspect:

Success in 30 days means we can show one governed data path, score the pilot, and decide whether to adopt, extend, harden, or reject the architecture.

References:
- Quick evaluation path: docs/community/quick-evaluation-path.md
- Comparison guide: docs/community/architecture-comparison-guide.md
- Validation scorecard: docs/community/validation-scorecard.md
```

## Champion Checklist

- The pilot has one owner and one data source.
- The value output is measurable in 30 days.
- Security and privacy constraints are written down.
- Production concerns are explicit before the pilot starts.
- The result will become a scorecard, issue, documentation patch, or approved story.
