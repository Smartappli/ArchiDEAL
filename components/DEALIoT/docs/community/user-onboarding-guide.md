# User Onboarding Guide

This guide is the first path for a new DEALIoT user, evaluator, pilot team, or integration partner.

## Choose Your Path

| Goal | Start here | Expected output |
|---|---|---|
| Understand the platform | Read `README.md` and the public website | Decide if the architecture fits your use case |
| Validate locally | Follow the quickstart and smoke test | First event reaches Kafka and health checks pass |
| Scope a pilot | Use `demo-pilot-playbook.md` | One data source, one value outcome, one scorecard |
| Propose an integration | Use `integration-partner-guide.md` | Integration contract with test and ownership boundaries |
| Share adoption evidence | Use `adopter-story-template.md` | Approved public or private adoption story |

## First 60 Minutes

1. Read the platform scope in `README.md`.
2. Check `SUPPORT.md` so you use the right channel.
3. Clone the repository and review `.env.example`.
4. Run the local validation path documented in the README.
5. Capture the commit SHA, command output, and deployment target.
6. If blocked, open a Q&A discussion or bug issue with logs and sanitized configuration.

## What To Share Publicly

- Repository commit SHA.
- Deployment target: local Compose, Kubernetes, Swarm, DealHost, or other.
- Commands run and sanitized logs.
- Data source type: MQTT device, media object, WildFi payload, backfill, or synthetic fixture.
- Whether the blocker affects evaluation, pilot, production, documentation, or contribution.

## What Not To Share Publicly

- Production secrets.
- Customer data.
- Private endpoint values.
- Raw personal data.
- Proprietary payloads unless explicitly sanitized.
- Security vulnerabilities; use private reporting instead.

## Community Entry Points

- Q&A discussion: usage questions and evaluation blockers.
- Ideas discussion: early product or integration proposals.
- Show and tell discussion: approved demo results and lessons learned.
- User feedback issue: reproducible friction that is not clearly a bug.
- Demo request issue: scoped pilot or evaluation request.
- Security advisory: vulnerability reports.

## Good Question Template

```text
Goal:
Deployment target:
Repository commit:
Command run:
Expected result:
Actual result:
Sanitized logs:
What I already tried:
```

## Pilot Readiness

Before starting a pilot, confirm:

- One data source is selected.
- One Kafka topic or event contract is in scope.
- One operational dashboard or data product is expected.
- One owner can make the adoption decision.
- A scorecard will be completed at the end of 30 days.

## Maintainer Response Model

Maintainers should resolve each user interaction as one of:

- Direct answer.
- Documentation patch.
- Bug issue.
- Feature issue.
- Pilot or partner follow-up.
- Explicit non-goal with reasoning.
