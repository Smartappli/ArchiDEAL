# Scalable Production Architecture Audit

This audit records the production-readiness iterations applied to DEALIoT.

## Objective

Prepare the repository for a scalable production deployment while preserving operational compatibility. The audit prioritizes changes that are verifiable through tests, renders, and CI workflows.

## Iteration 1: Runtime Dependency Security

Findings:

- Runtime producers and processors needed one consistent Kafka security contract.
- MQTT production defaults needed TLS rather than plaintext port `1883`.
- Management Console API routes needed an authentication boundary.

Corrections:

- Added Kafka `SASL_SSL` support to the MQTT-Kafka bridge, media backfill, and Flink job configuration.
- Added MQTT TLS configuration to the bridge.
- Added Management Console bearer-token enforcement for `/api/*` and mutation routes while keeping `/healthz` public.
- Added unit tests for Kafka security, MQTT TLS, and Management Console authorization.

## Iteration 2: Kubernetes Production Scaling

Findings:

- Production manifests needed explicit HPA/PDB coverage for scalable workloads.
- Runtime probes and disruption controls needed to be enforced by tests.
- Production overlay needed to reject placeholders during CI render.

Corrections:

- Added HPA for bridge, Flink TaskManager, Airflow worker, and Management Console.
- Added PDBs for application tiers.
- Added topology spread constraints for horizontally scaled workloads.
- Added probes and metrics exposure where appropriate.
- Added CI checks that reject mutable tags, placeholder tags, example endpoints, and example secrets in rendered production manifests.

## Iteration 3: Pod Security And Workload Hardening

Findings:

- Several Kubernetes workloads did not explicitly declare the full Pod Security `restricted` intent.
- CI smoke namespace did not enforce the same admission baseline.
- Some workload containers did not have a test preventing missing resources or security context regressions.

Corrections:

- Added Pod Security `restricted` labels to runtime namespaces.
- Added `seccompProfile: RuntimeDefault` to workload pod specs.
- Added `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, and `runAsNonRoot: true` to workload containers.
- Added liveness probing for Management Console.
- Added deployment tests that validate workload security context, resources, service-account token automount, and namespace Pod Security labels.

## Iteration 4: CI/CD Contract Hardening

Findings:

- Production Swarm render validation used local placeholder image values for some runtime images.
- Smoke image validation and production image contract validation were coupled through one environment variable.

Corrections:

- Split the smoke bridge image (`DEALIOT_SMOKE_BRIDGE_IMAGE`) from production image variables.
- Swarm production render now uses immutable `sha-${{ github.sha }}` images.
- Swarm render fails if placeholder or mutable production image tags are rendered.
- Deployment tests assert the workflow separation and render guardrail.

## Iteration 5: Documentation And Wiki Source

Findings:

- The README had grown into a mixed audit log, runbook, and architecture note.
- A GitHub Wiki was requested, but `https://github.com/Smartappli/DEALIoT.wiki.git` was not accessible from the local environment.

Corrections:

- Rewrote the README as a professional project entry point.
- Added versioned wiki source pages under `docs/wiki` so documentation can be published as soon as the GitHub Wiki is enabled.
- Added this audit record as a durable architecture decision trail.

## Iteration 6: Delivery Semantics And Truthful Health

Findings:

- The Rust normalizer disabled Kafka auto-commit and stored offsets locally, but never committed
  them to Kafka. A restart could therefore replay an unbounded range of already processed records.
- The Rust health endpoints always returned success, even while MQTT or Kafka was unavailable.
- MQTT messages were acknowledged by the client event loop before the downstream Kafka guarantee
  was explicit, leaving an avoidable loss window.
- Random bridge client IDs prevented reliable MQTT session recovery after reconnects.

Corrections:

- The normalizer now commits each source message synchronously after all required output records
  are acknowledged.
- Both Rust producers enable Kafka idempotence.
- The bridge uses manual MQTT acknowledgements after Kafka delivery and persistent sessions with a
  stable client ID.
