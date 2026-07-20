# Observability alert runbook

This runbook covers alerts shipped in `deploy/kubernetes/base/observability.yaml`. It does not
cover provider-specific Kafka, PostgreSQL, certificate, backup or restore alerts; those remain in
the restricted platform runbooks and are mandatory before production GO.

## First response for every alert

1. Acknowledge the page, record the alert start time, production release ID and image digests, and
   assign the owner shown on the alert.
2. Check whether Prometheus is scraping the expected stable job and whether the
   `monitoring.archideal.io/enabled: "true"` monitor/rule selectors are active. Never treat missing
   telemetry as a healthy service.
3. Compare the alert start with deployments, secret rotations, OIDC changes and external provider
   incidents. Preserve pod logs, APISIX error logs, alert query output and Kubernetes events.
4. Stop or reduce producers when continued processing could lose, reject or reorder data. Do not
   delete Kafka records, move consumer offsets, relax TLS/OIDC, disable NetworkPolicy or replay
   production traffic without incident-commander approval and a recorded recovery point.
5. After mitigation, verify the authenticated public smoke test and a uniquely identified GPS and
   sensor event. Observe recovery for at least the alert's longest query window before resolving.

Silence only a known duplicate symptom under an active parent incident. A silence needs an owner,
incident/change link and expiry; do not silence `absent()` or complete-unavailability alerts during
a rollout merely because monitoring is inconvenient.

## ArchiDEAL edge error budget burn

Alerts: `ArchiDEALEdgeErrorBudgetFastBurn`, `ArchiDEALEdgeErrorBudgetSlowBurn`.

Inspect `apisix_http_status` by `route`, `code` and upstream node. Confirm the eligible request
denominator is non-zero and that health/synthetic traffic is not being mixed into the query. Split
5xx errors by route, then correlate APISIX logs and traces with DEALHost, DEALData, DEALIoT or
DEALInterface errors.

- For one failing route, remove or roll back only that compatible route/workload.
- For a release-wide regression, use the previous digest-pinned release and the documented
  expand/contract rollback. Do not downgrade a schema destructively.
- For an external database, etcd or OIDC incident, keep the edge fail closed and follow the
  provider recovery runbook.

Resolve only after the five-minute error ratio is healthy and the long window is recovering.
Record error-budget consumption; an exhausted budget blocks ordinary releases.

## ArchiDEAL edge latency high

Alert: `ArchiDEALEdgeLatencyHigh`.

`apisix_http_latency` is reported in milliseconds and converted to seconds by the recording rule.
Compare `type="request"`, `type="upstream"` and `type="apisix"` by route. Check traffic volume,
payload size, pod CPU/memory throttling, APISIX connections, database latency and external service
latency. A low-volume p95 can be unstable; retain the sample count with the incident evidence.

Scale only after identifying the bottleneck and confirming HPA capacity. If upstream latency is the
cause, restore or shed traffic at that upstream rather than increasing APISIX replicas blindly.

## ArchiDEAL monitoring target unavailable

Alerts: `ArchiDEALAPISIXUnavailable`, `ArchiDEALOAuth2ProxyUnavailable`.

Determine whether the workload is unavailable or discovery is broken:

```bash
kubectl --context "$KUBE_CONTEXT" -n archideal get pods,services,endpoints
kubectl --context "$KUBE_CONTEXT" -n archideal get servicemonitors.monitoring.coreos.com
kubectl --context "$KUBE_CONTEXT" -n archideal describe networkpolicy \
  monitoring-identity-ingress monitoring-dealdata-ingress monitoring-ingestion-ingress
```

Verify the Prometheus instance watches `archideal`, selects the enabled monitor label, and runs in
the configured monitoring namespace. For oauth2-proxy, the shipped rule measures scrape
reachability only; inspect OIDC/Valkey logs and perform an approved operator login before declaring
authentication healthy. Never add an anonymous bypass to recover monitoring.

## ArchiDEAL APISIX etcd unavailable

Alert: `ArchiDEALAPISIXEtcdUnavailable`.

Check all three etcd endpoints, quorum, certificate expiry, client certificate authorization, SNI,
DNS and port 2379 reachability from APISIX. Preserve `apisix_etcd_reachable` by pod and the etcd
revision. If quorum is lost, keep the last healthy APISIX data plane serving only while routes and
credentials remain valid; do not initialize an empty etcd cluster under the production prefix.
Restore into a new quorum according to `backup-restore.md`, verify the snapshot, then rerun the
idempotent route bootstrap.

## ArchiDEAL runtime management unavailable

