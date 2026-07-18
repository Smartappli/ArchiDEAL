# Disaster recovery runbook

This runbook assumes the production topology defined in `deploy/kubernetes`: Kubernetes spans at
least three zones, while PostgreSQL, Kafka, MQTT, Valkey and APISIX etcd are external HA services.
The secondary region must be provisioned and tested before an incident; a Git repository is not a
substitute for replicated state.

## Targets and authority

- PostgreSQL RPO: 5 minutes; application recovery target: 60 minutes.
- APISIX etcd RPO: 1 hour; restore target: 30 minutes.
- Kafka replication lag target: below 5 minutes; end-to-end service target: 2 hours.
- Only the incident commander authorizes regional failover, DNS changes and data-loss acceptance.
- Platform restores infrastructure, data owners validate consistency, security validates identity,
  PKI and credential rotation, and the release owner runs the authenticated smoke test.

## Ready-state requirements

The secondary region must have three failure zones, network policy enforcement, an Ingress
controller, cert-manager, External Secrets Operator, a metrics adapter and access to the private
GHCR pull Secret. Pre-register `https://PUBLIC_HOST/oauth2/callback` with the OIDC provider for the
failover endpoint. Keep DNS TTL low enough to meet the target, but do not change DNS until the
secondary Ingress and certificate are Ready.

Maintain replicated and tested recovery paths for:

- PostgreSQL WAL/PITR and immutable cross-region snapshots;
- Kafka topics, ACLs, quotas, consumer offsets and cross-region records;
- MQTT ACLs, retained data and persistent sessions;
- Valkey AOF/provider snapshots and APISIX etcd snapshots;
- secret-manager versions, CA chains and digest-pinned release values.

## Scenario actions

| Scenario | Immediate action | Recovery path |
| --- | --- | --- |
| Kubernetes region unavailable | Stop DNS changes and confirm external state health | Build secondary cluster and run ordered promotion |
| PostgreSQL corruption | Contain writes and preserve a pre-containment snapshot | Point-in-time restore both database domains to one timestamp |
| Kafka loss or severe lag | Quarantine MQTT producers and record offsets | Promote replicated Kafka, restore ACLs/offsets, then resume consumers |
| etcd loss | Keep public edge on the last healthy APISIX fleet | Restore snapshot to new three-node etcd and rerun route bootstrap |
| OIDC or Valkey unavailable | Keep the edge fail closed | Restore identity/session dependencies; never enable an auth bypass |
| TLS/private CA compromise | Revoke affected material and hold Ingress | Issue new chains, update secret manager and force a full rollout |

## Regional failover

1. Declare the incident, recovery point, expected data loss and primary/secondary regions in the
   incident log. Freeze automated failback.
2. Fence the old region at database, Kafka and MQTT layers. Confirm there cannot be two writable
   primaries. Preserve pre-failover snapshots and consumer offsets.
3. Promote or restore dependencies in the order documented in `backup-restore.md`. Verify private
   DNS, TLS SNI and least-privilege credentials from the secondary Kubernetes network.
4. Select the last known compatible Git commit and image digests. Use a new `RELEASE_ID`; never
   rebuild an old tag to create a recovery image.
5. Render locally and review the server-side dry run. Then promote without creating the public
   Ingress until all internal gates have passed:

   ```bash
   deploy/kubernetes/deploy-production.sh \
     --values /secure/config/archideal-dr-values.yaml \
     --context archideal-dr \
     --smoke-token-file /secure/tokens/archideal-smoke.jwt
   ```

6. The deployer waits for ExternalSecrets, the Kafka topic/ISR preflight, migrations, all
   controllers and APISIX bootstrap before applying the Ingress. It then waits for the cert-manager
   Certificate and load-balancer address and performs bearer-authenticated health checks through
   the public edge.
7. Change DNS only after the smoke succeeds. Observe DNS convergence, OIDC callbacks, 4xx/5xx
   rates, Kafka lag, MQTT connections, database replication and duplicate event rates.
