# Developer Community Playbook

This playbook turns occasional interest into repeatable development support for DEALIoT.

## Community Purpose

The developer community should help the project become easier to run, test, extend, document, and adopt without lowering production standards.

The community is not a general chat room. It is a contribution system that turns questions, pilot friction, partner integrations, and documentation gaps into maintained code, tests, docs, examples, and validated use cases.

## Contributor Tracks

| Track | Good first outcome | Maintainer review focus |
|---|---|---|
| Documentation | Clarify one setup, runbook, FAQ, or adoption page | Accuracy and no unsupported claims |
| Device integration | Add one fixture, topic contract, and test path | Reproducibility and schema boundaries |
| Runtime reliability | Improve diagnostics, probes, DLQ, or smoke-test evidence | Operational safety and regression tests |
| Deployment | Improve Kubernetes, Swarm, or local validation guardrails | Secret handling and production risk |
| Data governance | Improve catalog, export, Data Act, DGA, or FAIR evidence | Compliance wording and auditability |
| Community operations | Convert repeated questions into docs, labels, templates, or discussions | Signal quality and maintainability |

## Contribution Ladder

| Level | Scope | Promotion signal |
|---|---|---|
| Visitor | Reads docs, asks Q&A, reports friction | Clear question with context |
| Evaluator | Runs quick evaluation or pilot path | Shares sanitized result or blocker |
| Contributor | Opens docs, tests, fixtures, or small code patch | PR passes review and validation |
| Regular contributor | Repeated high-quality patches in one track | Helps triage or mentor related issues |
| Maintainer candidate | Demonstrates judgment across code, docs, risk, and community | Can review without lowering standards |

## Maintainer Operating Model

Maintain a weekly community loop:

- Label new issues and discussions.
- Convert vague ideas into questions or scoped issues.
- Mark small, safe issues as `good first issue`.
- Mark mentored work as `mentored`.
- Publish at least one contributor-friendly task after each release or pilot.
- Close stale proposals with an explanation when there is no owner, fixture, or test path.

## Good First Issue Criteria

Use `good first issue` only when:

- The expected change fits in one or two files.
- The acceptance criteria are explicit.
- The validation command is listed.
- The task does not require private infrastructure.
- A maintainer can review it without domain-specific back-and-forth.

Use `help wanted` only when:

- The project wants the contribution.
- The scope is defined enough for an external contributor.
- A fixture, example, or failing test can guide the work.

## Community Health Metrics

Track monthly:

- Time to first maintainer response for contributor questions.
- Number of new contributors with a merged docs, fixture, or test patch.
- Number of repeated questions converted into documentation.
- Number of `good first issue` tasks opened and closed.
- Number of partner integrations with fixtures and tests.
- Number of pilot blockers converted into roadmap issues or explicit non-goals.

## Release Community Loop

For every meaningful release:

1. Publish a short note with what changed, who it helps, and how to try it.
2. Link one quick evaluation path or use case.
3. Create or refresh at least two contributor-friendly issues.
4. Thank contributors in release notes when their contribution is public.
5. Update docs if the same question appears twice.
