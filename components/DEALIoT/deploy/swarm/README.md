# Docker Swarm Production Deployment

`dealiot-stack.yml` deploys the DEALIoT application/runtime plane on Docker Swarm.

Before deploying, provision these external production dependencies:

- Kafka bootstrap endpoint
- MQTT broker endpoint
- S3-compatible object storage endpoint and credentials
- Airflow PostgreSQL metadata database
- Airflow Redis broker
- container registry images built by `.github/workflows/build-and-push-images.yml`

Create required Swarm secrets:

```bash
printf '%s\n' "$MQTT_PASSWORD" | docker secret create mqtt_password -
```

Render and deploy:

```bash
export DEALIOT_MQTT_KAFKA_BRIDGE_IMAGE=ghcr.io/smartappli/dealiot-mqtt-kafka-bridge:sha-REPLACE_WITH_RELEASE_SHA
export DEALIOT_MANAGEMENT_CONSOLE_IMAGE=ghcr.io/smartappli/dealiot-management-console:sha-REPLACE_WITH_RELEASE_SHA
export DEALIOT_FLINK_PYFLINK_IMAGE=ghcr.io/smartappli/dealiot-flink-pyflink:sha-REPLACE_WITH_RELEASE_SHA
export DEALIOT_ORCHESTRATION_IMAGE=ghcr.io/smartappli/dealiot-orchestration:sha-REPLACE_WITH_RELEASE_SHA
export KAFKA_BOOTSTRAP_SERVERS=kafka1.example.net:9092,kafka2.example.net:9092
export MQTT_HOST=mqtt.example.net
export MQTT_TOPICS='$share/ingestors/devices/#,$share/ingestors/wildfi/#'
export WILDFI_TOPIC_PREFIXES='wildfi,wild-fi'
export S3_ENDPOINT_URL=https://s3.example.net
export AWS_ACCESS_KEY_ID="$(op read op://dealiot/prod-s3/access-key)"
export AWS_SECRET_ACCESS_KEY="$(op read op://dealiot/prod-s3/secret-key)"
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="$(op read op://dealiot/prod-airflow/database-url)"
export AIRFLOW__CELERY__RESULT_BACKEND="$(op read op://dealiot/prod-airflow/result-backend)"
export AIRFLOW__CELERY__BROKER_URL=redis://redis.example.net:6379/0
export AIRFLOW__CORE__FERNET_KEY="$(op read op://dealiot/prod-airflow/fernet-key)"
export AIRFLOW__API__SECRET_KEY="$(op read op://dealiot/prod-airflow/api-secret-key)"
export AIRFLOW__API_AUTH__JWT_SECRET="$(op read op://dealiot/prod-airflow/jwt-secret)"
export AIRFLOW_ADMIN_PASSWORD="$(op read op://dealiot/prod-airflow/admin-password)"

docker stack deploy -c deploy/swarm/dealiot-stack.yml dealiot
```

Use `dealiot-smoke-stack.yml` only in CI or temporary validation environments.

Decoded WildFi GPS payloads are routed to `raw.gps`. Decoded WildFi IMU, environment, proximity,
movement, and metadata payloads are routed to `raw.sensor`. Keep native WildFi binary logs in object
storage or decode them before publishing telemetry.
