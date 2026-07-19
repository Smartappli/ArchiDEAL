# Backup and restore runbook

This runbook covers the Kubernetes production architecture in `deploy/kubernetes`. The
application workloads are stateless; Kafka, MQTT, PostgreSQL, Valkey and etcd are external HA
services owned by the platform team. Provider-specific commands must be kept in the restricted
operations repository and tested against a non-production account before use.

## Recovery objectives and evidence

| State | Backup mechanism | Maximum RPO | Restore target | Required evidence |
| --- | --- | ---: | ---: | --- |
| PostgreSQL metadata, data and DEALIoT registry | Continuous WAL archiving plus encrypted multi-AZ snapshots and cross-region copy | 5 min | 60 min | Successful PITR and application consistency checks, including device revisions and retirement state |
| Kafka topics | Cross-region replication plus versioned topic, ACL and quota definitions | 5 min | 2 h | Replication lag, topic counts and consumer-offset comparison |
| MQTT configuration and sessions | Provider replication/snapshot plus versioned ACL and listener configuration | 15 min | 60 min | Client reconnect, persistent-session and shared-subscription test |
| APISIX etcd | Encrypted hourly snapshots copied cross-region | 1 h | 30 min | `etcdutl snapshot status` or provider verification and route inventory |
| Valkey | TLS HA service with AOF or provider-equivalent snapshots | 15 min | 30 min | Write/read probe and oauth2-proxy session creation |
| Kubernetes desired state | Git commit, digest-pinned release values and rendered-manifest CI artifact | One release | 30 min | Server-side dry run and controller readiness |
| Secrets and PKI | Versioned secret-manager entries with protected cross-region replication | Provider SLA | 30 min | ExternalSecrets Ready, certificate chain and rotation date |

Backups are encrypted with a recovery key that is not stored in the Kubernetes cluster. Enable
object lock or the provider's immutable-retention control on cross-region copies. Alert on a
missed backup, replication lag above the stated RPO, expired certificates and restore-test age.

## Before every release

1. Record the Git commit, `RELEASE_ID`, every image digest, database migration level and external
   service version in the change ticket.
2. Confirm the latest PostgreSQL recovery point and etcd snapshot are healthy and replicated.
3. Confirm Kafka cross-region lag is within five minutes and MQTT session replication is healthy.
4. Verify the secret-manager recovery path, including the read-only GHCR pull credential at
   `SECRET_PREFIX/ghcr/dockerconfigjson`.
   Confirm the Kafka console, producer and consumer credentials map to distinct least-privilege
   principals and that the consumer/preflight principal can describe topic RF/ISR configuration.
5. Use expand/contract database migrations. A migration applied while the previous Ingress is
   serving traffic must remain compatible with the previous application version.

## Restore decision and containment

The incident commander declares the restore point and records why newer data may be discarded.
Before changing state:

- stop producers or route them to a durable quarantine where possible;
- prevent two regions from accepting writes at the same time;
- preserve database, etcd, Kafka and MQTT snapshots from immediately before containment;
- record consumer offsets, Kafka replication lag, DNS state and the active release;
- remove or withhold the public Ingress in a new recovery cluster until all internal checks pass.

Never restore etcd or PostgreSQL over the only remaining copy. Restore to new clusters/endpoints,
validate them, and then switch the production aliases.

## Restore order

Restore dependencies in this order so APISIX and the applications never observe a partially
restored control plane:

1. Secret manager, KMS/HSM access, DNS private zones and the OIDC provider.
2. PostgreSQL clusters to the selected consistent recovery time.
3. Kafka DR cluster, topic configuration, ACLs and consumer offsets; then MQTT configuration and
   persistent sessions.
4. Valkey and the APISIX etcd cluster.
5. Kubernetes cluster controllers: CNI policy enforcement, metrics, cert-manager and External
   Secrets Operator.
6. ArchiDEAL configuration and secrets, migration Jobs, application controllers and APISIX routes.
7. Public TLS Ingress, DNS and the authenticated production smoke test.

## PostgreSQL procedure

1. Select one timestamp before the incident and use it for metadata, data and the DEALIoT registry
   clusters.
2. Restore provider snapshots and replay WAL to that timestamp into new endpoints.
3. Verify TLS hostname validation, synchronous standby health and that the recovery timeline is
   writable only in the elected primary region.
4. Run read-only checks for database names, migration tables, row counts and critical foreign-key
   relationships. For `dealiot_registry`, verify `dealiot_schema_migrations`, device revision
   monotonicity and soft-retirement timestamps. Compare them with the recorded release migration
   level.
5. Update the private endpoint aliases and secret-manager passwords if the restore created new
   credentials. Render a new release ID and wait for its
   `externalsecret/archideal-runtime-secrets-${RELEASE_ID}` to become Ready. Do not attempt to
   refresh or reuse an existing release ID for rotated values.
6. Run the release migration Jobs only through `deploy-production.sh`; do not invoke migrations
   concurrently from application replicas.

## Kafka and MQTT procedure

1. Promote exactly one Kafka DR cluster. Reapply versioned topics with replication factor 3,
   `min.insync.replicas=2`, quotas and least-privilege ACLs.
   Reconcile the full `components/DEALIoT/deploy/kafka/topics.yaml` catalog; the Kubernetes
   preflight checks only the seven topics required by the currently deployed runtime.
2. Compare source and target high-water marks. Restore or translate the GPS and sensor consumer
   group offsets before starting DEALData consumers.
3. Promote exactly one MQTT cluster, restore listeners and per-device/ingestor ACLs, then verify
   TLS client trust and persistent sessions.
4. Publish a uniquely identified test event. Confirm one Kafka record and exactly one persisted GPS
   or sensor record; do not replay production traffic until duplicate-handling has been checked.

## etcd and Valkey procedure

1. Verify the etcd snapshot checksum and revision, then restore it to a new three-member cluster in
   three failure zones. Use fresh member identities and peer URLs.
2. Restore the `/archideal/apisix` prefix only from a snapshot belonging to the selected release.
   Configure the APISIX client certificate, private CA, SNI and scoped etcd username/password.
3. Restore Valkey through the managed provider or validated AOF path. Require TLS on port 6380 and
   confirm HA failover before oauth2-proxy starts.
4. Treat oauth2-proxy sessions as revocable. If Valkey session integrity is uncertain, start with an
   empty session database and require operators to authenticate again.

## Kubernetes promotion and validation

Prepare a new values file from the recorded release; never recover secret values into it. Then run:

```bash
deploy/kubernetes/deploy-production.sh \
  --values /secure/config/archideal-recovery-values.yaml \
  --context archideal-recovery \
  --smoke-token-file /secure/tokens/archideal-smoke.jwt
```

The deployer waits for both ExternalSecrets, the Kafka topic/ISR preflight, migrations,
Deployments, the ingestion StatefulSet, APISIX bootstrap, the Certificate, Ingress admission and
authenticated smoke checks. Do not expose the recovery cluster if any gate fails.

After a secret or CA rotation, use a new `RELEASE_ID` and rerun the deployer. It stamps each
PodTemplate with the release and a runtime revision derived from the live Secret and ConfigMaps,
which forces the workloads to consume the new material. Revoke the previous GHCR/OIDC/database
credentials only after the rollout and smoke check succeed.

## Monthly restore exercise

Restore into an isolated account and namespace every month. Capture timestamps for each recovery
objective, checksums, restored revisions, row/topic counts, smoke output and cleanup approval. A
failed or overdue exercise blocks production releases until the platform owner accepts and tracks
a remediation.
