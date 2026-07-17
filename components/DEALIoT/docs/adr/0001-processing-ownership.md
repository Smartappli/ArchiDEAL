# ADR 0001: Processing ownership

- Status: accepted
- Date: 2026-07-10

## Context

The Kubernetes base deployed both the Rust stream normalizer and a Flink session cluster. Both
processing paths can write `features.events` and `state.latest`, which makes ownership ambiguous
and can create duplicate or conflicting projections.

## Decision

Flink is the sole authoritative owner of stateful projections in production. Its checkpointed
`LatestByEntity` state owns `state.latest`.

The Rust normalizer is an alternative lightweight mode. It writes `features.events` by default and
may write `state.latest` only when `STREAM_NORMALIZER_STATE_OUTPUT_ENABLED=true` is explicitly set
for a non-production deployment.

Kubernetes processing modes are packaged as separate Kustomize resource packages. A site overlay must
select exactly one of them.

## Consequences

- Production upgrades and rescaling must preserve Flink checkpoints or savepoints.
- The Rust mode can scale as a stateless consumer when state output is disabled.
- CI rejects a production render containing both processing writers.
