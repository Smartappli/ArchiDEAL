# ArchiDEAL Kubernetes production baseline

This directory defines the unified Kubernetes target for ArchiDEAL. Docker Compose remains the
development and integration target; it is not an input to this deployment.

The baseline deploys only stateless application workloads. Kafka, MQTT, PostgreSQL, Valkey and
etcd are external HA services. Their minimum service-level contract is rendered in the production
overlay as `archideal-platform-contract`.

## Required controllers

- ingress-nginx controllers in the supplied namespace, with the standard
  `app.kubernetes.io/name=ingress-nginx` and
  `app.kubernetes.io/component=controller` Pod labels;
- cert-manager and the configured `ClusterIssuer`;
- External Secrets Operator and the configured `ClusterSecretStore`;
- a metrics adapter for the included CPU HPAs.
- Prometheus Operator CRDs and a Prometheus instance configured to select the included
  `ServiceMonitor`, `PodMonitor` and `PrometheusRule` objects.

The Prometheus instance must watch the `archideal` namespace and select objects carrying
`monitoring.archideal.io/enabled: "true"`. Its pods must run in `MONITORING_NAMESPACE`; the
NetworkPolicies permit only pods labelled `monitoring.archideal.io/scraper: "true"` to scrape the
declared dedicated metrics ports. Label the Prometheus Pod template, not arbitrary namespace
workloads, and restrict that label through admission policy to the monitoring platform team.
Alertmanager must route the rule severities to the owners in
`docs/slo.md`; installing the CRDs without those selectors and routes does not make monitoring
operational.

The namespace enforces the Kubernetes `restricted` Pod Security Standard. The release images must
therefore run as non-root and must be compatible with a read-only root filesystem where declared.

## Render

Copy `values.example.yaml` outside the repository and replace every example value. Production
promotion must use the ordered deployer and an explicit kubectl context:

Set `RELEASE_ID` to the exact `releaseId` from the selected signed release manifest. The verifier
rejects a hand-written or reused ID even when all ten image digests match.

```bash
deploy/kubernetes/deploy-production.sh \
  --values /secure/config/archideal-production-values.yaml \
  --context archideal-production \
  --smoke-token-file /secure/tokens/archideal-smoke.jwt \
  --release-manifest /secure/releases/release-1/release-manifest.json \
  --release-bundle /secure/releases/release-1/release-manifest.sigstore.json \
  --release-evidence-dir /secure/releases/release-1
```

Before rendering or contacting Kubernetes, the deployer verifies the signed release bundle, every
evidence hash and content contract, the exact ten values-file references and the eight first-party
image signatures/attestations. There is no promotion bypass; Cosign and registry access are
required. See `docs/supply-chain.md` for the reviewed immutable upstream pin file and the GitHub
Release download procedure. Upstream authorization additionally requires APISIX
3.14.1+ and oauth2-proxy 7.15.3+, a registry-resolved source-tag-to-digest proof, and successful
runtime compatibility checks against the exact promoted digests.

The deployer then renders and validates the complete bundle and promotes it in six phases:
namespace/admission, ExternalSecret plus private-DNS preflight then policy, Kafka topology preflight plus migrations,
application rollouts plus Prometheus monitoring rules, APISIX route bootstrap, and finally the
public TLS Ingress. Before the namespace is mutated, a read-only platform preflight requires the
Ingress/monitoring namespaces, an IngressClass implemented by `k8s.io/ingress-nginx`, Ready
ClusterIssuer and ClusterSecretStore, Available metrics APIService, and External Secrets,
cert-manager and Prometheus Operator CRDs. At least one ingress-nginx controller in
`INGRESS_NAMESPACE` must be Running and Ready, serve the configured class without `hostNetwork`,
and every one of its Pod IPs must be inside `INGRESS_PROXY_CIDR`. The same standard controller
labels are the only cross-namespace peers accepted by the oauth2-proxy ingress NetworkPolicy.
The platform preflight also requires a Ready labelled scraper and schedulable Linux/amd64 nodes in
three labelled zones. After the registry pull Secret is Ready, a fresh invocation-scoped Job uses
cluster DNS to resolve every Kafka, MQTT, metadata PostgreSQL, data PostgreSQL, DEALIoT registry
PostgreSQL, Valkey and etcd endpoint. It rejects an empty answer or any returned IPv4/IPv6 address
outside that dependency's configured CIDR before any NetworkPolicy is changed. The Job receives
only non-secret endpoint and CIDR values; no runtime credential is read or logged. A fresh
invocation-scoped Kafka preflight
then requires all seven ingestion/DLQ topics to
have at least three partitions, replication factor 3, two current in-sync replicas,
`min.insync.replicas >= 2` and disabled unclean leader election. It stops on the first failed
readiness gate. Do not use a monolithic
`kubectl apply` for production because Kubernetes does not order these resources.
Every long-running controller deliberately omits `spec.replicas`: its HPA is the sole
server-side-apply owner of scale, so an upgrade preserves the current live capacity. The HPA sets
the initial production minimum immediately after first creation. The deployer stamps the runtime
revision before applying a controller and then promotes controllers one at a time, so one release
causes exactly one rollout per controller and never restarts the entire architecture concurrently.

