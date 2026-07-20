# ArchiDEAL service-level objectives

This document is the production reliability contract for the unified ArchiDEAL request and event
paths. It defines targets and the telemetry required to prove them; it does not claim that a target
is currently met. A production rollout remains blocked while an indicator has no queryable metric,
owner, alert route, or runbook.

## Scope and measurement window

Objectives are measured over a rolling 30-day window in the production environment. Planned
maintenance is included unless the service has been explicitly removed from customer traffic. Test,
synthetic, and health-check traffic must be identifiable and excluded from customer indicators.

| Service indicator | Objective | Operational owner |
| --- | ---: | --- |
| Public APISIX requests that do not fail because of ArchiDEAL | 99.9% | platform on-call |
| Public API request latency | p95 below 750 ms | platform on-call |
| MQTT events accepted and durably acknowledged by Kafka | 99.9% | ingestion on-call |
| MQTT-to-DEALData persistence freshness | p95 below 60 seconds | data platform on-call |
| Invalid-event DLQ ratio | below 0.5% | data contract owner |
| DEALData Kafka consumer lag age | p95 below 60 seconds | data platform on-call |
| Signed release rollback or recovery after a failed rollout | below 15 minutes | release manager |

The latency targets are initial limits. They must be calibrated with at least two weeks of staging
telemetry and an agreed production load model before launch; calibration may tighten a target but
must not silently weaken it.

## Indicator contracts

The production overlay deploys Prometheus Operator discovery and rules in
`deploy/kubernetes/base/observability.yaml`. These are the metrics that exist in the deployed
applications; the table deliberately distinguishes complete and partial indicators.

| Indicator | Deployed source | Coverage |
| --- | --- | --- |
| Edge availability | APISIX `apisix_http_status`, route IDs prefixed `archideal-` | Measurable for traffic that reaches APISIX; eligible responses are 2xx, 3xx and 5xx, with 5xx counted as errors. OIDC rejection and Ingress failure before APISIX are not included. |
| Edge latency | APISIX `apisix_http_latency_bucket{type="request"}` | Measurable; APISIX reports milliseconds and the recording rule converts to seconds. |
| Identity-edge reachability | Prometheus `up{job="archideal-oauth2-proxy"}` | Reachability only. oauth2-proxy authentication success/failure counters are not assumed to exist. |
| MQTT bridge delivery | `dealiot_bridge_received_total`, `forwarded_total`, `errors_total`, `ready`, MQTT/Kafka dependency gauges | Operational coverage. Readiness includes a periodic bounded Kafka metadata check, so an idle bridge detects a post-start broker outage. `forwarded_total` increments only after Kafka acknowledgement and MQTT manual acknowledgement. Received deliveries can include broker redeliveries and counters reset on restart, so this is not by itself a unique-event 30-day durability SLI. |
| MQTT-to-Kafka latency | `dealiot_bridge_kafka_delivery_duration_seconds` | Measurable for successful Kafka acknowledgements; failed attempts are counted by `errors_total`, not added to the latency histogram. |
| Bridge DLQ ratio | `dealiot_bridge_dlq_total / dealiot_bridge_forwarded_total` | Measurable for validation performed by the bridge. |
| DEALData consumer health | `dealdata_consumer_ready`, assignment/database gauges and last successful poll timestamp | Measurable per GPS and sensor consumer. Readiness requires a healthy recent Kafka poll and a successful database check. A healthy standby without a partition remains ready during rollouts; `kafka_assigned` separately measures active consumption capacity. Liveness remains process-local. |
| DEALData outcomes | `dealdata_consumer_records_total{result=...}`, commit, poll and database error counters | Measurable per consumer service with bounded labels. A post-Kafka rejection is reported separately; the current consumer does not prove that such a record reached `dlq.events`. |
| First-persistence freshness | `dealdata_consumer_event_age_seconds` | Partial. It measures valid source timestamp to successful first insert. Duplicates are excluded and invalid/future clocks increment `invalid_event_clock_total`. Events that never reach a consumer remain invisible without a synthetic/correlated event SLI. |
| DEALData API reachability | Prometheus `up` plus the constant `dealdata_*_service_info` gauges | Reachability only; metrics scrapes never scan event tables and the APIs do not yet export request RED histograms. |
| Runtime management health | Controller `up` and Kubernetes-ready gauge; worker heartbeat/database readiness; durable queue depth, oldest age and stale-lease gauges | Operational coverage for controller/worker loss and stalled or growing operation queues. These gauges measure the control plane, not application request availability. |
| Kafka consumer-group lag | None in these application images | Missing. Install a Kafka exporter with committed offsets, high-water marks and lag age before GO. |
| Database/certificate/backup/revision health | None in these application images | Missing. Provider exporters and evidence collectors are mandatory before GO. |
| End-to-end synthetic | Invocation-scoped MQTT TLS publisher plus authenticated public GPS/sensor queries | Deployment-gate coverage. Every run has fresh Job, device and message identities; it traverses MQTT, the bridge, Kafka, consumers, PostgreSQL, APISIX and OIDC and proves replay idempotence. It is not yet a continuously scheduled SLI or Prometheus time series. |
| Rollback time | Retained deployment and incident evidence | Missing as a continuously measured SLI; every environment must time a previous-signed-release exercise. |

