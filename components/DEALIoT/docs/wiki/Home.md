# DEALIoT Wiki

This wiki is the production handbook for DEALIoT.

## Start Here

- [Architecture](Architecture)
- [Production Deployment](Production-Deployment)
- [Configuration Reference](Configuration-Reference)
- [Security and Compliance](Security-and-Compliance)
- [Operations and Scaling](Operations-and-Scaling)
- [CI/CD and Release](CI-CD-and-Release)
- [Runbook Index](Runbook-Index)

## Adoption Resources

The versioned community assets are maintained in `docs/community/`:

- `docs/community/adoption-playbook.md`
- `docs/community/architecture-popularity-playbook.md`
- `docs/community/github-star-growth-plan.md`
- `docs/community/use-case-catalog.md`
- `docs/community/quick-evaluation-path.md`
- `docs/community/architecture-comparison-guide.md`
- `docs/community/internal-champion-kit.md`
- `docs/community/public-launch-kit.md`
- `docs/community/first-github-discussion.md`
- `docs/community/adoption-funnel.md`
- `docs/community/user-community-launch-plan.md`
- `docs/community/user-onboarding-guide.md`
- `docs/community/developer-community-playbook.md`
- `docs/community/contributor-onboarding.md`
- `docs/community/community-governance.md`
- `docs/community/community-rituals.md`
- `docs/community/user-feedback-loop.md`
- `docs/community/seed-discussions.md`
- `docs/community/demo-pilot-playbook.md`
- `docs/community/integration-partner-guide.md`
- `docs/community/validation-scorecard.md`
- `docs/community/adopter-story-template.md`

Use them to position the architecture, earn legitimate GitHub stars, publish the first GitHub Discussion, select public use cases, compare alternatives, run quick evaluations, help internal champions, run pilots, onboard users and contributors, triage feedback, onboard integration partners, and prepare public adopter references.

## Current Production Target

Kubernetes is the primary production target. Docker Swarm is maintained as a simpler production-capable runtime and as a CI smoke target.

The application manifests do not deploy Kafka, PostgreSQL, Redis, MQTT, or production object storage. Those dependencies must be provided by managed services or dedicated operators.

## Runtime Planes

| Plane | Components | Production expectation |
|---|---|---|
| Ingestion | MQTT broker, MQTT-Kafka bridge | MQTT TLS, ACLs, bridge replicas, shared subscriptions |
| Event backbone | Kafka, Apicurio Registry | 3+ brokers, SASL/SSL or mTLS, schema compatibility governance |
| Object storage | S3-compatible storage | TLS, bucket lifecycle policy, checkpoint and savepoint buckets |
| Processing | Flink, Beam, Airflow | checkpointed streams, replay jobs, bounded backfills |
| Storage | TimescaleDB, HAProxy, PgBouncer | managed PostgreSQL or operator-managed HA PostgreSQL |
| Operations | Prometheus, Grafana, Management Console | authenticated access, probes, alerting and runbooks |

## Release Gates

A release is not production-ready unless all gates pass:

- Unit, integration, deployment, and smoke tests pass.
- Production Kubernetes overlay renders without placeholders.
- Production Swarm stack renders without placeholders.
- Images use immutable `sha-<commit>` tags.
- Runtime secrets are supplied out of band.
- NetworkPolicies are narrowed to private dependency CIDRs.
- Pod Security `restricted` is enforced on runtime namespaces.
- SBOM and provenance are generated for published images.
