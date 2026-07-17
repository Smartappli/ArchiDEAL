# Kubernetes Production Deployment

The Kubernetes manifests are a Kustomize base for the DEALIoT application/runtime plane.

Production prerequisites:

- a Kafka endpoint, preferably managed or operated by Strimzi,
- an MQTT broker endpoint,
- an S3-compatible endpoint,
- PostgreSQL and Redis for Airflow,
- images published by `.github/workflows/build-and-push-images.yml`,
- a `dealiot-secrets` Secret in the deployment namespace.

Create the production secret out of band:

```bash
kubectl create namespace dealiot
kubectl -n dealiot create secret generic dealiot-secrets \
  --from-literal=MQTT_PASSWORD="$MQTT_PASSWORD" \
  --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  --from-literal=AIRFLOW__CORE__FERNET_KEY="$AIRFLOW__CORE__FERNET_KEY" \
  --from-literal=AIRFLOW__API__SECRET_KEY="$AIRFLOW__API__SECRET_KEY" \
  --from-literal=AIRFLOW__API_AUTH__JWT_SECRET="$AIRFLOW__API_AUTH__JWT_SECRET" \
  --from-literal=AIRFLOW_ADMIN_PASSWORD="$AIRFLOW_ADMIN_PASSWORD" \
  --from-literal=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="$AIRFLOW__DATABASE__SQL_ALCHEMY_CONN" \
  --from-literal=AIRFLOW__CELERY__RESULT_BACKEND="$AIRFLOW__CELERY__RESULT_BACKEND" \
  --from-literal=AIRFLOW__CELERY__BROKER_URL="$AIRFLOW__CELERY__BROKER_URL"
```

Deploy the base:

```bash
kubectl apply -k deploy/kubernetes/base
```

Deploy the production overlay after replacing image tags and external endpoints:

```bash
kubectl apply -k deploy/kubernetes/overlays/production
```

Use `deploy/kubernetes/overlays/production/dealiot-secrets.example.env` and
`deploy/kubernetes/overlays/production/runtime-config.production.example.env` as operator-facing
templates. Do not commit real production values.
