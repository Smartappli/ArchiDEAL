# Contributing To DEALData

DEALData welcomes practical contributions that make the data services easier to run, verify, extend, and operate with DEALIoT and DealHost.

## Community Entry Points

- Usage questions: `https://github.com/Smartappli/DEALData/discussions/categories/q-a`
- Ideas and integration proposals: `https://github.com/Smartappli/DEALData/discussions/categories/ideas`
- Contributor help: `https://github.com/Smartappli/DEALData/discussions/categories/contributor-help`
- Security reports: follow `SECURITY.md` and do not open public vulnerability issues.

## Good First Contributions

- Improve local setup, smoke checks, or Django validation diagnostics.
- Add fixtures or tests for core, GPS, sensor, or WildFi ingestion behavior.
- Improve README guidance, deployment notes, or data-contract documentation.
- Harden CI checks without making local development brittle.
- Clarify idempotency, data quality, or Kafka integration behavior.

Good first issues must be small, reproducible, and include acceptance criteria plus a validation command. Maintainers should label them with `good first issue`; use `mentored` when a maintainer can actively guide the work.

## Contribution Rules

- Keep behavior testable and deterministic.
- Do not commit secrets, tokens, customer data, raw personal data, or private endpoint values.
- Do not add mutable production image tags.
- Add or update tests for behavior changes.
- Document operational impact when touching deployment, security, compliance, or data-contract files.
- Keep DEALIoT, DealHost, and external integrations optional and clearly scoped.

## Local Validation

Run the relevant gates before opening a pull request:

```powershell
.\scripts\validate.ps1
# Or target one service: .\scripts\validate.ps1 -Layer gps
```

The script runs compilation, the Django system check, migration drift detection,
and the relevant pytest suite. The equivalent explicit commands are:

```powershell
.\.venv\Scripts\python.exe -m compileall -q core_layer gps_layer sensor_layer
cd core_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=core.settings -q
cd ..\gps_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=gps.settings -q
cd ..\sensor_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=sensor.settings -q
cd ..
```

For Kafka ingestion changes, also validate the relevant `consume_dealiot_kafka` command path with sanitized fixtures or a local broker.

## Pull Request Expectations

A pull request should explain:

- The problem being solved.
- The affected layer: core, GPS, sensor, shared code, deployment, docs, or CI.
- The tests and manual checks performed.
- Any production configuration, secret, migration, data-contract, rollback, or support consideration.

External contributors should prefer small PRs. Large architecture or data-model changes should start as a discussion or issue with a clear user segment, operational impact, data-contract impact, and validation path.

## Documentation Expectations

If a change affects users, operators, integrators, or data-governance evidence, update at least one of:

- `README.md`
- `.env.example`
- deployment compose files
- layer-specific Django app documentation or tests
- issue, support, or contributor guidance
