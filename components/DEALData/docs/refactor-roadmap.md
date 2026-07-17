# Progressive refactor roadmap

This roadmap keeps DEALData deployable throughout the refactor. Each phase is
independently reviewable, tested, and reversible at the application boundary.

## Phase 1: Shared ingestion foundation — complete

- Move the common idempotent persistence workflow into `dealdata_common`.
- Keep the GPS and Sensor public ingestion functions, URLs, response bodies, and
  status codes stable.
- Preserve the pre-save lookup and the duplicate lookup after an integrity race.
- Add regression coverage for malformed GPS values and model-level validation.

Acceptance criteria: all layer tests pass, no migrations are generated, and the
Kafka consumers retain the same ingestion behavior.

## Phase 2: Define Core application boundaries

The repository contains an authentication application that is not currently
installed or routed by the Core service. Before changing it, maintainers must
choose one of these supported directions:

1. Activate it as a supported Core feature, including routes, templates,
   migrations, email configuration, permission rules, and end-to-end tests.
2. Remove it as unused code, after confirming that no deployment or external
   service imports it.

In the same phase, document ownership boundaries for Core, GPS, Sensor, and
shared code. Keep cross-service observed-object references as UUIDs rather than
database foreign keys.

Acceptance criteria: one explicit authentication direction, no dormant Django
apps, and documented service ownership.

## Phase 3: API contracts and observability — in progress

- Version or explicitly document ingestion and list-response contracts. The
  current HTTP and Kafka contract is now published.
- Consolidate repeated health and Prometheus response helpers while keeping the
  existing endpoints stable. This extraction is complete.
- Define retention, pagination, filtering, and rate-limit policies for large
  event volumes.
- Add contract tests for HTTP and Kafka ingestion parity.

Acceptance criteria: published API contract, stable health endpoints, and
contract tests covering success, validation, retries, and duplicates.

## Phase 4: Operational hardening — in progress

- Add a deployment-specific environment validation command. Deployment checks
  now run during production container startup.
- Make production security settings explicit and verify the production Compose
  configuration in CI.
- Validate numeric environment values at startup with actionable errors.
- Add structured application logging with correlation fields for event ID,
  device ID, topic, and Kafka partition/offset.
- Define backup, restore, and migration rollback procedures per database.

Acceptance criteria: staging deployment checklist, verified environment
validation, and documented recovery procedure.

## Phase 5: Developer experience and quality gates — in progress

- Provide one bootstrap command for the virtual environment and development
  tooling. A local validation command is now available for the repository or a
  single service.
- Ensure Ruff, mypy, Bandit, tests, migration checks, and Compose validation
  have clear local and CI execution paths.
- Split the test suites into focused unit, API, and integration groups as their
  size grows.
- Establish coverage targets for shared code in addition to each Django layer.

Acceptance criteria: a contributor can reproduce CI checks locally from a clean
checkout and obtain actionable failures.

## Delivery rules

- Deliver one phase or independently deployable slice at a time.
- Preserve public API compatibility unless a versioned deprecation is published.
- Pair behavior changes with tests and operational documentation.
- Do not combine schema changes with unrelated refactors.
