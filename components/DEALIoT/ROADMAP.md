# Roadmap

This roadmap is organized around adoption risk. Dates are intentionally not promised in the repository; work is prioritized by user evidence, pilot demand, and production readiness impact.

## Now

- Keep the local smoke path reliable from a clean checkout.
- Publish the static website through GitHub Pages.
- Maintain production deployment guardrails for Kubernetes and Swarm.
- Keep community, support, security, and pilot documentation current.

## Next

- Add a minimal public demo dataset and fixture narrative.
- Add benchmark notes for ingest latency, DLQ behavior, and replay/backfill throughput.
- Add architecture diagrams that can be reused in presentations and partner documentation.
- Expand partner integration examples for device adapters and data exports.
- Document a repeatable DealHost deployment package for managed environments.

## Later

- Add optional managed-service deployment profiles for common cloud and sovereign-host environments.
- Add signed image admission policy examples.
- Evaluate Rust rewrites for hot-path ingestion components where profiling proves material safety or performance benefit.
- Publish approved adopter stories and operational case studies.

## Not Planned Without Evidence

- Rewriting working Python components in Rust without profiling or security evidence.
- Adding vendor-specific services to the default production manifest.
- Claiming compliance certification from templates alone.
- Listing customers, partners, or adopters without written approval.
