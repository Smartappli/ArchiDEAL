# Deployment guide

## Development and integration

Requirements:

- Docker Engine and Docker Compose v2;
- Python 3.12 or newer for validation and smoke checks;
- OpenSSL for local credential generation;
- sufficient disk, memory and build time for Rust, Node and three Python application images.

Create the ignored `.env` file once:

```bash
./scripts/bootstrap-env.sh
```

Review it, then validate and start the stack:

```bash
python scripts/validate-monorepo.py
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
./scripts/smoke-architecture.sh
```

The public entry point is `http://127.0.0.1:8080` by default. No database, Kafka, MQTT, component
HTTP port or APISIX Admin port is exposed on the host.

Useful diagnostics:

```bash
docker compose ps --all
docker compose logs --timestamps apisix apisix-bootstrap
docker compose logs --timestamps mqtt-kafka-bridge dealdata-gps-consumer dealdata-sensor-consumer
docker compose down --remove-orphans
```

The compact root Compose profile explicitly requires VerneMQ, `mqtt-kafka-bridge` and Kafka.
DEALIoT `/api/health` summarizes those required dependencies; full-platform services such as
Airflow, Flink, Apicurio and Prometheus are excluded unless an operator explicitly adds them to the
optional or required scope. A healthy compact response and a successful MQTT → Kafka → DEALData →
APISIX smoke test validate development or staging integration only. They do not certify
production readiness or replace the signed-image, infrastructure, admission, HA, backup, TLS and
authenticated Kubernetes promotion prerequisites below.

## Release discipline

Every ArchiDEAL release should pin:

- the monorepo commit;
- container image digests;
- Kafka, APISIX, etcd, PostgreSQL, Flink, Beam and Apicurio versions;
- schema versions and topic configuration;
- database migration state.

Run component tests, root validation and the end-to-end smoke test before creating a release tag.
Nested `.github/workflows` files under `components/` are retained as provenance but are not executed
by GitHub; root workflows are authoritative.

The authoritative `Release images` workflow assembles a signed record for all eight first-party
images and the two approved upstream images. Its reviewed immutable upstream pins, fail-fast
configuration gate, evidence contract and retention procedure are described in
[supply-chain.md](supply-chain.md). Do not construct a production release manifest by hand or
replace a reviewed digest with a tag.

## Production deployment

Production is Kubernetes-only and the supported image profile is Linux/amd64. Every Pod is pinned
to that architecture. The application, Ingress and monitoring namespaces must be distinct trust
boundaries. Dependency and Pod ranges must be non-overlapping RFC1918 networks; the trusted-proxy
range must also use RFC1918 addressing. Kafka, MQTT, the two PostgreSQL trust zones, Valkey and
etcd use separate destination CIDRs so one workload receives only the egress path it needs.

Install Git, Cosign, Python 3.12+ and kubectl on the promotion host. Copy
`deploy/kubernetes/values.example.yaml` outside the repository, replace every example endpoint, and
copy its `releaseId` into `RELEASE_ID` and its ten image references exactly from one signed GitHub
Release manifest. Download and extract
that release's `release-evidence.tar.gz` as shown in [supply-chain.md](supply-chain.md), then use the
ordered deployer. It verifies the Sigstore release bundle, evidence hashes/content, repository
allowlist, eight first-party signatures and attestations before it renders or calls kubectl. It then
performs client-side and server-side admission checks, waits for secrets and the Kafka contract,
runs migrations, rolls out every controller, bootstraps APISIX, and only then promotes the public
Ingress and runs an authenticated smoke check:

Before the first promotion, label the actual Prometheus scraper Pods with
`monitoring.archideal.io/scraper=true`. The deployer requires at least one Ready scraper and Ready,
schedulable Linux/amd64 nodes across three `topology.kubernetes.io/zone` values before it mutates
the cluster. NetworkPolicies grant that labelled scraper only the dedicated metrics ports; the
DEALData application APIs remain reachable solely through APISIX.

The configured IngressClass must be served by ingress-nginx Pods in `INGRESS_NAMESPACE`. Their Pod
templates must retain the standard `app.kubernetes.io/name=ingress-nginx` and
`app.kubernetes.io/component=controller` labels, and their effective `--controller-class` and
`--ingress-class` arguments must match the configured IngressClass. Before any cluster mutation,
the deployer requires at least one such Running/Ready non-`hostNetwork` controller and verifies
that every Ready matching controller Pod IP is contained in `INGRESS_PROXY_CIDR`. oauth2-proxy
accepts ingress only from Pods satisfying that same namespace-and-label identity; choose the proxy
CIDR to cover those controller Pod IPs, not a broad node or VPC range.