Promotion completes only after the full public-edge smoke gate succeeds. It verifies OIDC access
to the DEALHost repositories API, rejection of the same anonymous request without following a
redirect, and HTTP 401 for an unsigned anonymous GitHub webhook. It also reads the
`dealdata-ingest-token` key from the already-Ready runtime Secret into a temporary mode-0600 file,
creates and replays unique GPS and sensor events, and requires one persisted record per layer. The
temporary credential is removed by the deployer's exit trap and is never passed as a command-line
value. A separate invocation-scoped Job uses a dedicated publish-only MQTT credential, publishes
GPS and sensor data over TLS, replays GPS, and the same authenticated public check requires exactly
one row per layer after the bridge, Kafka and consumers. Every deploy attempt gets new Job names
and a new device/message identity, even when `RELEASE_ID` is reused for a retry or rollback; a
previously Complete private-DNS, Kafka, APISIX bootstrap or synthetic Job, and no prior database
rows, can therefore satisfy the gate.

Those seven topics are the minimum runtime dependency of the workloads deployed here. They do not
replace the extended platform catalog in `components/DEALIoT/deploy/kafka/topics.yaml`, which the
Kafka platform automation must reconcile (including ACLs, retention and optional processing
topics) before the corresponding DEALIoT capabilities are enabled.
On an upgrade where `ingress/archideal` already exists, the deployer also requires
`--approve-live-upgrade`. Supply it only after verifying that database changes use the
expand/contract pattern and remain compatible with the release still receiving traffic. Before any
mutation it proves that all eleven controllers are fully observed and available, and that their
templates plus every Ready serving Pod use the same release as the Ingress.

After the first mutation, every non-zero exit activates the promotion fence: the deployer deletes
and waits for `ingress/archideal`, annotates the Namespace with the failed target and validated
previous release when available, preserves its original exit code, and prints an explicit
`production-rollback` command. A release is marked `succeeded` on the Namespace and Ingress only
after the public smoke and a second eleven-controller coherence proof. Rollback is never an Ingress
reapply; `rollback-production.sh` accepts only the recorded previous release and reruns signed
verification, the full ordered promotion and fresh one-shot Jobs without reversing database
migrations. Run that wrapper from a clean worktree at the previous manifest's signed revision; the
supply-chain gate rejects the failed release's checkout or any dirty source tree.

For an offline render used by CI or change review, call `render.py` directly and run
`kubectl kustomize` against the rendered production overlay. A directory can be replaced with
`--force` only when it contains the renderer's ownership marker.

The renderer rejects missing or unknown values, mutable or non-allowlisted image references,
all-zero image digests, `.invalid` endpoints, wildcard hosts, non-RFC1918 dependency ranges,
overlapping dependency/Pod ranges and unresolved placeholders. `RELEASE_ID` is limited to 39
DNS-label characters so every static migration/preflight Job name remains within Kubernetes'
63-character limit. Kafka, MQTT, metadata PostgreSQL, data PostgreSQL, DEALIoT registry PostgreSQL,
Valkey and etcd each require a distinct CIDR (a `/32` is valid) so egress policy is scoped by both
destination and port. Public OIDC, GitHub and OpenTelemetry ranges must be
change-reviewed and no broader than `/20` for IPv4 or `/48` for IPv6; the read-only platform
preflight resolves those public endpoints from the promotion host, while the invocation-scoped Job
validates private dependency answers from inside the cluster. Both reject addresses outside their
approved range. `--allow-example` exists only for CI syntax validation and
must never be used for a deployment.

