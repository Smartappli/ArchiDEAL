# Integration Partner Guide

This guide defines how hosting providers, systems integrators, research infrastructure teams, and device vendors can integrate with DEALIoT without creating a fork that cannot be maintained.

## Partner Tracks

| Track | Fit | Expected contribution |
|---|---|---|
| Device adapter | Sensor, gateway, or MQTT producer vendor | Topic contract, fixture payload, documentation, smoke test |
| Hosting runtime | Cloud, sovereign host, on-prem operator | Deployment profile, network/security contract, backup and observability notes |
| Data product | Analytics, catalogue, FAIR publication, or export partner | Schema mapping, governance evidence, export validation |
| Compliance workflow | Legal, DGA, Data Act, DORA, CRA, or FAIR specialist | Template, evidence topic mapping, review checklist |

## Integration Contract

Every integration should provide:

- A short use case and adoption audience.
- Runtime dependencies and supported deployment targets.
- Event topics and schemas touched by the integration.
- Failure modes and DLQ behavior.
- Required secrets and data sensitivity notes.
- A smoke or unit test that runs in CI or can be executed locally.
- Documentation linked from README, docs, or the website when public.

## Technical Boundaries

- Do not add vendor-specific secrets or endpoints to tracked files.
- Do not require mutable container tags for production.
- Do not bypass schema governance for runtime topics.
- Do not introduce unsafe browser DOM sinks or unauthenticated mutation APIs.
- Keep stateful production dependencies external unless a dedicated operator owns their lifecycle.

## Contribution Flow

1. Open an integration proposal issue.
2. Agree on the smallest event contract and test scope.
3. Add fixtures, documentation, and CI-safe tests.
4. Add deployment notes for Docker Compose, Kubernetes, or DealHost.
5. Request review with operational and security risks called out explicitly.

## Partner Readiness Checklist

- The integration has a named owner.
- A clean checkout can reproduce the demo path.
- Secrets are supplied out of band.
- The integration can be disabled without breaking the base platform.
- Documentation explains when the integration should not be used.
