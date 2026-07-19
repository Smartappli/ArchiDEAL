# DEALInterface

DEALInterface is the unified management console for the DEAL suite.

It is designed as a modular control plane:

- `DEALHost` owns the application catalog, immutable version metadata, APISIX route publication and health probes.
- `DEALIoT` keeps device, telemetry and edge operations isolated.
- `DEALData` keeps ingestion, catalog and lineage operations isolated.
- `DEALInterface` provides unified navigation for the management API contracts that are actually exposed.

DEALHost does not currently build, schedule or deploy application runtimes, manage domains, expose
runtime logs or enforce tenant quotas. Those capabilities remain explicit future contracts rather
than simulated controls in the console.

## Stack

- Vite
- React
- TypeScript
- a single responsive global stylesheet for the current UI foundation

## Local development

```bash
npm install
npm run dev
```

The app starts on `http://127.0.0.1:5173`.

## Tests and CI

```bash
npm run typecheck
npm run test:unit
npm run test:integration
npm run test:coverage

# Avec le serveur de prévisualisation lancé sur le port 4173
python3 -m pip install -r requirements-e2e.txt
npm run test:selenium
npm run build
```

Unit tests cover runtime probes, the same-origin management client, authentication failures and API
error normalization. Integration tests render the React console against controlled DEALHost,
DEALIoT and DEALData responses and verify navigation, reads and mutations without exposing bearer
tokens to browser code. GitHub Actions runs the same typecheck, test and build commands on pull
requests and pushes to `main`.

## Local module services

Start the module APIs in their own repositories before expecting live probes to pass:

```powershell
cd D:\projects\DEALHost
docker compose up

cd D:\projects\DEALIoT
docker compose -f docker-compose.yml -f docker-compose.dev.yml up management-console

cd D:\projects\DEALData
docker compose up core gps sensor
```

If a service is stopped, DEALInterface keeps rendering the console and marks the related probe as
offline.

## API configuration

By default the Vite dev server proxies module calls through local paths:

```text
/dealhost       -> http://127.0.0.1:8000
/dealiot        -> http://127.0.0.1:8090
/dealdata/core  -> http://127.0.0.1:7000
/dealdata/gps   -> http://127.0.0.1:7001
/dealdata/sensor -> http://127.0.0.1:7002
```

Create `.env.local` only when the services run elsewhere:

```bash
VITE_DEALHOST_API_URL=/dealhost
VITE_DEALIOT_API_URL=/dealiot
VITE_DEALDATA_API_URL=/dealdata/core
VITE_DEALDATA_CORE_API_URL=/dealdata/core
VITE_DEALDATA_GPS_API_URL=/dealdata/gps
VITE_DEALDATA_SENSOR_API_URL=/dealdata/sensor

DEALHOST_PROXY_TARGET=http://127.0.0.1:8000
DEALIOT_PROXY_TARGET=http://127.0.0.1:8090
DEALDATA_CORE_PROXY_TARGET=http://127.0.0.1:7000
DEALDATA_GPS_PROXY_TARGET=http://127.0.0.1:7001
DEALDATA_SENSOR_PROXY_TARGET=http://127.0.0.1:7002
```

Authenticated module calls use the same-origin operator session. In production, oauth2-proxy/APISIX
must translate that HttpOnly session into the module bearer identity. Tokens must never be added to a
`VITE_*` variable because Vite embeds those values in the public browser bundle.

An Nginx Basic Auth prompt protects a staging URL but does not establish the OIDC identity or module
roles required by DEALHost. On a Basic-only VPS, public health probes work while applications,
datasets and IAM correctly return `401`; do not solve that by injecting one shared administrator
token for every browser. Configure the documented oauth2-proxy/OIDC boundary before enabling those
external management mutations.

Default values are defined in `src/config/moduleRegistry.ts` and `vite.config.ts`.

## Current scope

The current development build provides:

- a responsive management shell;
- a home page showing all `DEALHost`, `DEALIoT` and `DEALData` modules;
- dedicated, shareable workspaces selected from the left navigation, with canonical
  `#/modules/{module}/{area}` URLs that survive refresh and browser back/forward navigation;
- live API connection probes for `DEALHost`, `DEALIoT` and the three `DEALData` layers;
- persistent DEALIoT device registration, conditional configuration updates and confirmed retirement
  through `/dealiot/api/devices`, using strong revision ETags for every mutation and bounded
  server-side pagination/search instead of loading the complete registry into the browser;
- DEALHost application catalog creation, metadata updates and version publication guarded by the
  displayed strong revision ETag. Version metadata is never presented as a completed runtime
  deployment; a concurrent `412` keeps every entered release field visible until the operator
  explicitly reloads and reviews the authoritative application revision;
- read-only module route metadata, an APISIX `dry_run` preview and a separate confirmed route
  publication action bound to the preview's strong ETag through `If-Match`; changed or cross-module
  previews cannot authorize publication, and disabled modules cannot be previewed or published from
  the console;
- DEALData dataset creation, conditional metadata updates and access-list administration through
  the DEALHost control plane,
  using the staff-only minimal `/dealhost/api/hosting/dataset-principals/` contract instead of the
  superuser IAM catalog; explicit OIDC issuer/subject provisioning is shown only to DEALHost
  superusers and never collects credentials, client secrets, API keys or bearer tokens;
- explicit loading, empty, read-only, expired-session and API-error states.

The production UI does not claim that release metadata is a completed application deployment.
Deployment orchestration, domain lifecycle, telemetry/rules configuration, lineage, audit evidence,
billing and support remain unavailable until their owning services expose stable management API
contracts. The optional demo mode still contains synthetic metrics and operator workflow data; live
connectivity, device, application, route, dataset and access-right state comes from module APIs.

Dataset user/group lists currently control visibility of DEALHost catalog entries only. They are not
data-plane authorization for DEALData GPS or Sensor events and must not be used as evidence that
event access is protected; the owning DEALData APIs still need an explicit authorization contract.

This is development validation, not production approval. Production still requires a configured
OIDC provider and role mapping, TLS and external secrets at the edge, durable backed-up databases,
auditing, rate limits and the remaining evidence gates documented in the root production-readiness
guide.
