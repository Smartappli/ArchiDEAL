# AGENTS.md

This file applies to the entire repository. More specific `AGENTS.md` files in subdirectories override it for their scope.

## Project overview

DEALIoT is a production-oriented real-time IoT data platform. The repository combines Python 3.12+ services and tests, a Rust workspace, Docker Compose development environments, Kubernetes and Docker Swarm deployment assets, shell scripts, dashboards, and operational/compliance documentation.

Before making a change, read the relevant sections of `README.md` and `CONTRIBUTING.md`. For operational or deployment changes, also consult the matching file under `docs/runbooks/`, `docs/wiki/`, or `deploy/`.

## Repository map

- `dealiot_contracts/`, `pipelines/`, `flink/jobs/`, `airflow/dags/`: Python contracts and processing/orchestration code.
- `management-console/`: Python management service and static web UI.
- `mqtt-kafka-bridge/`, `stream-normalizer/`, `dealiot-event-contracts/`, `wildfi-decoder-runner/`: Rust workspace crates.
- `tests/unit/`, `tests/integration/`, `tests/deployment/`: Python test suites and deployment guardrails.
- `deploy/kubernetes/`, `deploy/swarm/`, `docker-compose*.yml`: deployment definitions.
- `scripts/`: bootstrap, database, and end-to-end smoke scripts.
- `docs/`: architecture, runbooks, compliance evidence, and community documentation.

## Working rules

- Keep changes focused and preserve existing behavior unless the task explicitly changes it.
- Never commit secrets, tokens, customer data, private endpoints, `.env`, or files under `secrets/` other than tracked examples/placeholders.
- Do not introduce mutable image tags into production manifests. Production images must use immutable release SHA tags.
- Treat event schemas, topic names, environment variables, deployment manifests, and compliance evidence as public contracts. Update all producers, consumers, examples, tests, and documentation affected by a contract change.
- Keep vendor-specific integrations optional and clearly scoped.
- Add or update tests for behavior changes. Include operational impact and rollback considerations for deployment, security, storage, or migration changes.
- Do not edit generated or local artifacts such as `target/`, cache directories, coverage output, runtime logs, or local secret files.

## Style and formatting

- Follow `.editorconfig`: UTF-8, LF line endings, a final newline, and no trailing whitespace. YAML uses two-space indentation.
- Python is formatted and linted with Ruff using `pyproject.toml`; use double quotes and a 100-character line limit. Keep code compatible with supported Python versions (3.12 through 3.14 in CI).
- Rust belongs to the root Cargo workspace. Run `cargo fmt`; Clippy warnings are treated as errors.
- Shell scripts must pass ShellCheck at warning severity and should retain strict error handling where already used.
- Keep documentation commands executable and examples aligned with the current configuration.

## Validation

Run the narrowest relevant checks while developing, then broaden validation in proportion to the change.

### Python

```bash
uv run python -m unittest discover -s tests/unit -p "test_*.py" -v
uv run python -m unittest -v tests/integration/test_platform_integration.py
uv run --with PyYAML python -m unittest -v tests/deployment/test_deployment_readiness.py
uv run python -m unittest -v tests/test_application_smoke.py
```

For a single test module, run it directly with `uv run python -m unittest -v <module-or-path>`.

### Rust

```bash
cargo fmt --check --all
cargo clippy --workspace --locked -- -D warnings
cargo test --workspace --locked
cargo check --workspace --locked
```

### Repository and deployment assets

```bash
uvx pre-commit run --all-files --show-diff-on-failure
docker compose -f docker-compose.yml config -q
kubectl kustomize deploy/kubernetes/overlays/production
```

Use `bash scripts/smoke-e2e.sh` for changes that affect the runtime event flow, Compose services, Kafka/MQTT integration, schemas, or end-to-end processing. It is expensive and requires Docker, so report clearly when it was not run.

Do not claim a check passed unless it was actually run. In the final handoff, list the checks run and any checks skipped with the reason.

## Documentation and pull requests

- Update `README.md` or the relevant material under `docs/` when behavior, configuration, operations, deployment, security, compliance evidence, or user workflows change.
- Keep pull requests small when practical. Summaries should state the problem, runtime/adoption impact, validation performed, and any configuration, secret, migration, or rollback considerations.
- Large architecture or contract changes should have an explicit rationale, affected user/operator segment, operational impact, and validation path.
