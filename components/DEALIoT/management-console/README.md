# DEALIoT Management Console

Internal web console for operating the DEALIoT platform.

The unified gateway publishes the console below `/dealiot`; its static assets and API client use
that stable prefix. The embedded HTTP server accepts both prefixed requests and internal
prefix-stripped requests from APISIX.

It exposes:

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
`MANAGEMENT_CONSOLE_PRODUCTION_MODE=true` and configure either `MANAGEMENT_CONSOLE_TOKEN` or
`MANAGEMENT_CONSOLE_OIDC_INTROSPECTION_URL` with its HTTPS issuer, audience, client credentials and
role mappings. Production startup rejects an incomplete OIDC boundary. Introspection responses must
be active and match both `MANAGEMENT_CONSOLE_OIDC_ISSUER` and
`MANAGEMENT_CONSOLE_OIDC_AUDIENCE`.

Production mode fails closed when authentication is missing. Only `GET /healthz` remains anonymous
for orchestrator probes; static assets, API reads, and all write operations require an authorized
bearer token. Prefer OIDC for production and reserve the static token for controlled migrations.