Before it applies or updates any NetworkPolicy, the deployer launches a new invocation-scoped DNS
preflight from the `archideal` namespace. Every address returned inside the cluster for all Kafka
brokers, MQTT, metadata PostgreSQL, data PostgreSQL, the dedicated DEALIoT registry PostgreSQL,
Valkey and all three etcd endpoints must be inside that dependency's dedicated CIDR. Empty, mixed
in-range/out-of-range and uncovered dual-stack answers stop promotion. This Job receives no Secret
or service-account token and logs no resolved address. This protects both the first deployment and
upgrades from installing policies that do not match the cluster's actual DNS view.

Before the first release, provision the `dealiot_registry` database at
`POSTGRES_DEALIOT_REGISTRY_HOST` with distinct `dealiot_registry_migrator` and
`dealiot_registry_app` login roles. Store their passwords at
`SECRET_PREFIX/postgres/dealiot-registry-migration-password` and
`SECRET_PREFIX/postgres/dealiot-registry-password`; the runtime role must not own schema objects or
inherit from the migrator. The migrator must own (directly or through role membership) the
`public` schema and have `USAGE, CREATE`; the migration Job checks this before issuing DDL because
revoking the ambient `PUBLIC` creation grant requires owner rights. Make the TLS certificate valid
for the database DNS name. The runtime ConfigMap fixes `sslmode=verify-full` and mounts
`SECRET_PREFIX/pki/postgres-ca.crt`; no password belongs in the values file. Phase 3 runs the
release-scoped migration Job with the DDL credential, revokes all schema/table privileges from
`PUBLIC` and the runtime role, then grants the runtime role only schema `USAGE`, device
`SELECT`/`INSERT`/`UPDATE`, and migration-table `SELECT`. Retirement is an `UPDATE`; the runtime
role must have no effective or inherited `DELETE`, `TRUNCATE`, object ownership or schema `CREATE`.
The job verifies that post-grant contract before completing and waits with the other schema Jobs
before starting a console rollout. Readiness accepts only a strictly ordered suffix of newer
migrations so an expand/contract rollback remains possible; destructive schema contraction stays
blocked until the rollback window has closed.

Create separate IdP groups for `OIDC_ALLOWED_GROUP` and `OIDC_ADMIN_GROUP`. The first is the
oauth2-proxy admission group and grants read-only DEALHost/DEALIoT access; the second grants
DEALHost administration, DEALIoT writes, and DEALData scientific metadata/event administration
after introspection. An administrator needs both memberships because the edge rejects a principal
that lacks `OIDC_ALLOWED_GROUP`. The renderer refuses identical group values. Every introspecting
application reads authorization membership only from the pinned top-level `groups` claim; names
appearing in `scope`, `scp`, `roles` or `realm_access.roles` never grant read or administrative
access.

Direct API bearer tokens follow the same boundary as browser sessions: oauth2-proxy validates the
token and writes `X-Forwarded-Access-Token`, APISIX replaces `Authorization` on only the protected
DEALHost, DEALIoT, and three DEALData routes, and each application introspects that token before
applying its role checks. Those routes remove the raw `X-Forwarded-Access-Token` after the exchange.
DEALInterface and every other non-introspecting upstream explicitly remove both `Authorization`
and `X-Forwarded-Access-Token`; the original client header and edge token are never forwarded to
them. Provision the confidential DEALData introspection client below
`SECRET_PREFIX/dealdata/oidc-client-id` and `SECRET_PREFIX/dealdata/oidc-client-secret`; the same
release-scoped immutable Secret is projected into Core, GPS, and Sensor.

```bash
make production-deploy \
  PRODUCTION_VALUES=/secure/config/archideal-production-values.yaml \
  KUBE_CONTEXT=archideal-production \
  ARCHIDEAL_BEARER_TOKEN_FILE=/secure/runtime/archideal-token \
  PRODUCTION_RELEASE_MANIFEST=/secure/releases/release-1/release-manifest.json \
  PRODUCTION_RELEASE_BUNDLE=/secure/releases/release-1/release-manifest.sigstore.json \
  PRODUCTION_RELEASE_EVIDENCE_DIR=/secure/releases/release-1
```

Never deploy the production bundle with one monolithic `kubectl apply`: Jobs and serving workloads
would no longer be ordered. When an ArchiDEAL Ingress already exists, the deployer also requires
`APPROVE_LIVE_UPGRADE=1`; set it only after confirming that all migrations follow the
expand/contract pattern and remain compatible with the active release. Before its first mutation,
the deployer also requires all thirteen controller templates and every Ready serving Pod to carry one
unanimous `archideal.io/release`, matching the active Ingress. Mixed, unavailable or partially
observed releases fail before the cluster is changed.

