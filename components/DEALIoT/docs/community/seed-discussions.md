# Seed Discussions

Use these posts to seed the first community discussions after GitHub Discussions is enabled.

## Launch Discussion: Show DEALIoT

Category: Announcements. If Announcements is not available, use General. If neither exists, use Show and tell.

Use the exact title and body from `docs/community/first-github-discussion.md`.

The first reply should ask readers to choose one path:

- Try the quick evaluation path and report the first blocker.
- Propose one device, gateway, or data source integration.
- Share one production requirement that would decide adoption.
- Pick one mentored good-first issue.

## Q&A Seed: How do I validate DEALIoT locally?

Category: Q&A

```md
What is the shortest path to validate DEALIoT from a clean checkout?

Recommended path:

1. Read the platform scope in `README.md`.
2. Copy `.env.example` into a local environment file.
3. Start the local stack documented in the README.
4. Run the smoke test.
5. Capture commit SHA, commands, and sanitized logs if anything fails.

If you are blocked, reply with:

- Deployment target
- Commit SHA
- Command run
- Expected result
- Actual result
- Sanitized logs
```

## Ideas Seed: Which device integration should be prioritized first?

Category: Ideas

```md
We want device integrations to follow `docs/community/integration-partner-guide.md`.

A useful proposal should include:

- Device or producer type
- Payload examples, sanitized if needed
- Target Kafka topic
- Validation method
- Operational owner
- Why this integration matters for adoption

Which integration should be prioritized first, and what evidence would prove it is useful?
```

## Show And Tell Seed: Share a 30-day pilot result

Category: Show and tell

```md
If you run a pilot, share a sanitized summary here.

Useful structure:

- Data source
- Deployment target
- First useful event achieved or not
- Dashboard, export, or operational outcome
- Production gaps
- Documentation gaps
- Whether the result can be referenced publicly

Do not include secrets, customer data, raw personal data, or private endpoints.
```

## Pilot Report Seed: What should a good pilot prove?

Category: Pilot report

```md
A strong DEALIoT pilot should prove one concrete outcome in 30 days:

- One data source enters the platform.
- One event contract is clear.
- One dashboard, export, or operational decision is produced.
- One scorecard is completed.
- Production gaps are visible enough to decide the next step.

Use `docs/community/demo-pilot-playbook.md` and `docs/community/validation-scorecard.md`.
```