The missing and partial rows are production blockers for the corresponding objective; a green
PrometheusRule set is not evidence that an uninstrumented path is healthy. Before GO, the platform
must add provider-specific monitors for Kafka lag, PostgreSQL saturation, certificate expiry,
backup/restore age and deployment revision, plus schedule the shipped invocation-scoped synthetic
continuously if it is to back an SLI. Synthetic traffic must have bounded labels and remain
excluded from customer SLIs.

Metrics must carry bounded `service`, `environment`, `route`, `result`, and `revision` labels.
Device IDs, event IDs, MQTT topics containing identifiers, raw URLs, and other unbounded values must
not be metric labels. Those values belong in correlated logs and traces.

Availability is calculated as successful eligible events divided by all eligible events. A request
or event is unsuccessful when ArchiDEAL rejects, loses, times out, or returns a server error for
otherwise valid input. Client validation failures and policy-authorized rejections are reported but
excluded from availability only when their classification is tested and auditable.

Freshness starts at the source event timestamp and ends at the successful first DEALData insert.
The in-process measurement occurs immediately after the database operation returns and before the
Kafka offset commit; commit failures have their own critical alert. Clock skew is monitored:
missing, invalid, timezone-naive and future timestamps increment a counter and are not silently
inserted into the histogram.

## Prometheus Operator and routing contract

Prometheus must watch the `archideal` namespace and select `ServiceMonitor`, `PodMonitor` and
`PrometheusRule` objects labelled `monitoring.archideal.io/enabled: "true"`. Its pods run in the
configured `MONITORING_NAMESPACE`, which is the only external namespace allowed by NetworkPolicy
to reach dedicated metrics ports, including the TLS runtime-controller port 8081 and runtime-worker
port 9102. Scraping from another namespace will fail closed.

The monitors assign stable `job` labels for APISIX, oauth2-proxy, the runtime controller/worker,
the bridge, DEALData APIs and DEALData consumers. Do not build alerts from generated ServiceMonitor job names. Alertmanager must
route `critical` to the named on-call owner and `warning` to that owner's ticket channel, inhibit
symptom alerts under a declared parent outage, and send a tested dead-man notification. The
runbook for every included rule is `docs/runbooks/observability-alerts.md`.

## Error budgets and alerts

For a 99.9% objective, the 30-day error budget is 0.1% of eligible events or time. The deployed edge
rules use recording rules and multi-window evaluation:

- a fast-burn page at a 7.2% error ratio in both the five-minute and one-hour windows, equivalent to
  consuming 10% of a 30-day 99.9% budget in one hour;
- a slow-burn ticket at a 0.75% error ratio in both the one-hour and 24-hour windows, equivalent to
  consuming 25% of that budget in 24 hours;
- immediate pages for complete ingestion loss, sustained data loss, signature-policy bypass,
  restore failure, and exhausted database or Kafka capacity.

The edge burn alerts require at least one eligible request per minute to avoid low-volume noise.
Ratio alerts for DLQ and consumer rejection require at least 100 records in ten minutes. These
volume gates do not waive the SLO calculation; low-volume errors remain in the 30-day report.

Every alert includes or preserves `service`, `severity`, `owner`, `slo`, and `runbook_url`. Rules
for complete bridge/consumer/edge/runtime target loss, runtime queue stalls, commit/database
failure, event-clock failure, DLQ or rejection ratio, Kafka acknowledgement latency, freshness and APISIX/etcd reachability are included.
Provider capacity, backup, signature-policy and restore alerts remain external requirements and
must be tested in staging with Alertmanager routing, inhibition and a dead-man notification.

## Release and production acceptance

A production promotion is blocked unless all of the following evidence refers to the exact image
digests in the signed release manifest:

1. component tests and the cross-architecture smoke test pass;
2. all production manifests render, validate, and contain only digest-pinned images;
3. image vulnerability scans contain no unapproved High or Critical finding;
4. image signatures, provenance, and SBOM attestations verify against the protected ArchiDEAL
   release workflow identity;
5. end-to-end, authorization, invalid-event/DLQ, restart, broker-failure, and database-failure tests
   pass with no loss and bounded duplicates;
6. restore drills meet the approved RPO and RTO for every persistent database and event store;
7. load and soak tests remain within the targets above and no critical alert is active;
8. the previous signed release manifest and a database-compatible rollback procedure are available.

An exhausted error budget blocks ordinary releases. An emergency override requires an incident or
change record, named approver, expiry time, and a follow-up action; the override itself must be
observable and retained with the release evidence.