No secret value belongs in the values file. `ExternalSecret` reads all credentials and CA
certificates from the configured `ClusterSecretStore` below `SECRET_PREFIX`.
The runtime `ExternalSecret` and its target are named
`archideal-runtime-secrets-${RELEASE_ID}` and use `refreshPolicy: CreatedOnce`. Every workload and
release Job references that exact target, so a reconciliation cannot change credentials beneath a
running or rolling release. After verifying its target name, release label and owner, the ordered
deployer sets the native Kubernetes Secret `immutable: true` and confirms the API persisted that
guard before any migration or rollout. Retrying the same release ID reuses its existing Ready,
immutable Secret; it does not force a refresh. Rotate credentials only by staging overlap in the external systems and
promoting a new release ID, then retain the previous release Secret through the rollback window.
After that window, remove the old ExternalSecret and owned Secret under the environment's approved
secret-retention procedure. The separate registry pull ExternalSecret remains periodic so a pull
credential can rotate without changing application runtime identity.
The secret store must include `ghcr/dockerconfigjson`, containing a read-only GHCR pull credential;
all ServiceAccounts use the resulting `kubernetes.io/dockerconfigjson` Secret. It must also contain
the APISIX etcd CA and client key pair. `valkey/tls-url` must be a `rediss://` URL for
`VALKEY_HOST` on port 6380, whose certificate is valid for that hostname. Before migrations or
application rollouts, the ordered deployer validates the Secret in a non-logging pipe and rejects
`redis://`, a different hostname or a different port. DEALHost production settings repeat the
scheme check, and an init container applies the same fail-closed check before oauth2-proxy starts.
The development Compose profile may continue to use plaintext `redis://` only on its private local
network.

Kafka credentials are deliberately separate: `kafka/producer-*` is used only by the MQTT bridge,
`kafka/consumer-*` by the DEALData consumers and topology preflight, and `kafka/console-*` by the
operator console. Configure matching least-privilege Kafka ACLs; do not point these entries at one
shared principal.

MQTT credentials are split as well: `mqtt/username` and `mqtt/password` belong to the long-running
bridge subscriber, while `mqtt/smoke-username` and `mqtt/smoke-password` belong only to the bounded
production synthetic. Give the smoke principal publish-only ACLs for the invocation-scoped
`devices/archideal-smoke-*` synthetic topics; it must not subscribe or administer the broker.

PostgreSQL credentials are also split. Provision roles `dealdata_core`, `dealdata_gps` and
`dealdata_sensor`, each restricted to its namesake database, and store their passwords at
`postgres/dealdata-core-password`, `postgres/dealdata-gps-password` and
`postgres/dealdata-sensor-password` below `SECRET_PREFIX`. No DEALData layer may own or connect
with another layer's role. Provision the separate `dealiot_registry` database with two login
roles on the endpoint configured by `POSTGRES_DEALIOT_REGISTRY_HOST`:
`dealiot_registry_migrator` owns the `public` schema (directly or through role membership), has
`USAGE, CREATE`, and owns schema objects; `dealiot_registry_app` is the runtime role.
Store their distinct passwords at `postgres/dealiot-registry-migration-password` and
`postgres/dealiot-registry-password`. The runtime role must not own the database or inherit from
the migrator. Its server certificate must be valid for that hostname and chain to
`pki/postgres-ca.crt`; both roles use `verify-full` and can reach only
`POSTGRES_DEALIOT_REGISTRY_EGRESS_CIDR` on TCP/5432.

The release Job `dealiot-registry-mig-${RELEASE_ID}` runs
`python -m management_console.migrate` with the same digest-pinned console image and the dedicated
migrator credential before any application rollout. Migrations take a PostgreSQL advisory
transaction lock, preflight the migrator's owner/`USAGE`/`CREATE` rights before DDL, record
checksums, revoke all schema/table privileges from both `PUBLIC` and the runtime role, and grant
only schema `USAGE`, device `SELECT`/`INSERT`/`UPDATE`, and migration-table `SELECT`. Retirement is
an `UPDATE`; effective/inherited `CREATE`, `DELETE`, `TRUNCATE` and ownership make the job and
production readiness fail closed. An already-applied file whose contents changed fails the release.
Registry readiness accepts only an ordered suffix of newer migrations to support expand/contract
rollback; do not remove columns, tables or compatible constraints until the rollback window is
closed. Do not run this command from serving Pods or in parallel with the ordered deployer. The
registry database stores device metadata only: MQTT credentials and ACLs remain owned by the
broker/secret manager.

