# Demo Pilot Playbook

Use this playbook to run a credible DEALIoT evaluation with a prospect, partner, or internal team. The target is not a slideware demo. The target is a measurable end-to-end proof from one data source to one governed output.

## Pilot Goal

Prove that DEALIoT can ingest a representative IoT signal, validate the event contract, process or route the stream, expose operational evidence, and produce a decision-ready output within 30 days.

## Inputs Required

| Input | Required detail |
|---|---|
| Data source | MQTT topic, WildFi gateway, media metadata producer, or fixture publisher |
| Data contract | JSON schema, required fields, timestamp semantics, error policy |
| Value output | Dashboard, catalogue entry, export, alert, or downstream integration |
| Operational metric | Ingest latency, DLQ rate, topic throughput, replay time, or export completeness |
| Deployment target | Local Docker Compose, Kubernetes staging, Swarm staging, or DealHost-operated runtime |

## Local Demo Script

```bash
git clone https://github.com/Smartappli/DEALIoT.git
cd DEALIoT
cp .env.example .env
mkdir -p secrets
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
bash scripts/smoke-e2e.sh
```

Expected result: the smoke test publishes fixtures, validates Kafka topics, checks Apicurio artifacts, submits the minimal Flink path, and prints diagnostics on failure.

## Pilot Scorecard

| Criterion | Pass condition | Evidence |
|---|---|---|
| First event | A fixture or real device event reaches Kafka | Smoke-test log or Kafka consumer output |
| Contract governance | Schema is registered and incompatible payloads are rejected or routed to DLQ | Apicurio artifact and DLQ record |
| Operational visibility | Runtime health and lag are visible | Grafana or Prometheus screenshot |
| Recovery path | Restart, replay, or backfill path is documented | Runbook execution note |
| Data value | One catalogue entry, dashboard, alert, or export is produced | Link to output or exported artifact |
| Production gap | Remaining risks are logged | Issue, decision record, or pilot report |

## Demo Narrative

1. Start with the business data problem, not the infrastructure.
2. Show one event entering the platform.
3. Show the schema contract and DLQ behavior.
4. Show processing or routing into an operational output.
5. Show observability and runbook evidence.
6. Close with the production hardening path and explicit gaps.

## Post-Pilot Decision

Choose one of three outcomes:

- Adopt: create a production rollout issue and assign owners for secrets, dependencies, SLOs, and deployment target.
- Extend: add a partner integration, device adapter, or data product before production.
- Stop: record the blocker so the repository can improve or reject a poor-fit use case.
