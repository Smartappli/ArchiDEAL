# DEALHost — Architecture d’hébergement modulaire (Django 6 + APISIX + GitHub)

Ce composant contient un socle **Django 6 ASGI** (servi par **Granian**) pour exposer une plateforme d’hébergement modulaire reliée au monorepo **`Smartappli/ArchiDEAL`**, pilotée via **Apache APISIX**.

[![CI Django DEALHost](https://github.com/Smartappli/DEALHost/actions/workflows/ci.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/ci.yml)
[![SDK Unit Tests](https://github.com/Smartappli/DEALHost/actions/workflows/sdk-unit-tests.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/sdk-unit-tests.yml)
[![Validate Hosting Manifests](https://github.com/Smartappli/DEALHost/actions/workflows/hosting-manifests-validate.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/hosting-manifests-validate.yml)
[![Validate APISIX Routes](https://github.com/Smartappli/DEALHost/actions/workflows/apisix-routes-validate.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/apisix-routes-validate.yml)
[![Pre-commit](https://github.com/Smartappli/DEALHost/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/pre-commit.yml)
[![CodeQL](https://github.com/Smartappli/DEALHost/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/codeql.yml)
[![Bandit](https://github.com/Smartappli/DEALHost/actions/workflows/bandit.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/bandit.yml)
[![OSV Scanner](https://github.com/Smartappli/DEALHost/actions/workflows/osv-scanner.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/osv-scanner.yml)
[![Codacy Security Scan](https://github.com/Smartappli/DEALHost/actions/workflows/codacy.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/codacy.yml)
[![Dependabot Updates](https://github.com/Smartappli/DEALHost/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/dependabot/dependabot-updates)
[![Renovate](https://github.com/Smartappli/DEALHost/actions/workflows/renovate.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/renovate.yml)
[![SonarCloud](https://github.com/Smartappli/DEALHost/actions/workflows/sonarcloud.yml/badge.svg)](https://github.com/Smartappli/DEALHost/actions/workflows/sonarcloud.yml)

[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=bugs)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=coverage)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=Smartappli_DEALHost&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=Smartappli_DEALHost)


## Objectif

- Découper l’hébergement en **modules activables** (`apps.hosting.Module`).
- Synchroniser l’état applicatif avec GitHub (`/api/gateway/github/sync/`).
- Publier dynamiquement les routes APISIX (`/api/gateway/apisix/publish/`).
- Recevoir un webhook GitHub et déclencher un routage (`/api/gateway/github/webhook/`).

## Architecture proposée

```text
GitHub (Smartappli/ArchiDEAL)
        │
        │ webhook / API
        ▼
Django 6 ASGI + Granian (dealhost)
 ├── apps.hosting  -> registre de modules déployables
 └── apps.gateway  -> orchestration GitHub + APISIX
        │
        │ Admin API
        ▼
Apache APISIX
        │
        ▼
Upstream modules (containers/services Django)
        │
        └── Valkey (cache Redis)
```

## Structure

- `dealhost/settings/` : configuration modulaire (`base`, `dev`, `prod`, `env`).
- `apps/hosting/` : domaine hébergement (modèles, API REST des modules).
- `apps/gateway/` : services d’intégration GitHub + APISIX et endpoints d’orchestration.
- `infra/apisix/` : exemple de route APISIX standalone.

## Endpoints clés

- `GET /api/gateway/health/` : état du service gateway.
- `POST /api/gateway/github/sync/` : récupère le dernier commit d’une branche du dépôt `Smartappli/ArchiDEAL`.
- `GET /api/gateway/github/repositories/` : liste les repositories intégrés, leurs événements autorisés, modules mappés et routes publiques déclarées.
- `POST /api/gateway/apisix/publish/` : crée/met à jour une route APISIX, avec `dry_run=true` pour prévisualiser le payload sans appel admin APISIX.
- `POST /api/gateway/github/webhook/` : webhook signé GitHub -> publication de route. Les en-têtes `X-Hub-Signature-256`, `X-GitHub-Event` et `X-GitHub-Delivery` sont requis ; une livraison est traitée au plus une fois pendant 24 h.
- `GET/POST /api/hosting/modules/` : CRUD des modules hébergés.
- `GET/POST /api/hosting/tools/` : CRUD des outils (chaque outil peut lier plusieurs modules).
- `GET/POST /api/hosting/applications/` : CRUD des applications hébergées (chaque application peut lier plusieurs modules).
- `POST /api/hosting/autodiscover/` : auto découverte depuis les manifests modules/tools/apps.
- `GET /hosting/manage/` : interface de gestion (modules, tools, datasets accessibles à l'utilisateur connecté, applications + auto découverte).
- `POST /i18n/setlang/` : changement de langue de l’interface de gestion.
- `GET/POST /api/iam/users/` : gestion des utilisateurs (avec groupes/permissions + endpoint `set-password`).
- `GET/POST /api/iam/groups/` : gestion des groupes (rôles) et permissions associées.
- `GET /api/iam/permissions/` : catalogue des permissions Django.
- `GET /iam/manage/` : interface IAM (utilisateurs, groupes, permissions).

### SDK R (tools et applications)

Un SDK R minimal est disponible dans `sdk/r/dealhostR` pour piloter l’API hosting.

Fonctions exposées :
- `dealhost_client(base_url, token)`
- `create_tool(...)`, `update_tool(...)`, `list_tools(...)`
- `create_application(...)`, `update_application(...)`, `list_applications(...)`

Exemple rapide :

```r
# install.packages(c("httr2", "jsonlite"))
source("sdk/r/dealhostR/R/client.R")

client <- dealhost_client("http://localhost:8000", token = "YOUR_TOKEN")

create_tool(
  client,
  name = "Backoffice",
  slug = "backoffice",
  description = "Outil d'administration",
  module_ids = c(1, 2),
  enabled = TRUE
)

create_application(
  client,
  name = "Storefront",
  slug = "storefront",
  description = "Application e-commerce",
  module_ids = c(1),
  enabled = TRUE
)
```


### SDK Python (tools et applications)

Le SDK Python est disponible dans `sdk/python`.

Exemple rapide :

```python
from dealhost_sdk import DealHostClient

client = DealHostClient("http://localhost:8000", token="YOUR_TOKEN")

client.create_tool(
    name="Backoffice",
    slug="backoffice",
    description="Outil d'administration",
    module_ids=[1, 2],
    enabled=True,
)

client.create_application(
    name="Storefront",
    slug="storefront",
    description="Application e-commerce",
    module_ids=[1],
    enabled=True,
)
```

### SDK Rust (tools et applications)

Le SDK Rust est disponible dans `sdk/rust/dealhost-sdk`.

Exemple rapide :

```rust
use dealhost_sdk::DealHostClient;

fn demo() -> Result<(), reqwest::Error> {
    let client = DealHostClient::new("http://localhost:8000", Some("YOUR_TOKEN".to_string()));

    client.create_tool("Backoffice", "backoffice", "Outil d'administration", vec![1, 2], true)?;
    client.create_application("Storefront", "storefront", "Application e-commerce", vec![1], true)?;
    Ok(())
}
```

### SDK Go (tools et applications)

Le SDK Go est disponible dans `sdk/go/dealhost-sdk`.

Exemple rapide :

```go
package main

import (
    "fmt"

    dealhostsdk "github.com/dealiot/dealhost-sdk-go"
)

func main() {
    client := dealhostsdk.NewClient("http://localhost:8000", "YOUR_TOKEN")
    resp, err := client.CreateTool("Backoffice", "backoffice", "Outil d'administration", []int{1, 2}, true)
    if err != nil {
        panic(err)
    }
    fmt.Println(string(resp))
}
```

### SDK Julia (tools et applications)

Le SDK Julia est disponible dans `sdk/julia/DealHostSDK.jl`.

Exemple rapide :

```julia
using DealHostSDK

client = DealHostClient("http://localhost:8000"; token="YOUR_TOKEN")
create_tool(client; name="Backoffice", slug="backoffice", description="Outil d'administration", module_ids=[1, 2], enabled=true)
```

### SDK Java (tools et applications)

Le SDK Java est disponible dans `sdk/java/dealhost-sdk`.

Exemple rapide :

```java
import io.dealhost.sdk.DealHostClient;
import java.util.List;

DealHostClient client = new DealHostClient("http://localhost:8000", "YOUR_TOKEN");
String response = client.createTool("Backoffice", "backoffice", "Outil d'administration", List.of(1, 2), true);
System.out.println(response);
```

### Manifests d’intégration hosting/gateway

- Les manifests d’intégration sont lus depuis:
  - `manifests/modules/*.json`
  - `manifests/tools/*.json`
  - `manifests/applications/*.json`
  - `manifests/repositories/*.json`
- Champs attendus pour les modules: `name`, `slug`, `image`, `branch` (optionnel), `repository_owner` (optionnel), `repository_name` (optionnel), `source_path` (optionnel), `deployment_target` (optionnel), `public_path` (optionnel), `upstream_host` (optionnel), `upstream_port` (optionnel), `healthcheck_path` (optionnel), `contract_topics` (optionnel), `production_ready` (optionnel), `enabled` (optionnel).
- Champs attendus pour les tools/applications: `name`, `slug`, `description` (optionnel), `enabled` (optionnel), `module_slugs` (optionnel), `version` (optionnel, semver), `version_notes` (optionnel).
- Champs attendus pour les repositories: `repository_full_name`, `source_dependency` (`type`, `repository_full_name`, `versioning`, `version`, `ref`, `commit_sha`), `allowed_events`, `path_mappings` (`prefix`, `module_slug`) et `route_defaults` (`module_slug`, `public_path`, `upstream_host`, `upstream_port`).
- L’auto découverte crée/met à jour automatiquement les objets `Module`, `Tool` et `HostedApplication`, synchronise leurs liens modules, et enregistre l'historique des versions quand `version` est fourni.
- Les manifests repositories pilotent le mapping webhook GitHub -> modules et les routes APISIX par défaut; ils ne créent pas d'objets en base.
- Tout `source_path` rattaché à `Smartappli/ArchiDEAL` doit être couvert par un `path_mappings` du manifest repository correspondant.

### Internationalisation de l’interface

- L’interface `/hosting/manage/` est traduisible et propose un sélecteur de langue.
- Langues officielles FAO supportées : **arabe, chinois (simplifié), anglais, français, russe, espagnol**.
- Fichiers de traduction : `locale/<lang>/LC_MESSAGES/django.po`.


### Gestion des versions tools/apps

- Chaque `Tool` et `HostedApplication` expose:
  - `current_version` (version active),
  - `released_at` (date de publication),
  - un historique de versions (`versions`).
- Endpoints de versionning:
  - `GET /api/hosting/tools/{id}/versions/`
  - `POST /api/hosting/tools/{id}/versions/` avec `{ "version": "1.2.3", "notes": "...", "source": "manual" }`
  - `GET /api/hosting/applications/{id}/versions/`
  - `POST /api/hosting/applications/{id}/versions/`
- Filtre de liste disponible: `?current_version=<semver>`.

### Gestion complète des tools/apps

- Filtres disponibles sur les listes modules:
  - `?enabled=true|false`
  - `?repository=Smartappli/ArchiDEAL` ou `?repository=ArchiDEAL`
  - `?repository_owner=Smartappli`
  - `?repository_name=ArchiDEAL`
  - `?deployment_target=compose|kubernetes|swarm|external`
  - `?has_public_route=true|false`
- Filtres disponibles sur les listes tools/applications:
  - `?enabled=true|false`
  - `?module_slug=<slug>`
  - `?search=<texte>` (nom, slug, description, slug module)
- Actions dédiées:
  - `POST /api/hosting/tools/{id}/attach-module/` avec `{ "module_id": <id> }`
  - `POST /api/hosting/tools/{id}/detach-module/` avec `{ "module_id": <id> }`
  - `GET /api/hosting/tools/{id}/modules/`
  - `POST /api/hosting/applications/{id}/attach-module/` avec `{ "module_id": <id> }`
  - `POST /api/hosting/applications/{id}/detach-module/` avec `{ "module_id": <id> }`
  - `GET /api/hosting/applications/{id}/modules/`

## Démarrage local

1. Copier les variables d’environnement :
   ```bash
   cp .env.example .env
   ```
2. Lancer la stack :
   ```bash
   docker compose up
   ```
3. API servie en ASGI par Granian sur `http://localhost:8000`.
   - le conteneur applique `migrate` + `collectstatic` au démarrage ;
   - la base SQLite est persistée à l'emplacement défini par
     `DEALHOST_DB_PATH` (`/data/db.sqlite3` dans l'image) ;
   - `valkey` est démarré avec healthcheck + volume persistant ;
   - APISIX attend que l’API Django soit healthy avant exposition.

## Sécurité et production

- Remplacer toutes les valeurs `replace-me` / placeholders.
- Définir `DJANGO_ALLOWED_HOSTS`; en production, la configuration refuse de démarrer si cette variable est vide ou contient `*`.
- Définir `DEALHOST_API_TOKENS` pour les clients API en lecture et `DEALHOST_ADMIN_API_TOKENS` pour les opérations d'administration (IAM, publication APISIX, autodiscovery, création/mise à jour hosting).
- Restreindre l'exposition réseau et exposer uniquement APISIX en edge.
- Protéger le webhook GitHub avec `GITHUB_WEBHOOK_SECRET`.
- Configurer GitHub pour transmettre `X-GitHub-Delivery` : DEALHost déduplique les livraisons signées pendant 24 h afin d'éviter les publications de route rejouées.
- Restreindre les webhooks acceptés avec `GITHUB_ALLOWED_REPOSITORIES=Smartappli/ArchiDEAL`.
- Externaliser SQLite vers PostgreSQL en environnement de production.
- Sessions en backend `cached_db` (persistance DB + cache Valkey pour performance).


## Runtime ASGI

- Entrée applicative: `dealhost.asgi:application`.
- Serveur applicatif: `granian --interface asgi dealhost.asgi:application`.
- Le projet est **ASGI-only** et ne contient pas d’entrée WSGI.

## Cache et sessions

- `SESSION_ENGINE=django.contrib.sessions.backends.cached_db` : sessions persistées en base Django.
- `CACHES["default"]` pointe vers Valkey via `VALKEY_URL` (ex: `redis://valkey:6379/1`).
- `ServeStatic` est activé dans le middleware Django et via le storage `CompressedManifestStaticFilesStorage` pour servir les assets statiques en ASGI.

## Messaging interne (NATS)

- Un bus d'événements NATS est disponible pour la communication inter-modules/services.
- Variables d'environnement :
  - `NATS_URL` (défaut `nats://nats:4222`)
  - `NATS_STREAM` (défaut `dealhost`)
  - `NATS_SUBJECT_PREFIX` (défaut `dealhost`)
  - `NATS_ENABLED` (`true|false`, défaut `false`)
- Examples de sujets publiés :
  - `dealhost.hosting.module.created`
  - `dealhost.hosting.tool.version-released`
  - `dealhost.gateway.route.publish.requested`
- Worker de consommation (MVP) : `python -m apps.common.events.worker`.

## GitHub Workflows

- `CI Django DEALHost` (`.github/workflows/ci.yml`) : exécute une matrice multi-plateforme (Linux/macOS/Windows) et multi-versions Python (3.12 à 3.14). Le projet cible Python >=3.12 : les jobs 3.12/3.13/3.14 installent d'abord `requirements.txt` puis le package (`uv pip install --system -r requirements.txt` puis `uv pip install --system -e .`), vérifient les migrations, exécutent les tests unitaires sous couverture (`uv run coverage run --source=apps,dealhost,sdk manage.py test tests --verbosity 2`), exportent `coverage.xml` et lancent le contrôle de compilation.
- `SonarCloud` (`.github/workflows/sonarcloud.yml`) : exécute les tests avec couverture sur Ubuntu + Python 3.12 puis lance l'analyse SonarCloud (`SonarSource/sonarqube-scan-action@v6`) à partir du fichier `sonar-project.properties`.
- `Validate APISIX Routes` (`.github/workflows/apisix-routes-validate.yml`) : valide la syntaxe JSON des routes APISIX et vérifie la présence des routes coeur, DEALIoT et DEALData attendues.
- `Validate Hosting Manifests` (`.github/workflows/hosting-manifests-validate.yml`) : valide la cohérence des manifests modules/tools/applications/repositories, des routes APISIX, du scan Renovate des images, et applique en mode strict la politique de tags Docker pour les modules `production_ready=true`.
- `Pre-commit` (`.github/workflows/pre-commit.yml`) : installe `pre-commit` via `uv` puis exécute `uv run pre-commit run --all-files --show-diff-on-failure` (incluant Ruff en mode `--select ALL` et `ruff-format`).

## Dependency Automation

- `Dependabot` est configuré via `.github/dependabot.yml` pour surveiller chaque semaine les dépendances Python, Rust, Go, Docker Compose et GitHub Actions. Les updates runtime (`pip` racine, Compose, GitHub Actions) portent le label `runtime-risk`.
- `Renovate` est conservé pour les manifests non standard `manifests/modules/*.json`, avec scan regex des images Docker, labels séparés pour `smartappli-ghcr` et `public-image`, et approbation obligatoire des majors via Dependency Dashboard.
- Les manifests repositories épinglent aussi les dépendances source Smartappli: DEALIoT via tag GitHub, DEALData via commit SHA tant qu'aucun tag n'est publié.
- Le workflow Renovate utilise `secrets.RENOVATE_TOKEN` si disponible, puis le token GitHub du workflow en repli. Un token dédié reste recommandé pour éviter les limites de permissions et de déclenchement.
- Les tags Docker `latest`, implicites ou `local-placeholder` doivent rester associés à `production_ready=false`; les modules prêts production doivent utiliser un tag explicite ou un digest.


## Datasets accessibles dans le dashboard

- Le dashboard `/hosting/manage/` est protégé (utilisateur connecté requis).
- Les datasets affichés sont filtrés pour l'utilisateur connecté :
  - accès direct (`dataset.users`)
  - accès via groupes (`dataset.groups`)
  - uniquement `enabled=true`.
- Un superutilisateur voit tous les datasets actifs.
