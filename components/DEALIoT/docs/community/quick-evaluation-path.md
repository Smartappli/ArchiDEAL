# Quick Evaluation Path

This path helps a new evaluator decide whether DEALIoT deserves a pilot without needing private support.

## Evaluation Goal

The first goal is not to deploy everything. The first goal is to prove that one representative field data source can become one governed event flow with observable evidence.

## 10-Minute Fit Check

Answer these before cloning:

- What data source will represent the first field flow?
- Does the source map to telemetry, GPS, media metadata, dataset publication, governance evidence, or a device integration?
- What is the first useful output: topic, state table, dashboard, export, alert, scorecard, or compliance evidence?
- Who will decide whether the pilot continues?
- Which data must stay private or sanitized?

Stop if there is no concrete data source or no decision owner.

## 60-Minute Technical Check

Use a clean local environment and validate:

- Repository clone succeeds.
- Local configuration and secrets placeholders are understood.
- Smoke test path is identified.
- First event can be traced toward Kafka or the expected runtime topic.
- Failure evidence is readable enough to open a useful issue.

Success is not a perfect deployment. Success is a credible first signal and a short list of blockers.

## 1-Day Pilot Shape

Before a 30-day pilot, define:

- One data source.
- One event contract.
- One operator or stakeholder.
- One value output.
- One dashboard, export, or validation artifact.
- One production concern to inspect: security, scale, replay, observability, governance, or hosting.

## 30-Day Decision

Use `docs/community/validation-scorecard.md` and decide:

- Adopt: the path proves value and the production gaps are manageable.
- Extend: the use case fits, but one integration or contract is missing.
- Harden: the core architecture fits, but deployment, SLO, security, or compliance work blocks production.
- Reject: the architecture does not fit the data source, team constraints, or value output.

## Public Sharing

Convert successful or failed evaluations into durable assets:

- Q&A discussion for a usage question.
- Documentation patch for repeated friction.
- Use case issue for a reusable scenario.
- Pilot scorecard for adoption evidence.
- Approved adopter story when public publication is allowed.
