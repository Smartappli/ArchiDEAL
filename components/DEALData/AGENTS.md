# AGENTS.md

## Repository overview

DEALData contains three independently deployable Django services:

- `core_layer` (port 7000): projects, members, observed objects, and experiments.
- `gps_layer` (port 7001): GPS devices, raw fixes, processed positions, and WildFi `raw.gps` events.
- `sensor_layer` (port 7002): generic sensors, measurements, and WildFi `raw.sensor` events.
- `dealdata_common`: shared utilities used by the layers.

Each layer owns a separate PostgreSQL database. GPS and Sensor must not add SQL
foreign keys to Core; references to Core observed objects remain UUID values in
`observed_object_id`.

## Working conventions

- Keep changes scoped to the affected layer; shared changes belong in
  `dealdata_common` only when more than one layer needs them.
- Preserve ingestion idempotency. WildFi event paths depend on `event_id` and
  `payload_hash` to safely process retries from HTTP and Kafka.
- Add or update tests for behavioral changes. Use sanitized fixtures only; never
  commit secrets, tokens, customer data, personal data, or private endpoints.
- Create Django migrations for model changes. Do not edit existing applied
  migrations unless explicitly required to repair an unreleased change.
- When touching deployment, security, configuration, or data contracts, document
  the operational impact in the relevant docs or configuration example.
- Keep external DEALIoT and DealHost integrations optional and clearly scoped.

## Python tooling

- Target Python version: 3.14.
- Prefer the repository virtual environment at `.venv`.
- Dependency versions are centralized in `pyproject.toml`; the layer-specific
  `requirements.txt` files are used by the documented local setup.
- Use Ruff formatting and linting. Do not introduce style-only rewrites outside
  the requested change.

## Validation

Run the narrowest relevant checks first. From the repository root, the standard
full verification is:

```powershell
.\.venv\Scripts\python.exe -m compileall -q core_layer gps_layer sensor_layer
cd core_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=core.settings -q
cd ..\gps_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=gps.settings -q
cd ..\sensor_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=sensor.settings -q
cd ..
```

For Kafka ingestion changes, also exercise the applicable
`consume_dealiot_kafka` command using sanitized fixtures or a local broker.

Before handing off a change, report the commands run and any checks that could
not be run.

## Pre-commit checks

The repository pre-commit configuration enforces whitespace, YAML/JSON/TOML
validation, AST and merge-conflict checks, private-key detection, Ruff, mypy,
and Bandit. Run the relevant hooks or `pre-commit run --all-files` when the
environment supports it.
