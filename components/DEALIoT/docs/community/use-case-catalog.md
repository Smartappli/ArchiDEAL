# Use Case Catalog

This catalog gives evaluators concrete ways to decide whether DEALIoT fits their architecture, pilot, or partner proposal.

## How To Use This Catalog

Pick one use case, one data source, one output, and one adoption decision. Keep the first pilot small enough to score within 30 days.

## Use Cases

| Use case | User | Data source | DEAL path | Proof in 30 days |
|---|---|---|---|---|
| Livestock telemetry | Farm operator or research team | MQTT sensor and GPS payloads | DEALIoT ingestion, Kafka topics, latest state | First field event reaches dashboard or state table |
| Wildlife or WildFi decoding | Research team | WildFi binary payload | Decoder wrapper, raw sensor/GPS topics, DLQ | Valid payload routes correctly and invalid payload reaches DLQ |
| Precision agriculture monitoring | Farm operator | Soil, weather, device, or camera metadata | MQTT, media metadata, feature events | One operational alert or trend is produced |
| Industrial IoT pilot hardening | Industrial team | Gateway or PLC-derived MQTT stream | Kafka, schema registry, Flink, production overlay | Pilot path runs with documented production gaps |
| Research data publication | Lab or EU project | Curated dataset and metadata | DealData, Zenodo export, OpenAIRE export | Restricted or public metadata export is generated |
| Data Act access workflow | Product or data steward | Connected-product catalogue and sharing request | Legal compliance payloads and evidence topics | Access/share decision is recorded with safeguards |
| Hosting readiness | Platform or hosting partner | Existing customer workload | DealHost boundaries, deployment runbooks | Support scope, SLO, secrets, and deployment target are documented |
| Device partner integration | Device vendor or integrator | New MQTT producer | Topic contract, fixture, docs, test | Clean checkout reproduces the integration fixture |

## Selection Criteria

Choose the first public demo or pilot with these rules:

- The data source can be represented with sanitized fixtures.
- The success metric is visible in one command, dashboard, export, or scorecard.
- The use case maps to an existing event topic or a clearly scoped new topic.
- The result can produce documentation, test coverage, or an approved story.
- The pilot does not require exposing customer secrets or private endpoints.

## Demo Story Format

Use this structure for talks, posts, and show-and-tell:

1. Problem: field data is fragmented or hard to govern.
2. Input: one concrete telemetry, media, or metadata source.
3. Architecture path: ingestion, Kafka, schema, processing, state/export.
4. Evidence: smoke test, logs, topic, dashboard, scorecard, or export.
5. Decision: adopt, extend, harden, or reject.

## Priority Matrix

| Priority | Candidate | Reason |
|---|---|---|
| 1 | Livestock telemetry or WildFi decoding | Already close to repository fixtures and bridge behavior |
| 2 | Research data publication | Strong DealData differentiation and visible export evidence |
| 3 | Industrial pilot hardening | Strong production-readiness story, but needs clear deployment target |
| 4 | Device partner integration | Useful growth loop when a partner can provide fixture and owner |

## Public Proof Assets

- `scripts/smoke-e2e.sh`
- `docs/community/demo-pilot-playbook.md`
- `docs/community/validation-scorecard.md`
- `docs/community/adopter-story-template.md`
- `docs/community/seed-discussions.md`
- `docs/architecture/production-readiness.md`
