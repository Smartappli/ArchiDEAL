# Event contracts

The JSON Schema content embedded in `apicurio/bootstrap/*.json` is the canonical contract source.
Runtime validators in Rust and Python provide fast boundary checks but must not introduce fields or
constraints that contradict those schemas.

`fixtures/event-envelope-cases.json` is consumed by both language test suites. Any contract change
must update the canonical Apicurio artifact, shared fixtures, runtime validators, and documentation
in one pull request.

Rules:

1. Existing fields are never removed or narrowed in a minor schema version.
2. New fields are optional during a backward-compatible migration window.
3. New producers emit `event_id`, `schema_version`, `occurred_at`, `ingested_at`, and `source`.
4. Apicurio enforces `FULL` validity and `BACKWARD_TRANSITIVE` compatibility in production.
5. Breaking changes require a new topic or major contract version and an explicit migration ADR.
