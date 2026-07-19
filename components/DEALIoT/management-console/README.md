# DEALIoT Management Console

Internal web console for operating the DEALIoT platform.

The unified gateway publishes the console below `/dealiot`; its static assets and API client use
that stable prefix. The embedded HTTP server accepts both prefixed requests and internal
prefix-stripped requests from APISIX.

It exposes:

- a persistent PostgreSQL device registry and role-protected configuration API,
- platform topology and component ownership,
- HTTP/TCP health probes from inside the Compose or Kubernetes networks,
- Kafka topic and data classification inventory,
- dataset catalogue, FAIR metadata and Data Management Plan controls,
- Zenodo dataset draft export with DMP manifest and publication gates,
- OpenAIRE/DataCite metadata package export for PROVIDE or OAI-PMH exposure,
- DGA data products, access/permission evidence topics and readiness controls,
- Data Act connected-product catalogue, user access and third-party sharing controls,
- intermediation flow between raw data, applications and scientists,
- research project, ethics and output disclosure controls,
- NIS2, DORA and CRA security/resilience evidence gates,
- regulatory scope decisions, control assessments and reporting channels,
- legal compliance dossier artefacts, templates and release gates,
- legal finalization status separating repository completion from human approvals,
- adjacent-legislation matrix for GDPR, ePrivacy, AI Act, product, open-data and EHDS scope,
- runbook and operation catalogue,
- compliance-control tracking for GDPR, Data Act, DGA, AI Act, CRA and NIS2.

The console intentionally does not mount the Docker socket. Host-level start/stop/restart remains a
CLI or orchestrator responsibility.

## Authentication boundary

Development keeps the historical local behavior: when neither a bearer token nor OIDC is configured,
the console is accessible without authentication. Production deployments must set
`MANAGEMENT_CONSOLE_PRODUCTION_MODE=true`, `MANAGEMENT_CONSOLE_PUBLIC_ORIGIN` to the exact HTTPS
public origin, and `MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL` with its HTTPS issuer, audience,
client credentials and group mappings. Authorization groups are read only from the top-level claim
named by `MANAGEMENT_CONSOLE_OIDC_GROUPS_CLAIM` (default: `groups`); `scope`/`scp`, `roles` and
`realm_access.roles` never grant console access. Production startup rejects an incomplete or
ambiguous OIDC boundary. Introspection responses must be active and match both
`MANAGEMENT_CONSOLE_OIDC_ISSUER` and `MANAGEMENT_CONSOLE_OIDC_AUDIENCE`.

Production mode fails closed when authentication is missing. Only `GET /healthz` and `GET /readyz`
remain anonymous for orchestrator probes; Kubernetes NetworkPolicy and service routing must keep
them on the internal network. Static assets, API reads, and all write operations require an
authorized OIDC bearer token. `MANAGEMENT_CONSOLE_TOKEN` is rejected in production and remains a
local-development compatibility option only; database migrations use their separate PostgreSQL
role and CLI.

An authenticated principal without a sufficient mapped group receives `403`; a missing or invalid
bearer token receives `401`. Device registry reads require a configured read group. Creates,
updates and retirements require a write group.

Browser mutations carrying an `Origin` header must exactly match
`MANAGEMENT_CONSOLE_PUBLIC_ORIGIN`; bearer-authenticated service and CLI clients without `Origin`
remain supported. JSON `POST` and `PATCH` requests require `Content-Type: application/json`
(parameters such as `charset=utf-8` are accepted). These checks complement, rather than replace,
OIDC authorization and the gateway's same-origin routing policy.

## Device registry API

The same-origin public API is available below `/dealiot/api/devices`; APISIX strips the
`/dealiot` prefix before forwarding requests to the console.

| Operation | Endpoint | Role |
|---|---|---|
| List and filter | `GET /api/devices?status=&kind=&q=&limit=&cursor=` | read |
| Register | `POST /api/devices` | write |
| Inspect | `GET /api/devices/{device_id}` | read |
| Update | `PATCH /api/devices/{device_id}` | write |
| Retire | `DELETE /api/devices/{device_id}` | write |

Detail and mutation responses carry an `ETag` derived from the device revision. `PATCH` and
`DELETE` require that value in `If-Match`; a stale revision returns `412` and an omitted header
returns `428`. Deletion is a logical retirement: retired devices are excluded from normal reads,
and this initial API does not expose a restore operation. A conservative key-name denylist rejects
common secret-shaped fields in settings and labels, including API keys, authentication material,
bearer tokens, passwords and private keys. This is not a secret scanner: use opaque references in
the registry and keep every secret value in the deployment secret manager.

## PostgreSQL and migrations

The registry requires these environment variables:

```text
DEALIOT_REGISTRY_DATABASE_HOST
DEALIOT_REGISTRY_DATABASE_PORT=5432
DEALIOT_REGISTRY_DATABASE_NAME=dealiot_registry
DEALIOT_REGISTRY_DATABASE_USER=dealiot_registry
DEALIOT_REGISTRY_DATABASE_PASSWORD
DEALIOT_REGISTRY_DATABASE_SSLMODE=verify-full
DEALIOT_REGISTRY_DATABASE_SSLROOTCERT=/path/to/postgres-ca.crt
```

Run migrations as a separate release step before starting or rolling the console:

```bash
python -m management_console.migrate
```

The runner serializes concurrent attempts with a PostgreSQL advisory lock and refuses to continue
if an already-applied migration file changes. Before any DDL, it verifies that the migration role
has `USAGE` and `CREATE` and owns (directly or through role membership) the `public` schema; this is
required to revoke all ambient `PUBLIC` privileges safely. The serving role must remain a separate
non-owner with schema `USAGE`, device `SELECT`/`INSERT`/`UPDATE`, and migration-ledger `SELECT` only:
retirement uses `UPDATE`, so it receives neither `DELETE` nor `TRUNCATE`. Effective privileges are
verified after grants, including privileges inherited from other roles. The root ArchiDEAL Compose
stack provides a dedicated PostgreSQL service and runs this step automatically. Production must
provision the database, roles, TLS trust, backup and restore policy outside the application
container.

`GET /readyz` verifies the registry connection, the device table and every migration packaged in
the running image whenever the database is configured. For expand/contract rollbacks it accepts
only a well-formed, strictly ordered suffix of newer applied migrations; every migration known to
the running image must still be present in packaged order with its exact checksum. It also verifies
the required column/constraint/index fingerprint, performs a real device-table `SELECT`, and in
production rejects schema ownership, inherited `CREATE`, `DELETE`, `TRUNCATE` or other excess
runtime privileges. This tolerance does not make destructive migrations rollback-safe: retain
additive columns/tables until every supported application version is outside the rollback window.
Production mode also requires this check when the database variables are absent, so a deployment
cannot become ready without its registry. `GET /healthz` remains a process-liveness check and does
not prove registry availability.

The registry records configuration metadata only. It does not create MQTT credentials, change
VerneMQ ACLs or reconfigure the MQTT-Kafka bridge dynamically.
