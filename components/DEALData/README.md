# DEALData

DEALData regroupe les services Django qui portent les donnees metier de la
plateforme DEAL.

| Couche | Port local | Role |
| --- | ---: | --- |
| `core_layer` | `7000` | Projets, membres, objets observes et experiences. |
| `gps_layer` | `7001` | Capteurs GPS, donnees GPS brutes, positions traitees et evenements WildFi `raw.gps`. |
| `sensor_layer` | `7002` | Capteurs generiques, mesures associees et evenements WildFi `raw.sensor`. |

Le depot est prevu comme fournisseur de donnees pour `Smartappli/DEALIoT` et
comme ensemble de modules deployables derriere `Smartappli/DEALHost`.

## Architecture

Le depot contient trois services Django deployables separement. Chaque couche
utilise sa propre base PostgreSQL en Docker:

- `core-db` pour `core_layer`.
- `gps-db` pour `gps_layer`.
- `sensor-db` pour `sensor_layer`.

Les couches GPS et Sensor ne declarent pas de foreign keys SQL vers la base
Core. Les liens vers les objets observes sont conserves sous forme d'UUID
(`observed_object_id`) geres par `core_layer`.

Les donnees WildFi arrivent via les contrats DEALIoT suivants:

- `raw.gps` vers `gps_data.WildFiGPSFix`.
- `raw.sensor` vers `sensor_data.WildFiDecodedSensorEvent`.

Ces tables conservent l'enveloppe DEALIoT (`device_id`, `timestamp`,
`source`, `mqtt_topic`, `ingested_at`) avec le payload decode, les metadonnees
de transport et les champs utiles a l'idempotence (`event_id`, `payload_hash`).

Deux modes d'integration sont supportes:

- Push HTTP depuis un service externe vers les endpoints `/api/ingest/wildfi/...`.
- Consommation Kafka directe des topics DEALIoT `raw.gps` et `raw.sensor` via les
  workers Django `consume_dealiot_kafka`.

Le mode Kafka constitue le chainon direct `DEALIoT -> DEALData`: les workers
lisent les messages JSON produits par DEALIoT et les persistent dans les memes
chemins d'ingestion idempotents que l'API HTTP.

## Prerequis

- Python `>=3.14`.
- Docker et Docker Compose pour l'environnement PostgreSQL local.
- PowerShell pour les commandes ci-dessous.

## Installation locale

Depuis la racine du depot:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r core_layer\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r gps_layer\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r sensor_layer\requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest pytest-django pytest-cov
```

Le fichier `pyproject.toml` centralise aussi les versions ciblees, mais
l'installation editable du depot n'est pas active tant que le packaging
multi-couches n'est pas configure explicitement.

## Verification locale

Depuis la racine du depot, avec les dependances installees dans `.venv`:

```powershell
.\scripts\validate.ps1
# Ou une seule couche : .\scripts\validate.ps1 -Layer gps
```

La commande execute la compilation, les verifications Django, la detection de
migrations manquantes et les tests de la ou des couches choisies. Les commandes
equivalentes sont:

```powershell
.\.venv\Scripts\python.exe -m compileall -q core_layer gps_layer sensor_layer
cd core_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=core.settings -q
cd ..\gps_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=gps.settings -q
cd ..\sensor_layer; ..\.venv\Scripts\python.exe manage.py check; ..\.venv\Scripts\python.exe -m pytest . --ds=sensor.settings -q
cd ..
```

Pour appliquer les migrations localement dans une couche:

```powershell
cd core_layer
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py createsuperuser
cd ..
```

Adapter le dossier et le module settings pour `gps_layer` ou `sensor_layer` si
necessaire.

## Execution avec PostgreSQL

L'environnement Docker local demarre les trois services avec une base
PostgreSQL dediee par couche:

```powershell
Copy-Item .env.example .env
# Renseigner les cles Django, mots de passe PostgreSQL et DEALDATA_INGEST_TOKEN.
docker compose up --build
```

Endpoints de sante et d'observabilite:

- `GET http://localhost:7000/health/live/`
- `GET http://localhost:7000/health/ready/`
- `GET http://localhost:7000/metrics/`
- `GET http://localhost:7001/health/live/`
- `GET http://localhost:7001/health/ready/`
- `GET http://localhost:7001/metrics/`
- `GET http://localhost:7002/health/live/`
- `GET http://localhost:7002/health/ready/`
- `GET http://localhost:7002/metrics/`

