# ArchiDEAL architecture

## Scope

ArchiDEAL brings the four operational DEAL repositories into one change boundary. The component
directories retain their internal structure so upstream documentation, Dockerfiles, and tests remain
recognizable. Root assets define only cross-component contracts and the compact integration stack.

DEALWebsite stays independent because it is a public static marketing PWA and has no operational
request-path dependency on the platform.

## Runtime contracts

| Producer | Transport | Consumer | Contract |
| --- | --- | --- | --- |
| MQTT devices | MQTT | DEALIoT bridge | `devices/#` and `wildfi/#` topics |
| DEALIoT bridge | Kafka | DEALData GPS consumer | `raw.gps` envelope |
| DEALIoT bridge | Kafka | DEALData Sensor consumer | `raw.sensor` envelope |
| DEALInterface | HTTP, same origin | APISIX | `/dealhost`, `/dealiot`, `/dealdata/*` |
| DEALHost | HTTP Admin API | APISIX | idempotent route PUTs |
| APISIX | HTTP | component services | prefix removed by `proxy-rewrite`; the trusted edge scheme is preserved in `X-Forwarded-Proto` |

DEALData persists Kafka messages through the same ingestion functions as its HTTP ingestion APIs.
Idempotency is based first on `source + event_id` and then on the normalized payload hash.

## Network boundaries

| Network | Members | Purpose |
| --- | --- | --- |
| `edge` | APISIX, DEALInterface | browser-facing request path |
| `api` | APISIX, DEALHost, DEALIoT console/bridge, DEALData APIs | private HTTP upstreams |
| `event` | Kafka, DEALIoT bridge/console, DEALData consumers | event transport |
| `ingest` | VerneMQ, DEALIoT bridge/console, smoke client | MQTT ingestion |
| `data` | DEALData services, consumers, PostgreSQL | persistence |
| `host` | DEALHost, Valkey, NATS, APISIX, APISIX etcd/bootstrap | hosting control plane |

All networks except `edge` are internal. Databases, brokers, the APISIX Admin API, and service ports
are not published on the host.

## Gateway model

APISIX runs in traditional mode backed by a dedicated etcd instance. This is deliberate: DEALHost
publishes individual routes through `/apisix/admin/routes/{id}`, which is incompatible with
file-driven standalone mode. The one-shot bootstrap establishes the initial routes; later DEALHost
updates retain exact and wildcard paths plus the prefix-removal plugin.

The Admin API is reachable only on the internal `host` network. Its key is generated locally and is
never committed.

## Compact versus full IoT deployment

The root stack includes the IoT ingress path, Kafka and the management console, not the full
high-availability DEALIoT topology. The original full Compose, Kubernetes and Swarm assets remain in
`components/DEALIoT`. They cover multi-broker Kafka, clustered MQTT, Flink, Beam, Airflow, Apicurio,
SeaweedFS and observability, and require their own production capacity and secrets review.

The compact stack is the mandatory cross-component integration gate. Production uses the separate
root Kubernetes baseline in `deploy/kubernetes`; it does not inherit the development brokers,
databases or credentials from Compose.

## Production trust boundaries

The supported production profile is a private, operator-only, single-tenant control plane:

1. an Ingress controller terminates TLS from the public network;
2. oauth2-proxy completes OIDC Authorization Code flow and admits only the configured operator
   group;
3. APISIX accepts data-plane traffic only from oauth2-proxy and exposes no public Admin API;
4. NetworkPolicies allow each workload only the upstreams it owns;
5. Kafka, MQTT, PostgreSQL, Valkey and etcd are external HA services using authenticated TLS;
6. External Secrets Operator projects short-lived or rotated credentials into restricted pods;
7. APISIX exports metrics and traces to the configured monitoring plane.

Anonymous or multi-tenant access is not part of this profile. It requires application-level tenant
identity and resource authorization in every component before exposure.
