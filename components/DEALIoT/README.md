# DEALIoT

DEALIoT is a production-oriented real-time IoT data platform for multimodal telemetry, media metadata, schema governance, stream processing, orchestration, and operational compliance evidence.

The platform targets livestock, precision agriculture, and industrial IoT deployments where device telemetry, GPS data, media objects, and governance evidence must be processed reliably from edge ingestion to curated datasets.

[![CI](https://github.com/Smartappli/DEALIoT/actions/workflows/ci.yml/badge.svg)](https://github.com/Smartappli/DEALIoT/actions/workflows/ci.yml)
[![Production Deployment Test](https://github.com/Smartappli/DEALIoT/actions/workflows/production-deployment-test.yml/badge.svg)](https://github.com/Smartappli/DEALIoT/actions/workflows/production-deployment-test.yml)
[![CodeQL](https://github.com/Smartappli/DEALIoT/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smartappli/DEALIoT/actions/workflows/codeql.yml)
[![ShellCheck](https://github.com/Smartappli/DEALIoT/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/Smartappli/DEALIoT/actions/workflows/shellcheck.yml)
[![SonarQube](https://github.com/Smartappli/DEALIoT/actions/workflows/sonarqube.yml/badge.svg)](https://github.com/Smartappli/DEALIoT/actions/workflows/sonarqube.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALIoT&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALIoT)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALIoT&metric=coverage)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALIoT)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALIoT&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALIoT)

## Why Teams Adopt DEALIoT

DEALIoT is designed for teams that need to move beyond isolated IoT demos into governed, reproducible, production-ready data flows. The adoption thesis is simple: prove one field data source, one event contract, one useful output, and one operational decision path before scaling the architecture.

Strong first-fit scenarios include livestock telemetry, WildFi decoding, precision agriculture, industrial IoT hardening, research dataset publication, EU data-sharing readiness, managed hosting evaluation, and device or platform integrations.

## Fast Adoption Path

1. Confirm fit with the [use case catalog](docs/community/use-case-catalog.md).
2. Compare alternatives with the [architecture comparison guide](docs/community/architecture-comparison-guide.md).
3. Run the [quick evaluation path](docs/community/quick-evaluation-path.md) and capture the first event reaching Kafka.
4. Help an internal owner make the case with the [internal champion kit](docs/community/internal-champion-kit.md).
5. Scope one 30-day pilot with the [demo pilot playbook](docs/community/demo-pilot-playbook.md).
6. Score the pilot with the [validation scorecard](docs/community/validation-scorecard.md).
7. Publish an approved lesson, adopter story, or integration note using the [public launch kit](docs/community/public-launch-kit.md).

## Platform Scope

DEALIoT provides six runtime planes:

| Plane | Responsibility | Primary components |
|---|---|---|
| Ingestion | Secure MQTT ingestion and routing to Kafka topics | VerneMQ, Rust MQTT-Kafka bridge |
| Event backbone | Durable event transport and schema governance | Kafka KRaft, Apicurio Registry |
| Object storage | Raw and derived media object storage | SeaweedFS S3 locally, managed S3 in production |
| Processing | Stream processing, feature projection, replay, and backfill | Flink Kubernetes Operator, Beam, Airflow |
| Storage | Operational SQL state and connection pooling | TimescaleDB, Patroni, HAProxy, PgBouncer |
| Operations | Observability, control surfaces, and compliance evidence | Prometheus, Grafana, Management Console |

## Website And Adoption

- Public website: `https://smartappli.io/`
- Website source repository: `https://github.com/Smartappli/DEALWebsite`
- Adoption playbook: [docs/community/adoption-playbook.md](docs/community/adoption-playbook.md)
- Architecture popularity playbook: [docs/community/architecture-popularity-playbook.md](docs/community/architecture-popularity-playbook.md)
- GitHub star growth plan: [docs/community/github-star-growth-plan.md](docs/community/github-star-growth-plan.md)
- Use case catalog: [docs/community/use-case-catalog.md](docs/community/use-case-catalog.md)
- Quick evaluation path: [docs/community/quick-evaluation-path.md](docs/community/quick-evaluation-path.md)
- Architecture comparison guide: [docs/community/architecture-comparison-guide.md](docs/community/architecture-comparison-guide.md)
- Internal champion kit: [docs/community/internal-champion-kit.md](docs/community/internal-champion-kit.md)
- Public launch kit: [docs/community/public-launch-kit.md](docs/community/public-launch-kit.md)
- First GitHub discussion: [docs/community/first-github-discussion.md](docs/community/first-github-discussion.md)
- Adoption funnel: [docs/community/adoption-funnel.md](docs/community/adoption-funnel.md)
- User community launch plan: [docs/community/user-community-launch-plan.md](docs/community/user-community-launch-plan.md)
- User onboarding guide: [docs/community/user-onboarding-guide.md](docs/community/user-onboarding-guide.md)
- Community rituals: [docs/community/community-rituals.md](docs/community/community-rituals.md)
- User feedback loop: [docs/community/user-feedback-loop.md](docs/community/user-feedback-loop.md)
- Developer community playbook: [docs/community/developer-community-playbook.md](docs/community/developer-community-playbook.md)
- Contributor onboarding: [docs/community/contributor-onboarding.md](docs/community/contributor-onboarding.md)
- Community governance: [docs/community/community-governance.md](docs/community/community-governance.md)
- Seed discussions: [docs/community/seed-discussions.md](docs/community/seed-discussions.md)
- Demo pilot playbook: [docs/community/demo-pilot-playbook.md](docs/community/demo-pilot-playbook.md)
- Integration partner guide: [docs/community/integration-partner-guide.md](docs/community/integration-partner-guide.md)
- Pilot validation scorecard: [docs/community/validation-scorecard.md](docs/community/validation-scorecard.md)
- Adopter story template: [docs/community/adopter-story-template.md](docs/community/adopter-story-template.md)
- Community discussions: `https://github.com/Smartappli/DEALIoT/discussions`
- Roadmap: [ROADMAP.md](ROADMAP.md)
- Support policy: [SUPPORT.md](SUPPORT.md)
- Public references: [ADOPTERS.md](ADOPTERS.md)

The recommended adoption path is: validate the local smoke test, run a 30-day pilot with one data
source and one value output, then harden the target runtime with the production deployment
guardrails.

The recommended community path is: ask usage questions in GitHub Discussions, open issues only for
confirmed bugs or scoped changes, share pilot feedback with the user feedback template, and convert
repeated questions into documentation or tests.

## Architecture

```mermaid
flowchart LR
  Device[IoT devices] --> MQTT[MQTT broker]
  Media[Media producers] --> S3[S3-compatible object storage]
  MQTT --> Bridge[MQTT-Kafka bridge]
  Bridge --> Kafka[(Kafka)]
  S3 --> Kafka
  Registry[Apicurio Registry] -. schema governance .-> Kafka
  Kafka --> Flink[Flink Operator-managed job]
  Flink --> Derived[(features.events / state.latest)]
  Kafka --> Beam[Beam pipelines]
  Airflow[Airflow orchestration] --> S3
  Airflow --> Kafka
  Kafka --> State[(TimescaleDB / downstream stores)]
  Prometheus[Prometheus] --> Grafana[Grafana]
  Console[Management Console] --> Airflow
  Console --> Registry
  Console --> Flink
```

### Production Architecture Principles

- Kubernetes is the primary production target.
- Docker Swarm remains available for simpler runtime deployments and smoke validation.
- Stateful dependencies are externalized in production unless managed by a dedicated operator.
- Runtime dependency traffic is encrypted or private: Kafka `SASL_SSL`, MQTT TLS, S3 TLS, PostgreSQL private connectivity, and Redis private connectivity.
- Kubernetes production uses default-deny NetworkPolicies, Pod Security `restricted`, immutable image tags, readiness/liveness probes, HPA, PDB, and topology spread constraints.
- Secrets are expected from a secret manager, External Secrets Operator, or equivalent out-of-band mechanism.
- Flink is the authoritative production state owner; the Rust normalizer is an explicitly selected stateless alternative.
- Production images are signed keylessly and the optional security component verifies the protected workflow identity at admission.

## Repository Layout

```text
.github/workflows/                         CI, security scans, image build, deployment validation
airflow/dags/                              Airflow DAGs
apicurio/bootstrap/                        Registry schema bootstrap payloads
dealiot_contracts/                         Python event contract helpers for tests and pipelines
deploy/kubernetes/base/                    Kubernetes base runtime manifests
deploy/kubernetes/processing/              Mutually exclusive Flink and Rust processing packages
deploy/kubernetes/overlays/production/     Production Kustomize overlay
deploy/swarm/                              Docker Swarm runtime and smoke stacks
docs/                                      Architecture, compliance, and runbooks
flink/jobs/                                PyFlink streaming jobs
management-console/                        Internal operational console
mqtt-kafka-bridge/                         Rust MQTT to Kafka ingestion bridge
stream-normalizer/                         Rust Kafka-to-Kafka lightweight stream normalizer
dealiot-event-contracts/                   Shared Rust event contracts and validators
wildfi-decoder-runner/                     Rust runner for the packaged WildFi Java decoder
pipelines/                                 Replay and backfill utilities
scripts/                                   Bootstrap and smoke-test scripts
tests/                                     Unit, integration, and deployment guardrail tests
wildfi-decoder/                            Offline WildFi binary decoder image wrapper
```

## Event Topics

Core runtime topics include:

| Topic | Purpose |
|---|---|
| `raw.sensor` | Device telemetry and decoded WildFi sensor payloads |
| `raw.gps` | GPS and GNSS events |
| `raw.image2d.meta` | 2D image metadata |
| `raw.image3d.meta` | 3D image metadata |
| `raw.video2d.meta` | 2D video metadata |
| `raw.video3d.meta` | 3D video metadata |
| `media.object.events` | Object storage notifications |
| `features.events` | Derived feature events |
| `state.latest` | Compacted latest state projection |
| `dlq.events` | Invalid or unroutable event records |

Governance, Data Act, DGA, security, resilience, and compliance evidence topics are defined in `docker-compose.yml`, `apicurio/bootstrap/`, and `docs/runbooks/security-resilience-compliance.md`.
The provider-neutral production topic and principal contract is maintained in `deploy/kafka/topics.yaml`.

## Local Development

### Prerequisites

- Docker Engine with Compose v2
- Python 3.12 or newer for local tests
- `uv` for reproducible Python tooling
- Rust toolchain for native MQTT-Kafka bridge checks
- `kubectl` for rendering Kubernetes overlays

### Configure Local Secrets

```bash
cp .env.example .env
mkdir -p secrets
```

Populate the secret files listed in `README` runbooks and `.env.example`. Local secrets must stay outside Git; `.gitignore` and `.dockerignore` exclude `.env` and `secrets/`.

### Start The Development Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

To run the lightweight Rust Kafka-to-Kafka normalizer locally instead of submitting the PyFlink
minimal streaming job, enable its Compose profile:

```bash
docker compose --profile rust-normalizer -f docker-compose.yml up -d --build stream-normalizer
```

Do not run the Rust normalizer and the PyFlink minimal job against the same `features.events` and
`state.latest` topics unless you are intentionally comparing both implementations.

Useful local endpoints when the development overlay is active:

| Service | Endpoint |
|---|---|
| Airflow | `http://localhost:8088` |
| Flink | `http://localhost:8081` |
| Apicurio Registry | `http://localhost:8082/apis/registry/v3` |
| Management Console | `http://localhost:8090` |
| Grafana | `http://localhost:3000` |
| Prometheus | `http://localhost:9090` |
| SeaweedFS S3 | `http://localhost:8333` |

### Run The End-To-End Smoke Test

```bash
bash scripts/smoke-e2e.sh
```

The smoke test starts the core event-flow services, submits the minimal Flink job, publishes MQTT fixtures, validates Kafka topics, verifies Apicurio artifacts, and captures diagnostics on failure.

## Production Deployment

### Kubernetes

The production overlay is located at `deploy/kubernetes/overlays/production`.

Before deployment:

1. Replace all `sha-REPLACE_WITH_RELEASE_SHA` image tags with immutable release SHA tags.
2. Replace example dependency endpoints in `runtime-config.production.example.env`.
3. Provide `dealiot-secrets` through a secret manager or External Secrets Operator.
4. Narrow NetworkPolicy `ipBlock` ranges to real private dependency CIDRs.
5. Confirm metrics-server or another HPA metrics provider is installed.

Render locally:

```bash
kubectl kustomize deploy/kubernetes/overlays/production >/tmp/dealiot-production.yaml
```

Apply through your GitOps controller or deployment pipeline after replacing all placeholders.

### Docker Swarm

The Swarm stack is located at `deploy/swarm/dealiot-stack.yml` and expects external Kafka, MQTT, S3, PostgreSQL, and Redis services.

```bash
docker stack config -c deploy/swarm/dealiot-stack.yml
docker stack deploy -c deploy/swarm/dealiot-stack.yml dealiot
```

Create required Swarm secrets before deployment. See `deploy/swarm/README.md` for the exact contract.

## Runtime Security

The production runtime contract requires:

- Kafka `SASL_SSL` with SCRAM credentials.
- MQTT TLS on port `8883` by default.
- Management Console bearer-token protection for `/api/*` and mutation routes.
- Kubernetes Pod Security `restricted` on production and CI smoke namespaces.
- Default-deny Kubernetes NetworkPolicies.
- Immutable image tags and CI checks that reject mutable tags and unresolved placeholders.
- Container resources, readiness/liveness probes, dropped Linux capabilities, and disabled service-account token automounting.

The ingestion path uses at-least-once delivery semantics. The Rust bridge acknowledges MQTT QoS 1
messages only after Kafka confirms delivery, and the normalizer commits source offsets only after
both derived records have been acknowledged. Kafka idempotent producers prevent duplicates caused
by internal producer retries; consumers must still tolerate a duplicate if a process stops between
downstream delivery and source acknowledgement.

For end-to-end idempotence, publishers should include a stable `event_id`, `message_id`,
`measurement_id`, `sequence` or `counter`. The bridge hashes that source identity into the
64-character event identifier and therefore maps a redelivery to the same record. Without a source
identity it deliberately creates a new identifier for each MQTT delivery: this may retain a
duplicate after a retry, but it never drops a legitimate repeated measurement merely because its
payload equals an earlier one.

The bridge `/metrics` endpoint exposes readiness, received MQTT deliveries, durably forwarded
deliveries, DLQ records, loop errors and Kafka acknowledgement latency. Aggregate readiness requires
MQTT SUBACK reason codes granting QoS 1 for every configured subscription and the latest Kafka
metadata check; an ACL rejection or QoS downgrade fails the loop instead of marking the pod ready.
The Kafka check runs every
15 seconds with a 5-second bound, so an idle bridge leaves readiness after Kafka becomes unavailable.
Kafka queue admission is bounded to 5 seconds and broker delivery to 30 seconds. `received_total`
includes MQTT redeliveries and process counters reset on restart, so their ratio is an operational
signal, not a unique-event 30-day SLI. The unified ArchiDEAL production overlay discovers this
endpoint with a `PodMonitor`; the complete measurement limits are documented in `../../docs/slo.md`.

## Testing And Quality Gates

Run the same validation layers used by CI:

```bash
uv run python -m unittest discover -s tests/unit -p "test_*.py" -v
cargo fmt --check --all
cargo clippy --workspace --locked -- -D warnings
cargo test --workspace --locked
uv run python -m unittest -v tests/integration/test_platform_integration.py
uv run --with PyYAML python -m unittest -v tests/deployment/test_deployment_readiness.py
uv run python -m unittest -v tests/test_application_smoke.py
```

Additional CI gates include:

- Pre-commit hooks: YAML, JSON, Ruff, Mypy, djLint.
- CodeQL, Bandit, OSSAR, OSV Scanner, SonarQube, and Codacy coverage upload.
- Docker image builds with SBOM and provenance attestations.
- Kubernetes render and server-side dry-run validation.
- Docker Swarm render and smoke deployment validation.
- kind smoke deployment for the bridge image.

## Operations And Runbooks

Primary runbooks:

- [Operations](docs/runbooks/operations.md)
- [Backup and restore](docs/runbooks/backup-restore.md)
- [Security hardening](docs/runbooks/security-hardening.md)
- [Security resilience compliance](docs/runbooks/security-resilience-compliance.md)
- [WildFi ingestion](docs/runbooks/wildfi-ingestion.md)
- [Data Governance Act](docs/runbooks/data-governance-act.md)
- [Data Act](docs/runbooks/data-act.md)
- [Dataset catalogue and DMP](docs/runbooks/data-management-plan.md)
- [Zenodo export](docs/runbooks/zenodo-export.md)
- [OpenAIRE export](docs/runbooks/openaire-export.md)

The GitHub Wiki contains the production architecture handbook, deployment guide, configuration reference, operational runbooks, scaling model, and security checklist.

## WildFi Support

DEALIoT supports WildFi telemetry through:

- MQTT subscription to `$share/ingestors/wildfi/#`.
- Routing decoded GPS/GNSS payloads to `raw.gps`.
- Routing decoded IMU, environment, proximity, movement, and metadata payloads to `raw.sensor`.
- Offline binary decoding through the packaged `wildfi-decoder` image, driven by a Rust runner around the pinned upstream Java decoder.

References:

- `docs/runbooks/wildfi-ingestion.md`
- `deploy/kubernetes/overlays/production/wildfi-decoder-config.yaml`
- `deploy/kubernetes/overlays/production/wildfi-decoder-job.yaml`

## Contribution Workflow

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

New contributors should start with the [contributor onboarding guide](docs/community/contributor-onboarding.md). Maintainers use the [developer community playbook](docs/community/developer-community-playbook.md) and [community governance](docs/community/community-governance.md) to keep contribution paths small, reviewable, and aligned with production quality.

1. Create changes with tests.
2. Run the validation commands above.
3. Render Kubernetes and Swarm manifests when deployment files change.
4. Keep production placeholders out of rendered manifests.
5. Update README, wiki, runbooks, or community docs when user-facing behavior changes.
6. Commit with a focused message and push to GitHub.

Community expectations are defined in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Security reports
must follow [SECURITY.md](SECURITY.md), not public issues.

## License

This repository is licensed under the terms in [LICENSE](LICENSE).
