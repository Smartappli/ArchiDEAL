# CI/CD And Release

## Workflows

| Workflow | Purpose |
|---|---|
| `ci.yml` | Cross-platform unit tests, lint, repository validation, deployment tests, Compose config |
| `production-deployment-test.yml` | Production Swarm render, Swarm smoke, Kubernetes render, server dry-run, kind smoke |
| `build-and-push-images.yml` | Build and publish runtime images with SBOM and provenance |
| `sonarqube.yml` | Coverage and SonarQube analysis |
| `codeql.yml` | CodeQL static analysis |
| `bandit.yml` | Python security scanning |
| `osv-scanner.yml` | Dependency vulnerability scanning |
| `shellcheck.yml` | Shell script linting |
| `e2e-smoke.yml` | Full local event-flow smoke test |

## Release Image Tags

Images must be published as:

```text
ghcr.io/<owner>/dealiot-<component>:sha-<git-sha>
```

`latest` is not allowed in production manifests.

## Production Render Checks

The production deployment workflow rejects rendered Kubernetes manifests containing:

- `latest`
- `local-placeholder`
- `sha-REPLACE_WITH_RELEASE_SHA`
- `example.net`
- `SET_FROM_SECRET_MANAGER`

The Swarm render check rejects mutable or placeholder production images.

## Local Validation Commands

```bash
uv run python -m unittest discover -s tests/unit -p "test_*.py" -v
cargo fmt --check --all
cargo clippy --workspace --locked -- -D warnings
cargo test --workspace --locked
uv run python -m unittest -v tests/integration/test_platform_integration.py
uv run --with PyYAML python -m unittest -v tests/deployment/test_deployment_readiness.py
uv run python -m unittest -v tests/test_application_smoke.py
kubectl kustomize deploy/kubernetes/overlays/production >/tmp/dealiot-production.yaml
docker stack config -c deploy/swarm/dealiot-stack.yml >/tmp/dealiot-swarm.yaml
```

## Supply Chain

Current build workflow generates:

- Container images.
- SBOM attestations.
- Provenance attestations.
- OCI labels for source and revision.

Cluster admission signature verification remains an environment-level go-live requirement.