Promotion is fail-closed after the first mutation. An `EXIT` fence preserves the original failure
code, deletes `ingress/archideal`, waits for its removal even when the failure happens during the
public smoke, and records `failed`, the attempted release and the validated previous release on the
`archideal` Namespace. It prints the exact `make production-rollback` shape to use with archived
artifacts. It never silently re-exposes the previous Pods: public traffic resumes only after the
previous signed release has passed the complete ordered deploy and fresh smoke gates. A successful
promotion revalidates all thirteen serving controllers, then records a coherent `succeeded` state on
both the Namespace and Ingress.

The renderer fails on mutable images, unapproved image repositories, example endpoints, incomplete
HA dependencies, non-HTTPS OIDC/etcd/telemetry endpoints, wildcard access groups and public
dependency CIDRs. It also requires the exact APISIX dynamic `host:port` ceiling to match the
non-interface bootstrap upstreams, deployed Services and per-upstream `apisix-egress` rules. Secret
values are never accepted by the values file; they are extracted from the configured
`ClusterSecretStore`.

The deployer runs the full production smoke gate with the short-lived OIDC bearer token stored in
the file above. After the runtime `ExternalSecret` is Ready, it copies
`dealdata-ingest-token` into a mode-0600 temporary file and removes it through the deployer's
cleanup trap. The gate proves the authenticated DEALHost business API is reachable, anonymous
access is rejected without following a login redirect, and an unsigned anonymous GitHub webhook
is rejected with HTTP 401 by DEALHost. With the same short-lived administrator identity, it creates
a registry device, applies a conditional update, proves a stale ETag returns `412`, retires the
device and verifies it is no longer listed. It then creates one unique GPS event and one unique
sensor event through the public edge, replays both, and requires HTTP 201 then HTTP 200 with exactly
one stored event per layer. The smoke identity must therefore belong to both the edge admission and
admin groups; a separate negative read-only token test remains required evidence for production GO.

The final gate also runs an invocation-scoped MQTT TLS synthetic with the dedicated
`mqtt/smoke-username` and `mqtt/smoke-password` secrets. This broker account must have
publish-only ACLs for the `devices/archideal-smoke-*` GPS and sensor topics, without subscribe or
administrative rights. The public verification then waits for exactly one GPS and one sensor row
after MQTT, the Rust bridge, Kafka and both DEALData consumers; the GPS message is published twice
to prove end-to-end idempotence. Each deploy invocation specializes the private-DNS preflight,
Kafka contract preflight, APISIX bootstrap and MQTT synthetic templates with fresh Kubernetes Job
names. It also derives a fresh MQTT device and message identity, so retrying or rolling back with
the same `RELEASE_ID` cannot reuse a Complete Job or database rows from an earlier gate.

The same full gate can be repeated independently against the active release. The command creates a
new MQTT Job, verifies MQTT -> bridge -> Kafka -> consumers -> PostgreSQL through authenticated
OIDC queries, and also repeats the direct API idempotence checks. Both credentials must be supplied
as file paths; never put their values on the command line:

```bash
make production-smoke \
  PRODUCTION_VALUES=/secure/runtime/production-values.yaml \
  KUBE_CONTEXT=production-eu \
  ARCHIDEAL_BEARER_TOKEN_FILE=/secure/runtime/archideal-token \
  ARCHIDEAL_INGEST_TOKEN_FILE=/secure/runtime/dealdata-ingest-token
```

To roll back, select the artifacts of the `archideal.io/previous-release` recorded by the failed or
last successful promotion. Create a clean, detached source worktree at that manifest's signed Git
revision—the verifier rejects a different or dirty checkout. Review that the existing expanded
schema remains compatible with that application release, then run the target release's wrapper:

```bash
make -C /secure/releases/release-previous/source production-rollback \
  KUBE_CONTEXT=production-eu \
  ROLLBACK_VALUES=/secure/releases/release-previous/values.yaml \
  ROLLBACK_RELEASE_MANIFEST=/secure/releases/release-previous/release-manifest.json \
  ROLLBACK_RELEASE_BUNDLE=/secure/releases/release-previous/release-manifest.sigstore.json \
  ROLLBACK_RELEASE_EVIDENCE_DIR=/secure/releases/release-previous \
  ARCHIDEAL_BEARER_TOKEN_FILE=/secure/runtime/archideal-token \
  APPROVE_SCHEMA_COMPATIBLE_ROLLBACK=1
```

The wrapper requires the rollback target to equal the recorded previous release, then reuses the
same signed-release verifier, ordered deployer, invocation-fresh APISIX/MQTT Jobs and complete
smoke. It does not call reverse migrations, `pg_restore`, or any destructive schema operation.

Deployment mechanics do not by themselves authorize a go-live. Record every security, resilience,
backup, restore, durable-audit and SLO result in
[production-readiness.md](production-readiness.md). The current DEALHost Core NATS notifications
are disabled in the production baseline and are not a transactional audit log. See the
backup/restore and disaster-recovery runbooks before the first promotion.
