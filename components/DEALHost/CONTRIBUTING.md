# Contributing to DEALHost

Thank you for contributing to DEALHost. This project is a Django 6 ASGI hosting
platform that coordinates deployable modules, GitHub repositories, and Apache
APISIX routes.

## Before You Start

- Check existing issues and pull requests to avoid duplicate work.
- Open an issue for behavioral changes, API changes, or production-impacting
  work before submitting a large pull request.
- Keep changes focused. Separate refactors, dependency updates, and feature work
  into different pull requests when possible.

## Local Development

DEALHost targets Python 3.12 and newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Create a local environment file from the example before running the application.

```powershell
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

For the full local stack, use Docker Compose:

```powershell
docker compose up
```

## Validation

Run the relevant checks before opening a pull request.

```powershell
python manage.py test tests --verbosity 2 --settings=dealhost.settings.test
python -m compileall dealhost apps tests
```

If `pre-commit` is installed, run the repository hooks:

```powershell
pre-commit run --all-files
```

The GitHub workflows also validate SDK tests, APISIX routes, hosting manifests,
Ruff formatting and linting, CodeQL, Bandit, OSV Scanner, SonarCloud, and
dependency automation configuration.

## Pull Request Expectations

- Explain the user-visible behavior change and why it is needed.
- Include tests for new behavior or bug fixes.
- Update documentation when endpoints, settings, manifests, or SDK behavior
  change.
- Keep secrets, tokens, private URLs, and production credentials out of commits.
- Confirm whether database migrations, APISIX route changes, or deployment
  configuration updates are required.

## Security-Sensitive Changes

Do not disclose vulnerabilities in public issues or pull requests. Follow
`SECURITY.md` for private reporting guidance.
