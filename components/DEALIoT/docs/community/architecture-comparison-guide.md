# Architecture Comparison Guide

This guide helps evaluators compare DEALIoT against common alternatives before starting a pilot.

## Decision Summary

Choose DEALIoT when the team needs a reproducible IoT data architecture with event contracts, stream processing, operational evidence, and a path from local validation to hardened runtime.

Do not choose DEALIoT when the only requirement is a simple device dashboard, a single vendor demo, or a one-off data import.

## Comparison Matrix

| Option | Strong fit | Main weakness | DEALIoT advantage |
|---|---|---|---|
| Custom MQTT script and database | Very small prototype | Hard to govern, replay, scale, and operate | Contracts, topics, DLQ, processing, observability, runbooks |
| Cloud-only IoT service | Fast vendor-native onboarding | Lock-in and portability limits | Open runtime path with Kubernetes, Kafka, Flink, and portable evidence |
| Dashboard-only stack | Quick visualization | Weak data product and compliance story | Governance, exports, schema control, and operational evidence |
| Generic data lake | Batch analytics and storage | Weak real-time ingestion and device flow | MQTT-to-Kafka path, stream processing, latest state, replay |
| Bespoke research pipeline | Publication-focused experiment | Difficult handoff to operations | DEALData publication path plus production guardrails |

## Evaluation Questions

- Can the alternative replay, backfill, and inspect invalid events?
- Can schema changes be governed before production breakage?
- Can operators see health, lag, DLQ, and deployment status?
- Can the team explain how data sharing and publication are controlled?
- Can a partner reproduce the integration from fixtures and tests?
- Can the architecture move from local smoke test to hardened runtime?

## Anti-Fit Signals

DEALIoT is probably too much if:

- There is only one device and no growth path.
- There is no need for event contracts or replay.
- Data governance and compliance evidence are irrelevant.
- The team cannot run containers or managed infrastructure.
- The stakeholder only wants a visual dashboard.

## Adoption Recommendation

Use this rule:

- If the user needs speed only, keep the smallest tool that works.
- If the user needs reliability, governance, replay, scaling, or partner integrations, run the quick evaluation path.
- If the user needs operated infrastructure or compliance boundaries, evaluate DEALHost and DEALData alongside DEALIoT.
