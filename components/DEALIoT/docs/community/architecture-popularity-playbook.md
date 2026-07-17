# Architecture Popularity Playbook

This playbook makes DEALIoT easier to discover, explain, try, trust, and adopt. The objective is not generic popularity; it is repeatable adoption by users who can validate a real data path and explain why the architecture is worth using.

## Adoption Thesis

DEALIoT becomes popular when each evaluator can answer five questions quickly:

1. What problem does this solve better than a custom IoT stack?
2. Can I understand the architecture in less than 10 minutes?
3. Can I run a credible proof without private help?
4. Can I see whether my use case fits?
5. Can I trust the project enough to start a pilot?

## Positioning Message

Use this short message consistently:

> DEALIoT is a production-oriented IoT data architecture that connects field telemetry, stream processing, object metadata, governance evidence, and operational readiness in one reproducible stack.

Use this longer message for landing pages and launches:

> DEALIoT helps teams move from fragile IoT pilots to governed production data flows. It combines MQTT ingestion, Kafka, schema governance, Flink/Beam processing, object metadata, observability, and compliance evidence so teams can validate one field data source, score a 30-day pilot, and harden the runtime for Kubernetes or managed operations.

## Adoption Flywheel

| Loop | Action | Artifact | Success signal |
|---|---|---|---|
| Discover | Publish clear use cases and comparison points | README, website, launch kit | Visitors understand fit quickly |
| Try | Make the first validation path explicit | quickstart, smoke test, demo pilot playbook | First event reaches Kafka |
| Trust | Show production guardrails and compliance evidence | architecture docs, runbooks, tests | Operators can evaluate risk |
| Share | Collect sanitized lessons and adopter stories | show-and-tell, pilot reports, ADOPTERS.md | New evaluators see proof |
| Improve | Convert friction into docs, tests, or roadmap | feedback loop, issues, discussions | Repeated blockers decrease |

## Audience-Specific Hooks

| Audience | Hook | Proof to show |
|---|---|---|
| Research teams | Reproducible IoT-to-dataset pipeline | Zenodo/OpenAIRE export and scorecard |
| Agriculture and livestock operators | One path from field signals to operational state | MQTT fixtures, raw topics, latest-state projection |
| Industrial IoT teams | Production guardrails before scale | Kubernetes overlay, NetworkPolicies, CI gates |
| Public sector and EU projects | Data sharing with evidence | Data Act, DGA, security, resilience topics |
| Integration partners | Repeatable partner contract | integration guide, fixture, test requirement |
| Hosting partners | Operated reference stack | DealHost boundaries, support policy, runbooks |

## Discovery Checklist

- README explains the problem, use cases, quick validation path, and adoption path near the top.
- Website has a visible "Start validation" path and a direct community or pilot CTA.
- `llms.txt` includes the core adoption and community documents.
- GitHub Discussions and issue templates route questions into the right workflow.
- The repository exposes public launch copy that others can reuse.

## Trial Checklist

- The smoke test is referenced from README, demo pilot playbook, and onboarding guide.
- A new evaluator knows what success looks like: first event reaches Kafka, schema is registered, DLQ path is tested, diagnostics are produced on failure.
- The first pilot has one data source, one event contract, one dashboard/export, and one decision owner.
- Feedback is captured through user feedback issues or Q&A discussions.

## Trust Checklist

- Production-readiness documentation is linked from README.
- Security and support boundaries are explicit.
- Compliance statements are evidence-based and avoid certification claims.
- Public adopter references require approval.
- Managed operations are clearly separated from open-source best-effort support.

## Distribution Plan

| Channel | What to publish | Cadence |
|---|---|---|
| GitHub README | Crisp positioning, quickstart, community entry points | Always current |
| Public website | Product story, use cases, pilot CTA | Update per release |
| GitHub Discussions | Q&A, ideas, show-and-tell, pilot reports | Weekly triage |
| LinkedIn or blog | Use-case story, architecture walkthrough, pilot lessons | Monthly |
| Conferences and meetups | "From IoT pilot to governed data product" talk | Per opportunity |
| Partners | Integration contract and partner guide | Per partner |

## Launch Metrics

Measure these monthly:

- Repository visitors to discussions or demo request conversion.
- Time from clone to successful smoke test.
- Number of concrete demo requests.
- Number of discussions converted into docs or issues.
- Number of partner integration proposals with fixture and test path.
- Number of approved adopter stories.

## Do Not Do

- Do not buy attention before the validation path is clear.
- Do not claim production adoption without evidence.
- Do not use chat as the primary knowledge base.
- Do not accept broad roadmap ideas without user segment and proof path.
- Do not hide hard production requirements; they build trust when stated clearly.