8. Resume producers gradually. Confirm one test event reaches exactly one expected persistence
   record before removing quarantine or increasing traffic.

If an ArchiDEAL Ingress already exists in the target cluster, the deployer stops unless
`--approve-live-upgrade` is provided. That flag is an operator assertion that migrations follow the
expand/contract pattern and remain compatible with the version currently serving traffic; it is
not a technical bypass for a destructive migration.

## Failed promotion and rollback

Do not route traffic to a release whose migration, rollout, bootstrap, certificate or smoke gate
failed. From the first cluster mutation onward, the deployer's `EXIT` fence deletes
`ingress/archideal`, waits for absence, preserves the original exit code and records these Namespace
annotations:

- `archideal.io/promotion-state=failed`;
- `archideal.io/promotion-release=<failed target>`;
- `archideal.io/active-release=none`;
- `archideal.io/previous-release=<pre-mutation unanimous release>` when one was proven;
- `archideal.io/promotion-invocation=<fresh attempt>`.

If the command reports that Ingress deletion or verification failed, manually verify
`kubectl --context CONTEXT -n archideal get ingress archideal` returns NotFound and remove upstream
DNS/load-balancer routing before proceeding. Preserve the failed Job/Pod logs and Namespace
annotations as incident evidence.

Rollback is permitted only when the live expanded database schema remains backward-compatible.
Retrieve the exact values, signed manifest, Sigstore bundle and evidence directory for the recorded
`previous-release`; do not substitute digests or choose an unrelated release. Create a clean source
worktree at the signed manifest revision because release verification rejects the failed release's
checkout. After an explicit expand/contract compatibility review, run:

```bash
make -C /secure/releases/release-previous/source production-rollback \
  KUBE_CONTEXT=archideal-production \
  ROLLBACK_VALUES=/secure/releases/release-previous/values.yaml \
  ROLLBACK_RELEASE_MANIFEST=/secure/releases/release-previous/release-manifest.json \
  ROLLBACK_RELEASE_BUNDLE=/secure/releases/release-previous/release-manifest.sigstore.json \
  ROLLBACK_RELEASE_EVIDENCE_DIR=/secure/releases/release-previous \
  ARCHIDEAL_BEARER_TOKEN_FILE=/secure/tokens/archideal-smoke.jwt \
  APPROVE_SCHEMA_COMPATIBLE_ROLLBACK=1
```

The wrapper rejects a target other than the recorded previous release. It invokes the complete
signed verifier and ordered deployment, creates fresh APISIX bootstrap and MQTT synthetic Jobs,
and exposes the Ingress for the full authenticated smoke, keeping it only after that gate succeeds.
Any rollback failure is fenced again. It never reverses Django migrations, runs `pg_restore`, or rewinds a schema. If
schema compatibility cannot be proven, leave the Ingress fenced, restore the recorded PostgreSQL
recovery point into new clusters, and repeat the full recovery sequence instead.

For an already-active target region, remove it from DNS before destructive recovery. Roll back DNS
only to a fenced and verified region. Never use DNS as the mechanism that elects a database, Kafka
or MQTT primary.

## Failback

Failback is a separate planned change, not an automatic reversal. Rebuild the original region,
replicate current state into it, run consistency and restore checks, fence the DR writers, and then
perform the same ordered promotion and smoke test. Rotate temporary recovery credentials and
archive the incident timeline, achieved RPO/RTO and all accepted data loss.

## Quarterly exercise

Every quarter, simulate loss of a region without using production credentials. Exercise OIDC
callback failover, private GHCR pulls, PostgreSQL PITR, etcd restore, Kafka offset promotion, MQTT
reconnect, Valkey session recovery, certificate issuance and the authenticated smoke test. Record
actual RPO/RTO and assign owners and dates to every deviation.

The public edge is intentionally single-tenant and operator-only. Anonymous or multi-tenant
failover is unsupported until each application enforces shared tenant identity and resource-level
authorization; disaster recovery must not weaken this boundary.
