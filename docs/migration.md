# Monorepo migration record

## Import decision

ArchiDEAL was empty at migration time. The four source repositories were imported as component
snapshots under their existing names. `sources.lock.json` records each source repository, commit and
tree SHA. DEALWebsite was explicitly excluded.

The GitHub connector can create trees and commits but cannot push Git packfiles, so the target commit
does not contain the complete historical commit graphs. The original repositories remain the
authoritative history for all pre-migration changes and must stay accessible.

## Cutover sequence

1. Review and merge the ArchiDEAL bootstrap pull request.
2. Protect `main` and require the root component and architecture checks.
3. Move coordinated issues and release planning to ArchiDEAL.
4. Mark the four source repositories read-only or convert them to documented mirrors only after all
   consumers, webhooks and package/image automation use ArchiDEAL.
5. Do not accept independent source changes unless an explicit backport/forward-port procedure is
   used; otherwise the copies will diverge.
6. Tag the first compatibility-tested ArchiDEAL release only after the root smoke test passes.

## Directory ownership

| Path | Primary concern |
| --- | --- |
| `components/DEALIoT` | ingestion, event schemas, processing and IoT platform |
| `components/DEALHost` | hosting metadata, discovery, IAM and gateway control |
| `components/DEALData` | persistence, governance and read/ingestion APIs |
| `components/DEALInterface` | same-origin operator experience |
| `compose.yaml`, `deploy/`, `scripts/` | cross-component compatibility and deployment |

Any change to a Kafka envelope, public prefix, upstream name, auth rule or health path must update the
producer, consumer, gateway, interface, smoke test and documentation in the same pull request.
