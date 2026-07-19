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

Endpoints d'administration scientifique:

- `GET/POST http://localhost:7000/api/experiments/` et
  `GET/PATCH/DELETE http://localhost:7000/api/experiments/{uuid}/` pour relier
  une experimentation a un projet Core et a une liste d'objets observes existants.
- `GET/POST http://localhost:7002/api/sensors/` et
  `GET/PATCH/DELETE http://localhost:7002/api/sensors/{uuid}/` pour les
  metadonnees `code`, `vendor` et `model` d'un senseur generique.
- `GET/POST http://localhost:7001/api/gps-sensors/` et
  `GET/PATCH/DELETE http://localhost:7001/api/gps-sensors/{uuid}/` pour les
  metadonnees d'un senseur GPS (`code`, date d'achat, frequence, fournisseur,
  modele, carte SIM et etat actif).

Ces routes exigent un utilisateur Django staff en developpement ou l'appartenance
au groupe OIDC administrateur en production. La suppression d'un senseur ou d'un
senseur GPS renvoie `409 Conflict` tant que des mesures, positions ou liens vers
des objets observes lui sont rattaches; aucune donnee scientifique n'est supprimee
en cascade par ce CRUD de metadonnees.

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
Ce jeton d'ingestion ne donne aucun acces aux routes de lecture ou
d'administration.

Les routes d'administration et les listes WildFi utilisent l'authentification
DRF par session/Basic pour un staff local, ou un bearer OIDC introspecte sans
creer d'utilisateur persistant. Le bearer doit etre actif et porter l'issuer,
l'audience, le sujet stable et le groupe administrateur attendus. Configurer:

- `DEALDATA_OIDC_INTROSPECTION_URL`, `DEALDATA_OIDC_ISSUER` et
  `DEALDATA_OIDC_AUDIENCE`;
- `DEALDATA_OIDC_CLIENT_ID` et `DEALDATA_OIDC_CLIENT_SECRET` via le gestionnaire
  de secrets;
- `DEALDATA_OIDC_GROUPS_CLAIM`, `DEALDATA_OIDC_READ_GROUPS`,
  `DEALDATA_OIDC_ADMIN_GROUPS` et `DEALDATA_OIDC_TIMEOUT_SECONDS`.

Les groupes de lecture et d'administration doivent etre non vides et distincts.
Les endpoints scientifiques documentes ci-dessus sont staff-only: appartenir
uniquement a un groupe de lecture ne suffit pas. Une configuration OIDC absente
ou incoherente echoue fermee pour toute requete bearer.

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

Dans le deploiement Kubernetes ArchiDEAL, chaque worker expose en interne le port
`9100`: `/healthz` ne verifie que le processus, `/readyz` exige un poll Kafka
recent et sain ainsi qu'une base joignable, et `/metrics` publie les
resultats, erreurs de poll/commit/base ainsi que les histogrammes de duree de
persistance et d'age de premier enregistrement. Les variables
`DEALDATA_CONSUMER_METRICS_PORT`, `DEALDATA_CONSUMER_STALE_AFTER_SECONDS` et
`DEALDATA_CONSUMER_DATABASE_CHECK_INTERVAL_SECONDS` permettent d'adapter ce
contrat. Les labels restent bornes a `service` et `result`; aucun identifiant
d'evenement ou de device n'est exporte. Un replica en attente sans partition
reste donc ready pour ne pas bloquer un RollingUpdate; la jauge
`dealdata_consumer_kafka_assigned` et l'alerte de capacite signalent uniquement
le cas ou aucun replica du service ne possede de partition.

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

Le preflight de production exige aussi `min.insync.replicas >= 2` et
`unclean.leader.election.enable=false` sur chaque topic runtime. Le compte Kafka utilise par le Job
doit donc disposer de `Describe`, `DescribeConfigs` et de la lecture des metadonnees, sans droit de
production ni de modification de topic.

## Lecture des evenements

Les endpoints de lecture sont reserves au staff et acceptent des filtres par
device et intervalle temporel. DEALInterface demande les 20 derniers resultats
avec `summary=true`:

```powershell
Invoke-RestMethod "http://localhost:7001/api/wildfi/gps/?device_id=wildfi-17&from=2026-05-24T12:00:00Z&to=2026-05-24T13:00:00Z&limit=20&summary=true"
Invoke-RestMethod "http://localhost:7002/api/wildfi/sensor/?device_id=wildfi-17&sensor_type=temperature&from=2026-05-24T12:00:00Z&to=2026-05-24T13:00:00Z&limit=20&summary=true"
```

