# User Feedback Loop

This feedback loop makes user input actionable without turning every idea into unprioritized work.

## Intake Types

| Type | Channel | Required detail |
|---|---|---|
| Question | Q&A discussion | Goal, deployment target, command, blocker |
| Bug | Bug issue | Reproduction, expected result, actual result, logs |
| Feedback | User feedback issue | Friction, user segment, impact, suggested outcome |
| Idea | Ideas discussion | Use case, affected component, adoption value |
| Pilot signal | Demo request issue or pilot report discussion | Data source, 30-day outcome, decision owner |
| Adopter story | Adopter story issue | Approval status, sanitized outcome, remaining gaps |

## Triage Flow

1. Classify the input.
2. Check whether the user shared sensitive data; redact or redirect if needed.
3. Ask for missing reproduction or pilot details.
4. Decide: answer, docs, issue, roadmap, non-goal, or private follow-up.
5. Link the resulting artifact back to the original discussion or issue.
6. Review recurring topics monthly.

## Prioritization Score

Score each non-trivial request from 0 to 2.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| User impact | Nice-to-have | Blocks one evaluation | Blocks pilot or repeatable adoption |
| Reproducibility | Vague | Partially reproducible | Reproducible from clean checkout |
| Strategic fit | Outside scope | Adjacent | Core DEALIoT, DealHost, or DealData path |
| Maintenance cost | High or unclear | Moderate | Low or testable |
| Evidence value | Private only | Useful internally | Reusable public proof |

Decision:

- 8-10: candidate for near-term issue or roadmap item.
- 5-7: clarify, document, or place in backlog.
- 0-4: answer as non-goal or defer.

## Feedback Closure

Every feedback item should close with one of:

- Documentation added.
- Test added.
- Issue accepted.
- Roadmap item added.
- Answer provided.
- Private pilot follow-up started.
- Not planned, with reason.

## Monthly Review Questions

- Which question repeated more than once?
- Which pilot blocker prevented the first successful event?
- Which integration request has a clear owner and test path?
- Which support request exposed an unclear boundary?
- Which documentation update would reduce maintainer workload?

## Survey Questions

Use these questions after demos, pilots, or first-time evaluations:

1. What were you trying to prove with DEALIoT?
2. How long did it take to reach the first useful result?
3. What blocked or slowed you down?
4. Which component was hardest to understand?
5. What documentation would have helped?
6. Would you continue to a pilot or integration? Why?
7. Can any result be referenced publicly or privately?