Endpoints WildFi:

- `GET http://localhost:7001/api/wildfi/gps/`
- `POST http://localhost:7001/api/ingest/wildfi/gps/`
- `POST http://localhost:7001/api/ingest/wildfi/gps/batch/`
- `GET http://localhost:7002/api/wildfi/sensor/`
- `POST http://localhost:7002/api/ingest/wildfi/sensor/`
- `POST http://localhost:7002/api/ingest/wildfi/sensor/batch/`

Les endpoints d'ingestion acceptent le header
`X-DEALDATA-INGEST-TOKEN` quand `DEALDATA_INGEST_TOKEN` est defini.
En Docker local, cette variable doit etre renseignee dans `.env`.

Pour connecter directement DEALData aux topics Kafka DEALIoT:

```powershell
docker compose --profile dealiot up --build
```

Ce profil demarre deux workers supplementaires:

- `gps-dealiot-consumer`: consomme `raw.gps` et alimente `WildFiGPSFix`.
- `sensor-dealiot-consumer`: consomme `raw.sensor` et alimente
  `WildFiDecodedSensorEvent`.

Par defaut, les workers cherchent Kafka sur
`kafka1:9092,kafka2:9092,kafka3:9092`. Adapter
`DEALDATA_KAFKA_BOOTSTRAP_SERVERS` si DEALIoT expose d'autres endpoints.
Pour un cluster securise, configurer `DEALDATA_KAFKA_SECURITY_PROTOCOL` sur
`SASL_SSL`, les identifiants SASL et les chemins des certificats SSL decrits
dans `.env.example`. Les variables generiques `KAFKA_*` de DEALIoT sont aussi
acceptees comme valeurs de repli.

## Contrats d'ingestion

Exemple minimal `raw.gps`:

```json
{
  "event_id": "gps-event-1",
  "device_id": "wildfi-17",
  "timestamp": "2026-05-24T12:30:00Z",
  "source": "wildfi-mqtt",
  "mqtt_topic": "wildfi/wildfi-17/gps",
  "latitude": 50.6333,
  "longitude": 5.5667,
  "altitude_m": 121.5,
  "speed_m_s": 1.8,
  "heading_deg": 84.5,
  "payload": {
    "fix": 3,
    "hdop": 0.9
  }
}
```

Exemple minimal `raw.sensor`:

```json
{
  "event_id": "sensor-event-1",
  "device_id": "wildfi-17",
  "timestamp": "2026-05-24T12:30:00Z",
  "source": "wildfi-mqtt",
  "mqtt_topic": "wildfi/wildfi-17/sensor",
  "payload": {
    "sensor_type": "temperature",
    "value": 18.5,
    "unit": "C"
  }
}
```

Les endpoints batch acceptent soit un tableau JSON, soit un objet
`{"events": [...]}`.

Compatibilite champs DEALIoT:

- `altitude_m`, `speed_m_s` et `heading_deg` sont acceptes et normalises vers
  les colonnes `altitude`, `speed` et `heading`.
- Les anciens alias `alt`, `course`, `lat`, `lon` et `lng` restent acceptes.
- Pour `raw.sensor`, `sensor_type` est determine dans cet ordre: champ
  explicite top-level, `payload.sensor_type`, `payload.type`, suffixe
  `mqtt_topic` connu (`imu`, `environment`, `proximity`, `movement`,
  `metadata`, etc.), puis heuristiques sur les cles du payload.

Codes HTTP attendus:

- `201 Created`: evenement insere.
- `200 OK`: evenement deja connu ou batch traite.
- `400 Bad Request`: payload invalide.
- `403 Forbidden`: token d'ingestion invalide.

L'ingestion est idempotente. Si `event_id` est fourni, l'unicite est controlee
par couple `source` + `event_id`. Sinon, un `payload_hash` stable est calcule
sur le contenu de l'evenement.

## Lecture des evenements

Les endpoints de lecture acceptent des filtres par device et intervalle
temporel:

