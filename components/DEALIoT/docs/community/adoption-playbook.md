# Community Adoption Playbook

This playbook turns DEALIoT from an internal platform repository into an adoptable open architecture. It defines the public positioning, adoption path, proof assets, and operating cadence needed to attract credible users without overstating traction.

## Positioning

DEALIoT is a production-oriented IoT data platform for teams that need real-time ingestion, schema governance, stream processing, object metadata, observability, and compliance evidence in one open architecture.

DealHost is the managed runtime path for organizations that want the same architecture operated on hardened cloud, hybrid, or on-prem infrastructure.

DealData is the governance and value layer for catalogues, controlled sharing, Data Act readiness, DGA workflows, FAIR publication, Zenodo export, and OpenAIRE discovery.

## Primary Audiences

| Audience | Problem | Adoption message | Proof asset |
|---|---|---|---|
| Research teams | Multimodal field data is hard to process and publish | Start with a reproducible IoT-to-dataset pipeline | Demo pilot, Zenodo/OpenAIRE runbooks |
| Agriculture and livestock operators | Sensor and media streams are fragmented | Use one governed event backbone from device to dashboard | DEALIoT architecture and smoke test |
| Industrial IoT teams | Pilots fail when they reach operations | Adopt a Kubernetes-ready path with CI guardrails | Production deployment tests and runbooks |
| Public sector and EU-funded projects | Data sharing must be controlled and evidenced | Keep Data Act, DGA, and FAIR evidence in the runtime | Compliance dossier and evidence topics |
| Hosting and integration partners | Customers need a repeatable platform pattern | Package DealHost as the operated reference stack | Integration partner guide |

## Adoption Ladder

1. Discover: read the website, README, architecture page, and production readiness page.
2. Validate locally: run the development stack and `scripts/smoke-e2e.sh`.
3. Run a 30-day pilot: choose one data source, one event contract, one dashboard, and one data product.
4. Harden for production: render Kubernetes or Swarm manifests, replace placeholders, add real secrets and private dependency endpoints.
5. Publish evidence: document the pilot result in `ADOPTERS.md` or a private case study using the template.
6. Scale adoption: define SLOs, automate releases, add partner integrations, and move repeatable operations into DealHost.

## Proof Assets To Maintain

- Public website source under `https://github.com/Smartappli/DEALWebsite`.
- Professional README with architecture, quickstart, production deployment, and quality gates.
- Demo pilot playbook under `docs/community/demo-pilot-playbook.md`.
- Partner integration guide under `docs/community/integration-partner-guide.md`.
- Versioned wiki source under `docs/wiki/`.
- Production readiness and audit documents under `docs/architecture/`.
- GitHub issue forms for bugs, features, demo requests, documentation gaps, and adopter stories.
- GitHub discussion forms for Q&A, ideas, show-and-tell, and pilot reports.
- User community launch plan, onboarding guide, rituals, feedback loop, and seed discussions under `docs/community/`.
- `ADOPTERS.md` with only approved public references.

## 30-Day Pilot Motion

| Week | Outcome | Exit criteria |
|---|---|---|
| 1 | Scope and data contract | One device or producer selected, one Kafka topic selected, acceptance metrics written |
| 2 | Local proof | Development stack runs, fixture event reaches Kafka, schema is registered, DLQ path is tested |
| 3 | Operational proof | Dashboard, alert, and replay/backfill path demonstrated |
| 4 | Adoption decision | Pilot scorecard completed, production gaps logged, next deployment target chosen |

## Public Content Cadence

| Frequency | Asset | Goal |
|---|---|---|
| Weekly while active | Short technical note or issue update | Show momentum and remove adoption blockers |
| Monthly | Release note with screenshots, smoke-test result, and roadmap status | Make progress legible to evaluators |
| Per pilot | Sanitized case study or private success memo | Convert proof into reusable adoption evidence |
| Per release | Updated compatibility and deployment notes | Reduce operational risk for adopters |

## Success Metrics

Track adoption without gaming vanity metrics:

- Time from clone to first successful smoke test.
- Number of demo requests with a defined data source.
- Number of external issues or discussions that lead to documentation improvements.
- Number of validated deployment environments.
- Number of public or private adopter stories approved for reference.
- Number of partner integrations documented and tested.

## Operating Rules

- Do not list an adopter without written approval.
- Do not promise managed operations unless DealHost scope, SLOs, and support boundaries are agreed.
- Keep examples reproducible with commands that run from a clean checkout.
- Convert repeated support questions into documentation or tests.
- Keep compliance claims tied to concrete evidence topics, runbooks, and templates.
