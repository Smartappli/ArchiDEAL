# Contributor Onboarding

This guide helps new contributors make useful changes without needing private context.

## Start Here

1. Read `README.md` to understand the architecture.
2. Read `CONTRIBUTING.md` for validation expectations.
3. Read `SUPPORT.md` to choose the right channel.
4. Pick a contribution track from `docs/community/developer-community-playbook.md`.
5. Ask in GitHub Discussions if the scope is unclear before opening a large PR.

## First Contribution Paths

| Path | Best first PR |
|---|---|
| Documentation | Fix one unclear command, runbook step, FAQ, or adoption page |
| Tests | Add coverage for a small helper, parser, fixture, or repository guardrail |
| Device examples | Add a sanitized MQTT payload fixture and expected topic behavior |
| Deployment docs | Clarify one Kubernetes, Swarm, or local setup boundary |
| Community | Improve one issue template, discussion seed, label, or onboarding doc |

## Before Opening A Pull Request

Include:

- What changed.
- Why it matters for users, operators, adopters, or contributors.
- Which validation command was run.
- Whether the change affects runtime behavior, deployment, security, compliance, or docs only.
- Any follow-up that should become a separate issue.

## Validation Shortcuts

Use the smallest relevant validation first:

```bash
uv run python -m unittest discover -s tests/unit -p "test_*.py" -v
uvx pre-commit run --all-files --show-diff-on-failure
```

For website-only copy changes, work in the dedicated website repository:

```bash
cd ../DEALWebsite
npm run build
node --check app.js
node --check sw.js
```

## Asking For Help

Use the Contributor help discussion template when:

- You want to work on a contribution but need scoping.
- A validation command fails and the error is not clear.
- You are unsure whether a change belongs in code, docs, tests, or an issue.

Do not use public discussions for secrets, customer data, private deployment endpoints, or vulnerability details.
