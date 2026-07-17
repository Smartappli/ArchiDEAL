# Production Deployment

## Kubernetes Deployment

Production Kubernetes manifests live in `deploy/kubernetes/overlays/production`.

The overlay expects these external dependencies:

- Kafka with at least three brokers.
- MQTT broker with TLS and ACLs.
- S3-compatible object storage with TLS.
- Airflow metadata PostgreSQL database.
- Airflow Celery broker.

## Pre-Deployment Checklist

1. Build and push images with immutable `sha-<commit>` tags.
2. Replace all `sha-REPLACE_WITH_RELEASE_SHA` image tags.
3. Replace example endpoints in `runtime-config.production.example.env`.
4. Create `dealiot-secrets` through External Secrets Operator, Vault, cloud secrets, or equivalent.
5. Patch NetworkPolicy `ipBlock` ranges to private dependency CIDRs.
6. Confirm metrics-server or another HPA metrics provider is installed.
7. Confirm ingress namespaces are labeled `dealiot.io/ingress=allowed` where required.
8. Render the overlay and reject placeholders before applying.

## Required Render Command

```bash
kubectl kustomize deploy/kubernetes/overlays/production >/tmp/dealiot-production.yaml
```

The rendered manifest must not contain:

- `latest`
- `local-placeholder`
- `sha-REPLACE_WITH_RELEASE_SHA`
- `example.net`
- `SET_FROM_SECRET_MANAGER`

## Required Secret

Create `dealiot-secrets` with these keys:

| Key | Used by |
|---|---|
| `MQTT_PASSWORD` | MQTT-Kafka bridge |
| `KAFKA_SASL_PASSWORD` | Bridge, Flink, Airflow/backfill, Apicurio |
| `MANAGEMENT_CONSOLE_OIDC_CLIENT_SECRET` | Management Console OIDC introspection |
| `MANAGEMENT_CONSOLE_TOKEN` | Local or migration API auth fallback |
| `AWS_ACCESS_KEY_ID` | Flink and Airflow/backfill |
| `AWS_SECRET_ACCESS_KEY` | Flink and Airflow/backfill |
| `AIRFLOW__CORE__FERNET_KEY` | Airflow |
| `AIRFLOW__API__SECRET_KEY` | Airflow |
| `AIRFLOW__API_AUTH__JWT_SECRET` | Airflow |
| `AIRFLOW_ADMIN_PASSWORD` | Airflow bootstrap |
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | Airflow metadata database |
| `AIRFLOW__CELERY__RESULT_BACKEND` | Airflow result backend |
| `AIRFLOW__CELERY__BROKER_URL` | Airflow broker |

## Docker Swarm Deployment

Swarm manifests live in `deploy/swarm/dealiot-stack.yml`.

Required preflight:

```bash
docker stack config -c deploy/swarm/dealiot-stack.yml >/tmp/dealiot-swarm.yaml
```

The rendered stack must use immutable production image tags and must not render placeholder images.

## Rollback Model

- Kubernetes: use rollout history, GitOps revision rollback, or image tag rollback.
- Swarm: update configuration uses `failure_action: rollback`.
- Flink: production uses operator-managed savepoint upgrades and job-aware autoscaling.

## Go-Live Blockers To Resolve Per Environment

- Private dependency endpoints and CIDRs.
- Real secret-store, OIDC, and signer mappings.
- Installation of the optional secret, admission, monitoring, and Flink operator controllers.
- Execution of E2E, fault-injection, and restore drills against staging-managed dependencies.
- Site-calibrated SLO thresholds after the initial staging observation window.
