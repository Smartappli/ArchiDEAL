# First GitHub Discussion

Use this as the first public GitHub Discussion after Discussions are enabled. Publish it in English to maximize reach across the GitHub, IoT, data engineering, and open-source infrastructure audience.

Recommended category: Announcements. If that category is not available, use General. If neither exists, use Show and tell.

## Title

```text
Show DEALIoT: production-oriented IoT data architecture from MQTT to governed data products
```

## Body

```md
We are opening DEALIoT for public evaluation.

DEALIoT is a production-oriented IoT data architecture for teams that need more than a demo pipeline. It connects field telemetry, MQTT ingestion, Kafka topics, schema governance, stream processing, replay/backfill, observability, and governance evidence into one reproducible stack.

Why it exists:

- Many IoT pilots stop at ingestion.
- Production teams also need contracts, replay, DLQ, observability, deployment guardrails, and data-sharing evidence.
- Research, agriculture, livestock, industrial IoT, and public-sector projects need a path from field data to governed data products.

What is included:

- MQTT to Kafka ingestion
- Schema governance with Apicurio
- Stream processing with Flink and Beam
- Airflow replay/backfill paths
- Object and media metadata flows
- Prometheus/Grafana observability
- Kubernetes and Swarm deployment guardrails
- DealData governance/export evidence
- A 30-day pilot scorecard

Start here:

- Website: https://smartappli.io/
- Repository: https://github.com/Smartappli/DEALIoT
- Quick evaluation path: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/quick-evaluation-path.md
- Use case catalog: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/use-case-catalog.md
- Contributor onboarding: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/contributor-onboarding.md

We are looking for:

- One concrete field data source to validate
- Device or gateway integration proposals
- Feedback on the local evaluation path
- Documentation gaps that block adoption
- Small contributor issues with fixtures or tests
- Public-safe pilot lessons or show-and-tell posts

If this looks useful, star the repository, try the quick evaluation path, and reply with the first use case you would validate.

Please do not post secrets, customer data, personal data, private endpoint values, or vulnerability details in this public discussion.
```

## Follow-Up Actions

- Reply within 3 business days to every concrete use case or blocker.
- Convert repeated blockers into documentation, tests, or scoped issues.
- Link accepted small tasks to `docs/community/contributor-onboarding.md`.
- Reference the discussion in external launch posts.
- Add a weekly recap comment with what changed because of the discussion.
