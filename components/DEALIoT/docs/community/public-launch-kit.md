# Public Launch Kit

This kit provides copy and assets for announcing DEALIoT consistently across GitHub, website updates, social posts, partner emails, and community discussions.

## One-Liner

DEALIoT is a production-oriented IoT data architecture for turning field telemetry, media metadata, stream processing, and governance evidence into a reproducible data platform.

## Short Pitch

DEALIoT helps teams move from fragile IoT pilots to governed production data flows. It combines MQTT ingestion, Kafka, schema governance, stream processing, object metadata, observability, and compliance evidence so teams can validate one field data source, score a 30-day pilot, and harden the runtime for production.

## Technical Pitch

DEALIoT is an open architecture for real-time IoT data systems. It routes MQTT telemetry and media metadata into Kafka, governs schemas with Apicurio, processes streams with Flink and Beam, orchestrates replay and backfills with Airflow, stores operational state, and exposes observability plus compliance evidence for production readiness.

## Launch Post

```md
We are publishing DEALIoT as a production-oriented IoT data architecture.

It is designed for teams that need more than a demo pipeline:

- MQTT ingestion into Kafka
- Schema governance
- Stream processing with Flink and Beam
- Media metadata and object-event flows
- Operational state and observability
- Compliance and data-governance evidence
- A 30-day pilot scorecard

Start here:

- Website: https://smartappli.io/
- Repository: https://github.com/Smartappli/DEALIoT
- Adoption playbook: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/adoption-playbook.md
- Demo pilot playbook: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/demo-pilot-playbook.md

We are looking for evaluators with one concrete field data source and one measurable output.
```

## First GitHub Discussion

Use `docs/community/first-github-discussion.md` for the first public Discussion. Recommended category: Announcements. Fallback category: General, then Show and tell.

Title:

```text
Show DEALIoT: production-oriented IoT data architecture from MQTT to governed data products
```

The discussion body should ask for one concrete use case, one evaluation blocker, or one integration proposal. It should also link to:

- Repository: https://github.com/Smartappli/DEALIoT
- Website: https://smartappli.io/
- Quick evaluation path: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/quick-evaluation-path.md
- Use case catalog: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/use-case-catalog.md
- Contributor onboarding: https://github.com/Smartappli/DEALIoT/blob/main/docs/community/contributor-onboarding.md

If the discussion creates useful feedback, convert repeated blockers into documentation, tests, or scoped issues within the same week.

## Partner Outreach Email

```text
Subject: DEALIoT integration pilot with one concrete data source

Hello,

We are opening DEALIoT for evaluation as a production-oriented IoT data architecture.

The useful first step is not a broad platform discussion. It is a 30-day pilot around one data source, one event contract, and one measurable output.

Good pilot candidates include:

- MQTT telemetry from devices or gateways
- GPS or sensor streams
- Media metadata flows
- Dataset publication through Zenodo or OpenAIRE
- Data governance and controlled sharing workflows

Repository:
https://github.com/Smartappli/DEALIoT

Pilot playbook:
https://github.com/Smartappli/DEALIoT/blob/main/docs/community/demo-pilot-playbook.md

If this is relevant, please reply with the data source, expected output, deployment target, and decision timeline.
```

## Conference Or Meetup Abstract

```text
From IoT pilot to governed data product: a production-oriented architecture with MQTT, Kafka, Flink, and compliance evidence

Many IoT pilots stop at ingestion. Production systems need schema governance, replay, object metadata, observability, operational state, and data-sharing evidence. This talk walks through DEALIoT, an open architecture that connects MQTT ingestion, Kafka, Apicurio, Flink, Beam, Airflow, and compliance topics into one reproducible validation path.

The session shows how to scope a 30-day pilot around one data source, one event contract, and one measurable output, then decide whether to harden, extend, or reject the architecture.
```

## README Badge Text

Use this phrase near links or social cards:

```text
Production-oriented IoT data architecture: MQTT -> Kafka -> schema governance -> stream processing -> governed data products.
```

## Call To Action Options

- Run the smoke test.
- Start a 30-day pilot.
- Open a Q&A discussion.
- Propose a device integration.
- Share a sanitized pilot report.
- Request managed hosting scope.

## Screenshots To Capture

Capture these after a representative smoke test or pilot:

- Architecture diagram.
- Smoke test output.
- Kafka topics or registry artifacts.
- Flink or Airflow view.
- Grafana or management console health view.
- Export manifest or compliance evidence payload.

Store public-safe screenshots under a future `assets/community/` folder in `https://github.com/Smartappli/DEALWebsite` only after checking that no secrets, endpoint values, or private data are visible.