## Exposure and tenancy

The only public Service selected by the Ingress is `oauth2-proxy`. It authenticates browser
requests with OIDC Authorization Code + PKCE and bearer smoke/API requests against the configured
issuer and audience; both paths require membership in `OIDC_ALLOWED_GROUP`. There are no public
health bypass routes. The sole authentication exception is the exact `POST`
`/dealhost/api/gateway/github/webhook/` callback: DEALHost validates the GitHub HMAC signature,
allowed repository, event type and delivery identifier with the secret-manager webhook secret.
No other method or path bypasses OIDC. HA sessions are stored in the external Valkey service using
the secret-managed TLS URL. APISIX proxy traffic is accepted only from oauth2-proxy; its Admin API
is accepted only from the route bootstrap Job and DEALHost.

`OIDC_ALLOWED_GROUP` and `OIDC_ADMIN_GROUP` must be different identity-provider groups. Edge
admission and read-only DEALHost/DEALIoT operations require the former; DEALHost administration and
DEALIoT registry creation, update and retirement require the latter. Because oauth2-proxy enforces
edge admission first, an administrator must belong to both groups. Do not make the admin group an
alias of, or automatically grant it to, every admitted reader.

For browser sessions and directly supplied bearer tokens, oauth2-proxy validates issuer, audience
and admission-group membership, emits the validated access token only in
`X-Forwarded-Access-Token`, and does not trust or forward the caller's original `Authorization`
header. The protected APISIX DEALHost and DEALIoT routes replace that header with
`Bearer $http_x_forwarded_access_token`; each application then introspects the forwarded token and
enforces its read/admin role mapping, while APISIX removes the raw forwarded-token header. All
non-introspecting upstreams remove both `Authorization` and `X-Forwarded-Access-Token`. The
renderer checks that policy on every bootstrap route and also proves that the exact dynamic-route
host/port ceiling matches deployed Services and `apisix-egress`; no client-supplied identity header
is accepted as an authorization source or leaked to another module.

This is an operator-only, single-tenant edge. Multi-tenant or anonymous/public exposure is not
supported until DEALHost, DEALData and DEALIoT implement and enforce a shared tenant identity and
resource-level authorization model.

## Deployment order

External Secrets must become Ready before migration Jobs run. Migration Jobs include the release
ID in their names, fail closed, and complete before any application workload is updated. The
Ingress is promoted only after every Deployment is Ready and the APISIX bootstrap Job completes.
Do not reuse a release ID with different images or migrations.

The APISIX bootstrap owns the reserved `archideal-` route-ID prefix. It upserts the desired base
routes and deletes obsolete routes in that namespace after all upserts succeed. DEALHost dynamic
routes use the separate `module-` prefix and are preserved. They can never claim a bootstrap or
manifest path, including an exact match. No audited `module-` route delete exists yet, so DEALHost
blocks disable/delete/rename/retarget mutations for every routable module. The current module
manifests remain `production_ready=false`; consequently the supported production baseline uses
only bootstrap routes. Enabling a dynamic production route requires both an explicit manifest
review (`production_ready=true`) and completion of the revocation/audit prerequisite.

Every PodTemplate carries `archideal.io/release`. During promotion the deployer also stamps a
runtime revision derived from the live runtime Secret and ConfigMaps, so a same-image secret or
configuration rotation causes a rollout. Rotate the secret-manager value, use a new release ID,
rerun the deployer, verify the smoke test, and only then revoke the previous credential.

See `docs/runbooks/backup-restore.md` and `docs/runbooks/disaster-recovery.md` before promoting a
release. The deployed metrics, known coverage gaps, Prometheus selector contract and alert actions
are documented in `docs/slo.md` and `docs/runbooks/observability-alerts.md`.