Alerts: `ArchiDEALRuntimeControllerUnavailable`,
`ArchiDEALRuntimeKubernetesBackendUnavailable`, `ArchiDEALRuntimeWorkerUnavailable`.

First distinguish discovery, process health and dependency health. The controller metric target
uses HTTPS with the private controller CA; a failed scrape can therefore mean an expired or
mismatched certificate as well as a stopped process. The controller readiness and
`dealhost_runtime_controller_kubernetes_ready` additionally prove a bounded authenticated query to
the Kubernetes API. Worker readiness requires both a recent processing-loop heartbeat and a query
of the durable PostgreSQL operation store. Readiness fails after one heartbeat deadline; liveness
uses twice that deadline so Kubernetes restarts a persistently wedged loop without turning a
single bounded controller request into a restart. The metrics-only Service publishes NotReady
addresses deliberately, so its diagnostic scrape remains reachable while readiness is false.

```bash
kubectl --context "$KUBE_CONTEXT" -n archideal get pods,services,endpoints \
  -l 'app.kubernetes.io/name in (dealhost-runtime-controller,dealhost-runtime-worker)'
kubectl --context "$KUBE_CONTEXT" -n archideal get servicemonitor \
  archideal-runtime-controller archideal-runtime-worker -o yaml
kubectl --context "$KUBE_CONTEXT" -n archideal logs deploy/dealhost-runtime-worker \
  --all-pods --since=20m
kubectl --context "$KUBE_CONTEXT" -n archideal logs deploy/dealhost-runtime-controller \
  --all-pods --since=20m
```

For controller backend failure, inspect ServiceAccount token projection, the exact runtime-apps
Role/RoleBinding, API-server DNS/TLS and `KUBERNETES_API_EGRESS_CIDR`. For worker failure, inspect
PostgreSQL TLS/connectivity and the loop heartbeat age before restarting anything. A controller
outage does not authorize giving the web Deployment a controller token or Kubernetes permissions.
Do not delete queued operations: they are idempotent durable records and should drain after the
dependency is restored. Confirm at least one controller and worker target is ready, then observe a
new uniquely keyed test operation reach a terminal state before resolving.

## ArchiDEAL runtime operation backlog or stall

Alerts: `ArchiDEALRuntimeOperationBacklogOld`, `ArchiDEALRuntimeOperationBacklogHigh`,
`ArchiDEALRuntimeOperationStuck`.

Compare `dealhost_runtime_operation_queue_depth`,
`dealhost_runtime_operation_oldest_age_seconds`, `dealhost_runtime_operation_stale_leases` and
`dealhost_runtime_active_controller_failures`. All worker replicas intentionally report the same
database-backed queue gauges, so use `max`, not `sum`, when investigating global depth. Break the
backlog down by the bounded `operation_type` and `status` labels, then correlate the oldest request
time with controller 4xx/5xx logs and Kubernetes rollout events. Never add deployment IDs,
application names or idempotency keys as metric labels.

A short lease-free interval while a reconciliation schedules its next poll is normal. The stale
lease gauge counts only an expired lease or a lease-free operation already eligible to run. The
worker normally fails a reconciliation after 30 minutes; a running age above 35 minutes therefore
indicates that timeout enforcement itself is not progressing. Preserve the operation row and
logs, restore worker/controller capacity, and let lease recovery replay it. Manually changing
status, generation, lease fields or idempotency keys can violate ordering and is prohibited. Scale
workers only after confirming the bottleneck is worker capacity rather than Kubernetes or database
availability.

## ArchiDEAL bridge unavailable or degraded

Alerts: `ArchiDEALBridgeUnavailable`, `ArchiDEALBridgeReplicaDegraded`.

Inspect bridge readiness by pod, MQTT shared-subscription state, Kafka metadata access, TLS chain,
SASL principal ACLs and failure-zone scheduling. `ready=1` requires an MQTT SUBACK reason code
granting QoS 1 for every configured subscription and the latest periodic Kafka metadata check to
succeed; an ACL rejection or QoS downgrade is a loop error and reconnect, never a successful
readiness acknowledgement. Inspect
`dealiot_bridge_mqtt_subscriptions_ready`, `dealiot_bridge_kafka_ready` and
`dealiot_bridge_kafka_metadata_errors_total`; the Kafka check runs every 15 seconds and is bounded
to 5 seconds. Confirm at least two replicas are ready before restoring normal producer volume. Do
not switch to clean MQTT sessions or plaintext brokers as a shortcut.

## ArchiDEAL bridge delivery errors

Alert: `ArchiDEALBridgeDeliveryErrors`.

