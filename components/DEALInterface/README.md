# DEALInterface

DEALInterface is the unified management console for the DEAL suite.

It is designed as a modular control plane:

- `DEALHost` keeps hosting, gateway and runtime operations isolated.
- `DEALIot` keeps device, telemetry and edge operations isolated.
- `DEALData` keeps ingestion, catalog and lineage operations isolated.
- `DEALInterface` centralizes IAM, RBAC, audit, billing, support and operator workflows.

## Stack

- Vite
- React
- TypeScript
- CSS modules through a single global stylesheet for the first UI foundation

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
npm run build
```

Unit tests cover runtime API probe classification and authentication behavior. Integration tests render
the React console with mocked DEALHost, DEALIoT and DEALData endpoints to verify that live connection
state reaches the UI. GitHub Actions runs the same typecheck, test and build commands on pull requests
and pushes to `main`.

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

`VITE_DEALIOT_MANAGEMENT_TOKEN` is supported for local development when DEALIoT protects `/api/*`
with `MANAGEMENT_CONSOLE_TOKEN`. Do not expose production secrets through `VITE_*` variables.

Default values are defined in `src/config/moduleRegistry.ts` and `vite.config.ts`.

## Current scope

This first version provides:

- a responsive management shell;
- global platform metrics;
- module navigation for `DEALHost`, `DEALIot` and `DEALData`;
- active module detail panels;
- control-plane topology;
- operator action queue with active-module focus;
- module control profiles with operating facts and workflow cards;
- live API connection probes for `DEALHost`, `DEALIot` and the three `DEALData` layers;
- shared workflow and activity sections;
- runtime endpoint configuration ready for API integration.

Operational metrics remain mocked until the backend dashboard contracts are finalized; connectivity
and health state now come from the live module APIs when they are running.