- Kubernetes runs the bridge as a StatefulSet; Swarm derives the client ID from the stable task
  slot. Bridge scale-down is deliberately rate-limited.
- `/healthz` remains a liveness endpoint, while `/readyz` reflects dependency readiness.
- Deployment tests enforce the delivery and workload identity contract.

## Rust Runtime Status

The production MQTT-Kafka bridge, stream normalizer, shared event contracts, and WildFi decoder
runner are Rust workspace members and are built and tested in CI. The Python bridge module remains
only as a compatibility reference for existing unit fixtures; production images execute the Rust
binary.

## Iteration 7: Job-Aware Flink Scaling

Findings:

- The production overlay attached a CPU-based HPA directly to standalone Flink TaskManager pods.
- Adding TaskManagers does not change the parallelism of an already submitted standalone job, and
  removing them can force task recovery without a coordinated rescale or savepoint.

Corrections:

- Removed the TaskManager HPA and retained the explicit three-replica production floor.
- Documented savepoint-driven manual capacity changes as the current operating model.
- Kept Flink Kubernetes Operator adoption as the prerequisite for automatic, job-aware scaling.

## Current Go-Live Readiness

## Iteration 8: Processing Ownership And Operator Lifecycle

- Accepted Flink as the sole authoritative owner of `state.latest` in production.
- Split Flink and Rust into mutually exclusive Kustomize packages.
- Migrated production to Flink Kubernetes Operator application mode with Kubernetes HA metadata,
  S3 checkpoints/savepoints, savepoint upgrades, and job-aware autoscaling.
- Aligned the Flink JVM image, PyFlink wheel, driver/plugins, and Kafka connector on the operator
  1.15 validated Flink 2.2 line.
- Disabled state output by default in the stateless Rust alternative.

## Iteration 9: Contracts, Identity, And Registry Governance

- Added deterministic SHA-256 event IDs, schema versions, and occurrence timestamps at ingestion.
- Added shared cross-language envelope fixtures and validation in Python and Rust.
- Made Apicurio schemas canonical, enabled full validity and backward-transitive compatibility, and
  documented a provider-neutral Kafka topic/principal contract.

## Iteration 10: Identity And Supply Chain

- Added OIDC token introspection and read/write role mapping to Management Console.
- Enabled OIDC and role/owner authorization for Apicurio production.
- Added keyless Cosign signing to the image workflow and a Kyverno admission policy for the
  protected workflow identity.
- Added an External Secrets contract so literal production secrets are not required.

## Iteration 11: Runtime Evidence And SLOs

- Added dependency-aware startup/readiness, SIGTERM draining, and Prometheus metrics to Rust
  runtimes.
- Replaced sleeping smoke placeholders with real MQTT publication and Kafka consumption in both
  kind and Swarm.
- Added PodMonitor, alert-rule, SLO, error-budget, and ownership contracts.

## Iteration 12: Recovery Evidence

- Added an automated broker/bridge fault-injection drill that checks no loss and bounded duplicates.
- Added an Airflow PostgreSQL logical backup/isolated restore drill with table-count verification,
  an RTO gate, Kafka topic recovery checks, and evidence publication.
- Integrated both drills into the E2E workflow.

Ready for staging:

- Processing ownership, event identity, delivery semantics, restore verification, and fault
  injection are executable contracts.
- Kubernetes and Swarm perform actual MQTT-to-Kafka flow tests.
- OIDC, immutable signed images, optional admission verification, default deny, and secret-manager
  integration are represented in deployment assets.

Environment-specific before production:

- Replace example endpoints/CIDRs and bind the OIDC roles to the real identity provider.
- Install and configure External Secrets Operator, Kyverno, Prometheus Operator, and Flink Operator.
- Patch the remote secret store and signer identity, then enable the optional platform components.
- Run the drills against staging-managed dependencies and calibrate SLO thresholds from observed
  telemetry.

## Residual Finding

The legacy Python bridge remains as a compatibility fixture while Rust defines the production
ingestion behavior. Retiring those fixtures is a cleanup task and no longer blocks the production
architecture.