Inspect `dealiot_bridge_errors_total`, pod restarts and logs around Kafka produce or MQTT event-loop
failure. Compare `received_total` and `forwarded_total`, but remember that MQTT redeliveries can
increase the received counter more than once for one logical event. Manual MQTT acknowledgement
occurs only after Kafka acknowledges the record, so leave failed events unacknowledged and repair
Kafka/MQTT connectivity. Queue admission is bounded to 5 seconds and Kafka delivery to 30 seconds;
investigate broker saturation rather than raising these limits to conceal an outage. After recovery,
verify idempotent downstream persistence and bounded duplicates before increasing traffic.

## ArchiDEAL invalid event ratio high

Alerts: `ArchiDEALBridgeDlqRatioHigh`, `ArchiDEALConsumerRejectedRatioHigh`.

Identify the event contract/version and producer release from structured logs; never add device IDs
or event IDs as metric labels. Sample sanitized records from `dlq.events` and compare them with the
versioned topic/schema contract. The bridge alert proves that a rejected event was durably written
to the DLQ. The consumer rejection alert is distinct: current consumer metrics prove rejection but
do not prove a second DLQ write. Preserve the source Kafka offsets and quarantine affected
producers until the contract owner approves a compatible decoder or replay.

## ArchiDEAL bridge Kafka latency high

Alert: `ArchiDEALBridgeKafkaLatencyHigh`.

The histogram measures successful produce acknowledgement latency, not the full MQTT-to-DEALData
path. Check broker ISR, request queue, throttling, network/TLS latency and producer error logs.
Confirm all required topics still have replication factor 3 and at least two in-sync replicas. Do
not lower `acks=all`, replication factor or `min.insync.replicas` to clear the alert.

## ArchiDEAL DEALData consumer unavailable

Alerts: `ArchiDEALGPSConsumerUnavailable`, `ArchiDEALSensorConsumerUnavailable`,
`ArchiDEALConsumerNoAssignedCapacity`.

Readiness requires a recent healthy Kafka poll and a successful `SELECT 1` database check. It does
not require a partition: a standby replica can remain ready during a RollingUpdate when the group
has fewer partitions than pods. Liveness is only the process-local HTTP server, so a dependency
outage should remove the pod from readiness without a kubelet restart loop. Inspect these metrics
by service and pod:

- `dealdata_consumer_kafka_assigned`;
- `dealdata_consumer_database_ready`;
- `dealdata_consumer_last_successful_poll_timestamp_seconds`;
- `dealdata_consumer_poll_errors_total`.

The capacity alert fires only when every observed replica for a service has
`dealdata_consumer_kafka_assigned=0`; one unassigned standby alone is expected. Check group
membership, topic partition count, assignment, ACLs, broker TLS and PostgreSQL TLS/HA. Never reset
a group to `latest`. If offsets must move, record both old and new offsets, preserve the source
data, and obtain data-owner approval.

## ArchiDEAL DEALData commit or database errors

Alerts: `ArchiDEALConsumerCommitFailure`, `ArchiDEALConsumerDatabaseErrors`.

On commit failure, assume a processed batch can be replayed; verify idempotency keys before
recovery. On a database error, check primary election, pool saturation, TLS hostname validation,
disk/capacity and migration compatibility. Do not commit the affected Kafka batch manually. Restore
database health, allow the consumer to replay, then compare inserted and duplicate counters and
confirm no source offsets skipped the failed batch.

## ArchiDEAL DEALData freshness high

Alert: `ArchiDEALConsumerFreshnessHigh`.

The metric covers successful first inserts only. Compare event-age p95 by `service` with Kafka
provider lag, consumer assignment, batch size, database persistence duration and producer clocks.
If Kafka lag is not exported, this alert alone cannot distinguish upstream delay from consumer
delay and the production evidence is incomplete. Reduce producer rate or add consumer capacity only
after checking partition count and assignment; replicas beyond available partitions do not help.

## ArchiDEAL invalid event clock

Alert: `ArchiDEALConsumerInvalidEventClock`.

Missing, malformed, timezone-naive or future source timestamps are excluded from the freshness
histogram and counted. Identify the producer/firmware and verify NTP/clock discipline using
correlated logs. Do not rewrite timestamps silently. Quarantine invalid producers or apply a
versioned, audited normalization rule, then verify new events use timezone-aware UTC timestamps.

## Closure evidence

Attach the alert query and labels, affected release, start/detection/mitigation/recovery times,
relevant sanitized logs/traces, Kafka offsets and database checks, smoke result and follow-up owner.
If the alert exposed a missing metric or runbook step, the observability gate remains NO-GO until
that gap is tracked and tested in staging.