```powershell
Invoke-RestMethod "http://localhost:7001/api/wildfi/gps/?device_id=wildfi-17&from=2026-05-24T12:00:00Z&to=2026-05-24T13:00:00Z&limit=10"
Invoke-RestMethod "http://localhost:7002/api/wildfi/sensor/?device_id=wildfi-17&sensor_type=temperature&from=2026-05-24T12:00:00Z&to=2026-05-24T13:00:00Z&limit=10"
```

## Production

Renseigner les variables de `.env.example`, puis lancer avec l'override:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

Avec la consommation Kafka DEALIoT:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile dealiot up --build
```

Variables obligatoires en production:

- `CORE_DJANGO_SECRET_KEY`, `GPS_DJANGO_SECRET_KEY`,
  `SENSOR_DJANGO_SECRET_KEY`.
- `CORE_DJANGO_ALLOWED_HOSTS`, `GPS_DJANGO_ALLOWED_HOSTS`,
  `SENSOR_DJANGO_ALLOWED_HOSTS`.
- `CORE_DATABASE_HOST`, `GPS_DATABASE_HOST`, `SENSOR_DATABASE_HOST`.
- `CORE_DATABASE_USER`, `GPS_DATABASE_USER`, `SENSOR_DATABASE_USER`.
- `CORE_DATABASE_PASSWORD`, `GPS_DATABASE_PASSWORD`,
  `SENSOR_DATABASE_PASSWORD`.
- `DEALDATA_INGEST_TOKEN` pour les endpoints d'ingestion GPS et Sensor.

Le demarrage d'un conteneur de production execute `python manage.py check
--deploy` avant les migrations. Il exige HTTPS, HSTS et un jeton d'ingestion
pour les services GPS et Sensor.

Variables optionnelles ou avec valeur par defaut:

- `CORE_DATABASE_NAME`, `GPS_DATABASE_NAME`, `SENSOR_DATABASE_NAME`.
- `DEALDATA_KAFKA_BOOTSTRAP_SERVERS`,
  `DEALDATA_KAFKA_AUTO_OFFSET_RESET`, `DEALDATA_KAFKA_MAX_RECORDS`,
  `DEALDATA_KAFKA_POLL_TIMEOUT_MS`.
- `DEALDATA_KAFKA_SECURITY_PROTOCOL`, `DEALDATA_KAFKA_SASL_MECHANISM`,
  `DEALDATA_KAFKA_SASL_USERNAME`, `DEALDATA_KAFKA_SASL_PASSWORD`.
- `DEALDATA_KAFKA_SSL_CAFILE`, `DEALDATA_KAFKA_SSL_CERTFILE`,
  `DEALDATA_KAFKA_SSL_KEYFILE`, `DEALDATA_KAFKA_SSL_CHECK_HOSTNAME`.
- `DEALDATA_GPS_KAFKA_TOPIC`, `DEALDATA_GPS_KAFKA_GROUP_ID`,
  `DEALDATA_SENSOR_KAFKA_TOPIC`, `DEALDATA_SENSOR_KAFKA_GROUP_ID`.
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`,
  `SENTRY_SEND_DEFAULT_PII`.
- `DJANGO_SECURE_SSL_REDIRECT` (defaut `true`),
  `DJANGO_SECURE_HSTS_SECONDS` (defaut `31536000`) et
  `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` et
  `DJANGO_SECURE_HSTS_PRELOAD` (defaut `true`).

En production, `DJANGO_DEBUG=false` est impose par `docker-compose.prod.yml`.
Les valeurs numeriques invalides sont rejetées au demarrage avec un message
explicite : `DATABASE_CONN_MAX_AGE` et `DJANGO_SECURE_HSTS_SECONDS` doivent
etre des entiers non negatifs, et `SENTRY_TRACES_SAMPLE_RATE` doit etre compris
entre `0` et `1`.

## Notes d'exploitation

- Les metriques exposees par `/metrics/` utilisent un format compatible
  Prometheus.
- Les migrations doivent etre appliquees par couche avant ouverture du trafic.
- `.env.example` contient les variables attendues avec des valeurs vides.
  Renseigner `.env` localement ou via le gestionnaire de secrets de
  l'environnement cible.
- `docker-compose.dev.yml` et `docker-compose.staging.yml` sont actuellement
  vides. Ils ne modifient donc pas le comportement tant qu'ils ne sont pas
  completes.
