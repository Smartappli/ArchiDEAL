# Adoption Funnel

This funnel converts attention into adoption decisions. It should guide README structure, website copy, community triage, and release notes.

## Funnel Stages

| Stage | User question | Repository answer | Conversion signal |
|---|---|---|---|
| Awareness | What is this and why should I care? | Website, README pitch, public launch kit | User clicks docs or stars repository |
| Fit | Does this match my use case? | Use case catalog and architecture docs | User selects a data source |
| Trial | Can I run it? | Local development path and smoke test | First event reaches Kafka |
| Trust | Can this survive production constraints? | Production readiness, tests, runbooks, support boundaries | User opens pilot or hardening discussion |
| Adoption | Can we commit to this? | Pilot playbook, scorecard, adopter story template | Pilot scorecard completed |
| Expansion | Can others integrate or operate it? | Partner guide, DealHost boundaries, feedback loop | Partner integration or managed hosting scope |

## Conversion Assets

| Asset | Stage |
|---|---|
| `README.md` | Awareness, fit, trial |
| `https://github.com/Smartappli/DEALWebsite` | Awareness, fit |
| `docs/community/github-star-growth-plan.md` | Awareness, expansion |
| `docs/community/first-github-discussion.md` | Awareness, fit |
| `docs/community/use-case-catalog.md` | Fit |
| `docs/community/architecture-comparison-guide.md` | Fit, trust |
| `docs/community/quick-evaluation-path.md` | Trial |
| `docs/community/internal-champion-kit.md` | Trust, adoption |
| `scripts/smoke-e2e.sh` | Trial |
| `docs/architecture/production-readiness.md` | Trust |
| `docs/community/demo-pilot-playbook.md` | Adoption |
| `docs/community/validation-scorecard.md` | Adoption |
| `docs/community/integration-partner-guide.md` | Expansion |
| `docs/community/contributor-onboarding.md` | Expansion |
| `docs/community/developer-community-playbook.md` | Expansion |

## Weekly Funnel Review

Ask:

- Where did users stop?
- Which question repeated?
- Which command or page failed to move them forward?
- Which use case created the strongest signal?
- Which artifact should be improved before promoting more broadly?

## Minimum Viable Popularity

Do not optimize for stars alone. A healthier early target is:

- 3 concrete demo requests.
- 2 external questions converted into documentation.
- 1 partner integration proposal with fixture and owner.
- 1 pilot scorecard completed.
- 1 approved adopter story or private reference.
