# Pilot Validation Scorecard

Use this scorecard at the end of a demo or pilot to decide whether DEALIoT should move forward, be extended, or be rejected for the use case.

## Scoring

Use a 0 to 3 score for each criterion:

- 0: not demonstrated.
- 1: demonstrated manually with major gaps.
- 2: demonstrated with minor gaps or documented workaround.
- 3: demonstrated repeatably with evidence and owner.

## Scorecard

| Criterion | Score | Evidence link | Owner | Follow-up |
|---|---:|---|---|---|
| First event reaches Kafka |  |  |  |  |
| Schema is registered and validated |  |  |  |  |
| Invalid payload reaches DLQ or equivalent error path |  |  |  |  |
| Processing or routing produces target output |  |  |  |  |
| Observability exposes health, lag, and failures |  |  |  |  |
| Replay or backfill path is documented |  |  |  |  |
| Security and secret handling are acceptable |  |  |  |  |
| Production deployment gaps are explicit |  |  |  |  |
| Business value output is accepted by the adopter |  |  |  |  |

## Decision Rule

- 22 or higher: adoption candidate, create production rollout plan.
- 15 to 21: extension candidate, fix explicit gaps before production.
- Below 15: stop or re-scope the use case.

Any score of 0 for security, secrets, or production gaps blocks production adoption regardless of total score.
