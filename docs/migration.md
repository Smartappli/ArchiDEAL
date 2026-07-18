# Monorepo migration record

## Import decision

ArchiDEAL was empty at migration time. The four source repositories were imported as component
snapshots under their existing names. `sources.lock.json` records each source repository, commit and
tree SHA. DEALWebsite was explicitly excluded.

The GitHub connector can create trees and commits but cannot push Git packfiles, so the target commit
does not contain the complete historical commit graphs. The original repositories remain the
authoritative history for all pre-migration changes and must stay accessible.

## Cutover status

The bootstrap was merged in ArchiDEAL pull request #1. The four former source repositories now keep
only a redirect README on `main`; their earlier commits remain the authoritative pre-migration
history. New code, issues, releases, image automation and coordinated changes belong in ArchiDEAL.

Before the first production tag:

1. protect `main` and require component, architecture, security and production-manifest checks;
2. build and attest every release image once, then promote the same digests;
3. pass the root integration smoke and the production acceptance gates;
4. record backup restoration and rollback evidence for the target environment.

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
