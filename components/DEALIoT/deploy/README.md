# Production Deployment Targets

This directory contains production deployment targets for orchestrators that are not Docker
Compose.

The production model is intentionally split from the local Compose topology:

- Docker Compose remains the local development and integration environment.
- Docker Swarm and Kubernetes deploy the application/runtime plane.
- Stateful production services should be provided by managed services or dedicated operators:
  Kafka, PostgreSQL/Airflow metadata, Redis, S3-compatible object storage, MQTT, and monitoring
  storage.

This avoids pretending that bind-mounted single-host Compose services are a reliable multi-node
production architecture.

## Targets

| Target | Path | Purpose |
|---|---|---|
| Docker Swarm | `deploy/swarm/dealiot-stack.yml` | Production Swarm stack for the application plane |
| Swarm smoke | `deploy/swarm/dealiot-smoke-stack.yml` | CI-only stack that verifies image/startup wiring |
| Kubernetes | `deploy/kubernetes/base` | Kustomize base for the application plane |
| Kubernetes production | `deploy/kubernetes/overlays/production` | Strict production overlay with immutable image tags and NetworkPolicies |
| Kubernetes smoke | `deploy/kubernetes/overlays/ci-smoke` | CI-only kind overlay |

## GitHub validation

The workflow `.github/workflows/production-deployment-test.yml` validates both orchestrators:

1. renders the production Swarm stack,
2. deploys a Swarm smoke stack,
3. renders the Kubernetes Kustomize base,
4. renders the Kubernetes production overlay and rejects mutable `latest` tags,
5. deploys a Kubernetes smoke overlay on kind.

The smoke deployments do not start the full data platform. They prove that the production
deployment assets, image packaging, secrets, service accounts, and rollout mechanics are valid in
ephemeral CI infrastructure.
