# ADR 0003: Trust and tenancy boundary

- Status: accepted
- Date: 2026-07-10

## Context

The current deployment uses one Kubernetes namespace and shared Kafka, registry, storage, and
orchestration endpoints. It does not enforce hard tenant isolation.

## Decision

One DEALIoT deployment is one organisational trust domain. Production is single-tenant at the
platform boundary. Separate organisations require separate namespaces, service identities, Kafka
ACL scopes, buckets, encryption keys, and preferably separate clusters or accounts.

OIDC roles control human access inside a trust domain, but they are not a substitute for tenant
isolation.

## Consequences

- No `tenant_id` is required in the version 1 event envelope.
- A future multi-tenant product requires a new ADR and threat model before shared deployment.