En mode resume, GPS retourne uniquement `id`, `device_id`,
`observed_object_id`, `timestamp`, `latitude` et `longitude`; Sensor retourne
`id`, `device_id`, `observed_object_id`, `timestamp` et `sensor_type`. Le
`payload`, les metadonnees de transport et les autres champs detailles sont
omis de la reponse, et pas seulement masques par l'interface. Sans
`summary=true`, le contrat detaille historique reste disponible aux memes
administrateurs.

## Limites du perimetre de gestion

Ces API administrent les associations d'experimentation et les metadonnees des
senseurs. Elles ne fournissent pas de carte, de workflow d'import/acquisition en
masse, ni de configuration de routage ou de retention des mesures. Les
"datasets" visibles dans DEALInterface sont des entrees de catalogue DEALHost
et leurs ACL de visibilite; ils ne constituent ni un stockage DEALData ni une
ACL par ligne pour les evenements GPS/Sensor.

## Profil Compose durci

Ce profil sert aux validations locales ou de preproduction de DEALData. Il ne
constitue pas le deploiement de production unifie: celui-ci se fait depuis la
racine d'ArchiDEAL avec `deploy/kubernetes/`, comme decrit dans
`../../docs/deployment.md`.

Pour exercer le profil Compose avec la consommation Kafka DEALIoT, exporter les
variables documentees dans `.env.example` depuis le gestionnaire de secrets puis
lancer:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile dealiot up --build
```

Variables obligatoires pour ce profil durci:

- `CORE_DJANGO_SECRET_KEY`, `GPS_DJANGO_SECRET_KEY`,
  `SENSOR_DJANGO_SECRET_KEY`.
- `CORE_DJANGO_ALLOWED_HOSTS`, `GPS_DJANGO_ALLOWED_HOSTS`,
  `SENSOR_DJANGO_ALLOWED_HOSTS`.
- `CORE_DATABASE_HOST`, `GPS_DATABASE_HOST`, `SENSOR_DATABASE_HOST`.
- `CORE_DATABASE_USER`, `GPS_DATABASE_USER`, `SENSOR_DATABASE_USER`.
- `CORE_DATABASE_PASSWORD`, `GPS_DATABASE_PASSWORD`,
  `SENSOR_DATABASE_PASSWORD`.
- `DATABASE_SSLMODE=verify-full` et `DATABASE_SSLROOTCERT_SOURCE`, chemin de la
  CA PostgreSQL fournie par le gestionnaire de secrets.
- `DEALDATA_INGEST_TOKEN` pour les endpoints d'ingestion GPS et Sensor.
- `DEALDATA_KAFKA_BOOTSTRAP_SERVERS`,
  `DEALDATA_KAFKA_SASL_USERNAME`, `DEALDATA_KAFKA_SASL_PASSWORD` et
  `DEALDATA_KAFKA_SSL_CAFILE_SOURCE`.

Le demarrage d'un conteneur de production execute `python manage.py check
--deploy` avant les migrations. Il exige HTTPS, HSTS, PostgreSQL avec verification
du certificat et du nom d'hote, ainsi qu'un jeton d'ingestion pour les services
GPS et Sensor.

`docker-compose.prod.yml` monte les CA PostgreSQL et Kafka en lecture seule sous
`/run/secrets`. Il impose `SASL_SSL`, la verification du nom d'hote Kafka et des
identifiants SASL non vides. Les mots de passe doivent etre injectes dans
l'environnement du processus Compose par le gestionnaire de secrets; ils ne
doivent jamais etre ecrits dans `.env` ou dans le depot.

Variables optionnelles ou avec valeur par defaut:

- `CORE_DATABASE_NAME`, `GPS_DATABASE_NAME`, `SENSOR_DATABASE_NAME`.
- `DEALDATA_KAFKA_AUTO_OFFSET_RESET`, `DEALDATA_KAFKA_MAX_RECORDS`,
  `DEALDATA_KAFKA_POLL_TIMEOUT_MS`.
- `DEALDATA_KAFKA_SASL_MECHANISM` (defaut `SCRAM-SHA-512`).
- `DEALDATA_KAFKA_SSL_CERTFILE`, `DEALDATA_KAFKA_SSL_KEYFILE` pour une
  identite cliente TLS optionnelle hors du profil Compose standard.
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
- `.env.example` documente les variables attendues avec des valeurs vides. Un
  fichier `.env` peut etre utilise localement, mais les secrets de production
  doivent etre injectes par le gestionnaire de secrets sans fichier persistant.
- `docker-compose.dev.yml` et `docker-compose.staging.yml` sont actuellement
  vides. Ils ne modifient donc pas le comportement tant qu'ils ne sont pas
  completes.
