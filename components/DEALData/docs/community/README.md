# DEALData Community Guide

This directory records the public contribution and support model for DEALData.

## Entry Points

- Ask usage questions in GitHub Discussions before opening broad issues.
- Open bugs only when there is a concrete reproduction path.
- Use feature requests for scoped improvements to data services, ingestion, deployment, or documentation.
- Use private vulnerability reporting for security issues.

## Contribution Tracks

| Track | Examples | Validation |
| --- | --- | --- |
| Core data service | Projects, members, observed objects, experiments | Django checks and layer tests |
| GPS data service | GPS fixes, WildFi `raw.gps`, latest state | GPS layer checks and ingestion tests |
| Sensor data service | Sensor events, WildFi `raw.sensor`, type inference | Sensor layer checks and ingestion tests |
| Shared code | Kafka helpers, common serializers, idempotency helpers | Affected layer tests plus targeted unit tests |
| Operations | Compose files, env examples, CI workflows | Deployment or smoke validation |
| Documentation | README, support, templates, examples | Link and command review |

## Maintainer Expectations

- Keep issues small and reproducible.
- Keep data-contract changes explicit.
- Require tests or documentation for user-facing behavior changes.
- Close support loops by turning repeated questions into docs or templates.
- Keep confidential data, endpoint values, and security details out of public threads.
