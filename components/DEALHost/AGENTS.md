# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

DEALHost is a Django 6 ASGI hosting platform for modular deployable services. It coordinates:

- Django apps under `apps/` and project settings under `dealhost/`.
- Hosting manifests under `manifests/`.
- Apache APISIX route configuration under `infra/apisix/`.
- Client SDKs under `sdk/` for Python, Go, Rust, R, Julia, and Java.

Primary runtime dependencies are defined in `pyproject.toml` and `requirements.txt`. The project targets Python 3.12+; CI currently exercises Python 3.12, 3.13, and 3.14.

## Repository conventions

- Keep changes focused and scoped to the requested behavior.
- Add or update tests for behavior changes and bug fixes.
- Update docs when endpoints, settings, manifests, APISIX routes, or SDK behavior change.
- Do not commit secrets, tokens, private URLs, production credentials, or populated local environment files.
- Preserve existing user changes in the worktree. Do not overwrite unrelated edits.
- Prefer existing patterns in nearby files over introducing new abstractions.

## Local setup

Typical PowerShell setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Full local stack:

```powershell
docker compose up
```

## Validation commands

Run the smallest relevant check for the files changed. For broad Python/Django changes, use:

```powershell
python manage.py makemigrations --check --dry-run
python manage.py test tests --verbosity 2 --settings=dealhost.settings.test
python -m compileall dealhost apps tests
```

For coverage parity with CI:

```powershell
coverage run manage.py test tests --verbosity 2 --settings=dealhost.settings.test
coverage report --fail-under=80
```

For formatting and lint hooks:

```powershell
pre-commit run --all-files
```

For hosting manifests and APISIX route changes:

```powershell
python scripts/validate_hosting_manifests.py
$env:HOSTING_MANIFEST_STRICT_IMAGES = "true"
python scripts/validate_hosting_manifests.py
python -m json.tool infra/apisix/routes.json
```

For SDK changes:

```powershell
python -m unittest discover -s sdk/python/tests -v
Push-Location sdk/go/dealhost-sdk; go test ./...; Pop-Location
Push-Location sdk/rust/dealhost-sdk; cargo test; Pop-Location
Push-Location sdk/java/dealhost-sdk; mvn --batch-mode test; Pop-Location
Rscript -e "testthat::test_local('sdk/r/dealhostR')"
julia --project=sdk/julia/DealHostSDK.jl -e "using Pkg; Pkg.instantiate(); Pkg.test()"
```

## Django and API guidance

- Test settings are configured through `DJANGO_SETTINGS_MODULE=dealhost.settings.test` in `pyproject.toml`.
- Keep domain logic near the owning app: hosting code in `apps/hosting/`, gateway orchestration in `apps/gateway/`, IAM in `apps/iam/`, and shared auth/events code in `apps/common/`.
- When adding or changing models, include migrations and check that `makemigrations --check --dry-run` passes after committing generated migrations.
- Use explicit permission and authentication behavior for new API endpoints.
- Prefer deterministic tests that do not require real GitHub, APISIX, NATS, Redis/Valkey, or network access unless explicitly requested.

## Manifest and APISIX guidance

- Keep JSON manifests valid and consistent with `scripts/validate_hosting_manifests.py`.
- When adding modules, tools, applications, repositories, or datasets, update related manifests together so discovery and gateway behavior remain coherent.
- APISIX standalone route config lives in `infra/apisix/routes.json`; validate JSON syntax after edits.
- Production image policy is stricter when `HOSTING_MANIFEST_STRICT_IMAGES=true`.

## Security guidance

- Treat gateway, webhook, token, IAM, and deployment settings as security-sensitive.
- Do not log or expose API tokens, GitHub tokens, APISIX admin keys, webhook secrets, or session credentials.
- Keep `.env` local. Use `.env.example` only for placeholder values and documented configuration names.
- Follow `SECURITY.md` for vulnerability reporting context.

## Pull request handoff

When summarizing changes, include:

- What changed and why.
- Tests or validation commands run.
- Any migrations, settings, APISIX route changes, manifest changes, or deployment impacts.
