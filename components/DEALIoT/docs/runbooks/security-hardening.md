# Security Hardening Runbook

The current Compose topology is safe enough for local validation only. These controls are required
before a non-local deployment.

## Network Exposure

The base Compose file must not publish host ports. Local ports belong in `docker-compose.dev.yml`.
Production-like exposure belongs behind an explicit edge service, currently `seaweedfs-edge`.

Verify:

```bash
grep -n "^[[:space:]]\\{4\\}ports:" docker-compose.yml && exit 1 || true
```

## Required Controls

- Kafka: enable SASL/TLS and ACLs; remove PLAINTEXT listeners outside local dev
- MQTT: use per-client credentials or certificates; avoid shared admin credentials for producers
- PostgreSQL/PgBouncer: use SCRAM or certificate authentication; avoid `auth_type = plain`
- UIs: require authentication and route through Caddy or another controlled ingress
- Secrets: keep `.env` and `secrets/` out of Git and Docker build contexts
- Images: build with pinned dependencies, scan images, and publish SBOMs

## Rotation

Rotate all credentials after:

- accidental commit or log exposure
- handover between environments
- failed deployment where logs may have been shared externally
- any change to authentication mode

Rotation must include:

- `.env` values
- Docker secret files
- PostgreSQL roles
- SeaweedFS S3 credentials
- VerneMQ credentials
- Grafana and pgAdmin admin users
