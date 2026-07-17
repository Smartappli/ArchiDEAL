# DEALIoT Management Console

Internal web console for operating the DEALIoT platform.

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
