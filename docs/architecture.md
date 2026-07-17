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
| APISIX | HTTP | component services | prefix removed by `proxy-rewrite` |

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

The compact stack is the mandatory cross-component integration gate. A full production profile can
be added only after it passes the same root contracts and smoke scenario.
