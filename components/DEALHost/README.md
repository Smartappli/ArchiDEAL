# DEALHost — Catalogue modulaire et contrôle de routes (Django 6 + APISIX + GitHub)

Ce composant contient un socle **Django 6 ASGI** (servi par **Granian**) pour exposer le catalogue applicatif, les métadonnées de versions, les probes de santé et la publication de routes **Apache APISIX** reliés au monorepo **`Smartappli/ArchiDEAL`**.

DEALHost expose désormais un plan de contrôle runtime asynchrone pour déployer et exploiter les versions applicatives revues sur Kubernetes. La publication d'une version fige le catalogue runtime (images par digest et profils vérifiés), mais ne déclenche jamais un déploiement : seule une mutation explicite de l'API runtime crée une opération réconciliée par le worker et le contrôleur isolé. Le build d'images, les domaines personnalisés et les quotas locataires restent hors périmètre.

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

- Cataloguer des **modules activables** (`apps.hosting.Module`).
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
 ├── apps.hosting  -> catalogue de modules, applications et versions
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
- `apps/hosting/` : catalogue et API REST des modules, applications, versions et datasets.
- `apps/gateway/` : services d’intégration GitHub + APISIX et endpoints d’orchestration.
- `infra/apisix/` : exemple de route APISIX standalone.

## Endpoints clés

- `GET /api/gateway/health/live/` : liveness locale, sans dépendance externe.
- `GET /api/gateway/health/ready/` : readiness PostgreSQL + Valkey ; renvoie `503`
  si l'une des deux dépendances est indisponible.
- `GET /api/gateway/health/` : alias de readiness conservé pour compatibilité.
- `POST /api/gateway/github/sync/` : récupère le dernier commit d’une branche du dépôt `Smartappli/ArchiDEAL`.
- `GET /api/gateway/github/repositories/` : liste les repositories intégrés, leurs événements autorisés, modules mappés et routes publiques déclarées.
- `POST /api/gateway/apisix/publish/` : crée/met à jour une route APISIX, avec
  `dry_run=true` pour prévisualiser le payload sans appel admin APISIX. Cette
  prévisualisation renvoie un ETag fort déterministe dans le corps et l'en-tête
  `ETag`. La publication opérateur (`dry_run=false`) exige exactement cet ETag
  dans `If-Match` (`428` absent, `400` invalide, `412` si le payload effectif a
  changé) et transmet à APISIX le même payload que celui comparé. Une ligne
  `Module` désactivée bloque aussi le dry-run (`409`, `code=module_disabled`) et ne
  retombe jamais sur le manifest ; un slug absent de la base et des manifests est
  refusé (`400`, `code=module_unknown`). En production, une route dynamique exige en
  plus un manifest de module revu avec `production_ready=true` (`409`,
  `code=module_not_production_ready`). Elle reprend les plugins d'observabilité ; le
  jeton OIDC n'est échangé contre `Authorization` que pour les upstreams DEALHost,
  DEALIoT et les trois couches DEALData qui l'introspectent. Toutes les autres cibles
  suppriment explicitement `Authorization` et `X-Forwarded-Access-Token`. Le profil de
  développement conserve
  l'en-tête `Authorization` reçu et n'active pas OpenTelemetry sans collecteur local.
  Avant toute prévisualisation ou publication,
  DEALHost refuse les chemins ambigus/encodés, les espaces système (`/oauth2`,
  `/healthz`, `/readyz`, `/apisix`, `/dealhost`, `/dealiot`, `/dealdata`) et les
  chevauchements exacts ou parent/enfant avec une route bootstrap ou un autre module
  actif. Toutes les routes déclarées par les manifests/bootstrap restent la propriété
  exclusive du bootstrap, y compris quand le slug, le chemin et l'upstream dynamiques
  leur correspondent exactement. Il n'existe aucune exception permettant à l'API
  dynamique de les recréer ou de les écraser.
- `POST /api/gateway/github/webhook/` : webhook signé GitHub -> publication de route. Les en-têtes `X-Hub-Signature-256`, `X-GitHub-Event` et `X-GitHub-Delivery` sont requis ; une livraison est traitée au plus une fois pendant 24 h.
- `GET/POST /api/hosting/modules/` : CRUD des modules hébergés.
  Faute de dépublication APISIX auditée, DEALHost traite tout module portant un
  triplet de routage complet comme potentiellement publié : sa désactivation, sa
  suppression, son renommage ou la modification de son chemin/upstream renvoie `409`
  (`code=route_revocation_unavailable`). Les autres métadonnées restent modifiables et
  un module sans route publique reste supprimable.
- `GET/POST /api/hosting/tools/` : catalogue CRUD des outils (chaque outil peut lier plusieurs modules).
- `GET/POST /api/hosting/applications/` : catalogue CRUD des applications (chaque application peut lier plusieurs modules) ; le CRUD de catalogue ne déploie rien sans appel runtime explicite.
- `GET /api/hosting/runtime-environments/` : environnements Kubernetes autorisés et capacités disponibles.
- `GET/POST /api/hosting/deployments/` : état désiré/observé et création asynchrone d'un déploiement runtime.
- `GET/PATCH/DELETE /api/hosting/deployments/{uuid}/` : lecture, configuration conditionnelle et déploiement inverse avec ETag fort.
- `POST /api/hosting/deployments/{uuid}/actions/` : `start`, `stop`, `restart` ou `scale` selon les capacités de l'environnement.
- `GET /api/hosting/deployments/{uuid}/operations/` et `GET /api/hosting/operations/{uuid}/` : historique et suivi des opérations durables.
- `POST /api/hosting/deployments/{uuid}/log-requests/` : snapshot borné et éphémère des journaux d'un composant.
- `GET/POST /api/hosting/datasets/` : catalogue des datasets et listes de visibilité. Les lectures authentifiées sont limitées aux entrées actives attribuées directement ou via un groupe ; le staff voit tout et réalise les mutations. Les mises à jour et suppressions exigent la révision courante dans `If-Match`. Ces listes ne contrôlent pas l'accès aux événements GPS ou Sensor de DEALData.
- `GET /api/hosting/dataset-principals/` (edge monorepo :
  `GET /dealhost/api/hosting/dataset-principals/`) : catalogue staff-only minimal pour
  l'édition des ACL de datasets. Il expose uniquement les identifiants, libellés,
  e-mails utiles, états et types d'identité des utilisateurs, ainsi que les noms
  de groupes. Il n'expose ni claims OIDC, ni permissions, ni jetons, et indique
  séparément si l'opérateur superutilisateur peut provisionner une identité OIDC.
- `POST /api/hosting/autodiscover/` : auto découverte depuis les manifests modules/tools/apps.
- `GET /hosting/manage/` : interface de gestion (modules, tools, datasets accessibles à l'utilisateur connecté, applications + auto découverte).
- `POST /i18n/setlang/` : changement de langue de l’interface de gestion.
- `GET/POST /api/iam/users/` : gestion des utilisateurs (avec groupes/permissions + endpoint `set-password`).
- `GET/POST /api/iam/oidc-identities/` : liste et provisionne, pour un
  superutilisateur uniquement, les identités OIDC techniques utilisables dans les
  ACL de datasets.
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
- L’auto découverte crée/met à jour automatiquement les objets `Module`, `Tool` et `HostedApplication`, synchronise leurs liens modules, et enregistre une version immuable quand `version` est fourni. La révision d'une application n'avance que si ses métadonnées, ses liens modules ou sa version courante changent effectivement. Rejouer le même contenu est sans effet ; réutiliser le même numéro avec des notes différentes fait échouer et annule l’auto découverte.
- Les manifests repositories pilotent le mapping webhook GitHub -> modules et les routes APISIX par défaut; ils ne créent pas d'objets en base.
- Tout `source_path` rattaché à `Smartappli/ArchiDEAL` doit être couvert par un `path_mappings` du manifest repository correspondant.

### Internationalisation de l’interface

- L’interface `/hosting/manage/` est traduisible et propose un sélecteur de langue.
- Langues officielles FAO supportées : **arabe, chinois (simplifié), anglais, français, russe, espagnol**.
- Fichiers de traduction : `locale/<lang>/LC_MESSAGES/django.po`.


### Gestion des versions tools/apps

- Chaque `Tool` et `HostedApplication` expose:
  - `current_version` (dernière métadonnée publiée),
  - `released_at` (date de publication),
  - un historique de versions (`versions`).
- Endpoints de versionning:
  - `GET /api/hosting/tools/{id}/versions/`
  - `POST /api/hosting/tools/{id}/versions/` avec `{ "version": "1.2.3", "notes": "...", "source": "manual" }`
  - `GET /api/hosting/applications/{id}/versions/`
  - `POST /api/hosting/applications/{id}/versions/` avec l'ETag fort de la
    `HostedApplication` courante dans `If-Match`
- `current_version` et `released_at` sont en lecture seule dans les CRUD tools/applications ; seule l'action de publication peut les avancer.
- Une première publication crée la version et renvoie `201`. Un rejeu avec exactement les mêmes `notes` et `source` renvoie l'objet existant avec `200`, sans modifier les dates ni produire un nouvel événement. Le même numéro avec des métadonnées différentes renvoie `409` (`code=version_conflict`) et ne modifie rien.
- La création de l'historique, le snapshot runtime protégé par digest, la mise à jour du pointeur de catalogue et l'incrément de `HostedApplication.revision` sont atomiques. Pour les applications, le contrôle `If-Match` est effectué sous le même verrou de ligne : l'absence renvoie `428`, un ETag mal formé `400`, et une révision périmée `412` avec l'ETag courant. Une publication réellement nouvelle avance la révision ; son rejeu exact avec la révision courante ne l'avance pas et ne ramène jamais le pointeur du catalogue vers une ancienne version. Toute réponse de succès porte l'ETag de révision courant. La publication ne déclenche aucun déploiement ; elle rend seulement la version éligible si toutes ses images et tous ses profils sont déployables.
- Filtre de liste disponible: `?current_version=<semver>`.

### Gestion runtime Kubernetes

Le runtime est désactivé par défaut et échoue explicitement avec `503` tant que
`DEALHOST_RUNTIME_ENABLED=true` n'est pas configuré. Le serveur web ne reçoit jamais
d'identifiants Kubernetes. Il valide les profils, écrit une opération durable en base,
puis un processus séparé la loue et appelle le runtime-controller interne via TLS et
Bearer :

```bash
python manage.py process_runtime_operations
python manage.py process_runtime_operations --once
```

Chaque mutation exige une `Idempotency-Key` de 8 à 128 caractères sûrs. Les créations
utilisent l'ETag de la `HostedApplication`; les configurations, actions, demandes de
logs et suppressions utilisent celui du déploiement. Une réponse `202` signifie
uniquement « mise en file » : l'état final est donné par la ressource opération.

Une version est déployable seulement si chaque module capturé lors de sa publication :

- cible Kubernetes, est activé et possède un slug compatible avec un composant runtime ;
- référence une image immuable `repository@sha256:<64 hex>` autorisée par la politique
  de l'environnement ;
- possède un profil runtime activé, vérifié et dont le digest correspond exactement à
  la spécification (port, probe, ressources, clés de configuration et règles réseau).

Les valeurs sensibles ne sont jamais acceptées dans `configuration`. `secret_refs`
contient seulement des noms logiques canoniques présents dans
`RuntimeEnvironment.policy.allowed_secret_refs`, puis résolus côté contrôleur. Les snapshots
de logs sont limités par l'environnement, conservés cinq minutes dans le cache puis
supprimés; leur réponse utilise `Cache-Control: private, no-store`. Les domaines
personnalisés ne sont pas exposés tant que DNS, certificats et callback OIDC ne disposent
pas d'un contrat transactionnel commun.

Variables principales :

```bash
DEALHOST_RUNTIME_ENABLED=true
DEALHOST_RUNTIME_CONTROLLER_URL=https://runtime-controller.internal
DEALHOST_RUNTIME_CONTROLLER_TOKEN=<secret>
DEALHOST_RUNTIME_CONTROLLER_TIMEOUT_SECONDS=15
DEALHOST_RUNTIME_CONTROLLER_CA_FILE=/var/run/runtime-controller-ca/ca.crt
```

En production, le web partage uniquement le drapeau d'activation avec le worker. Le
token du contrôleur et le bundle CA sont montés dans le worker, tandis que les droits
Kubernetes restent exclusivement attachés au pod runtime-controller dans le namespace
applicatif isolé.

Les `secret_refs` restent des noms logiques : le contrôleur les résout sous la forme
`<RUNTIME_CONTROLLER_SECRET_NAME_PREFIX>-<nom-logique>`. Il n'a aucun droit de lecture
sur les Secrets. Il exige avant mutation une entrée correspondante dans le ConfigMap
opérateur `dealhost-runtime-secret-catalog`, placé dans un autre namespace et lisible
en `get` seulement. Chaque entrée JSON fixe le nom résolu et les clés d'environnement
autorisées, sans contenir de valeur secrète. Le catalogue vide et toute entrée absente
ou incohérente échouent fermé. Kubernetes signale ensuite un Secret réel absent ou
une clé manquante dans l'état du rollout, sans que DEALHost lise ou retourne sa valeur.

Le runtime-controller rejette les domaines et tout `network_egress` FQDN tant qu'un
mécanisme d'application réseau ne les garantit pas. Il ne les ignore jamais
silencieusement.

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

Chaque `HostedApplication` expose une `revision` positive en lecture seule. Une réponse
de détail porte l'ETag fort correspondant (`"3"`). Les `PATCH`/`PUT`/`DELETE`, la publication
de version et les actions `attach-module`/`detach-module` exigent exactement cet ETag dans `If-Match` : l'absence
renvoie `428`, un ETag mal formé `400`, et une révision périmée `412` avec l'ETag
courant. Une modification acceptée avance la révision et, lorsque Core NATS est activé,
tente d'émettre une notification best-effort ;
réattacher ou détacher une relation déjà dans l'état demandé reste sans effet.

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
- Pour les comptes de service, définir `DEALHOST_API_TOKENS` en lecture et `DEALHOST_ADMIN_API_TOKENS` pour les opérations d'administration.
- Pour les opérateurs derrière l'edge OIDC, configurer `DEALHOST_OIDC_INTROSPECTION_URL`, `DEALHOST_OIDC_ISSUER`, `DEALHOST_OIDC_AUDIENCE`, les identifiants confidentiels du client et les groupes `DEALHOST_OIDC_READ_GROUPS` / `DEALHOST_OIDC_ADMIN_GROUPS`. Les groupes sont lus uniquement dans le claim top-level nommé par `DEALHOST_OIDC_GROUPS_CLAIM` (défaut : `groups`) ; `scope`/`scp`, `roles` et `realm_access.roles` ne donnent jamais de privilège. L'introspection valide l'activité, l'émetteur, l'audience et l'appartenance au groupe avant de construire l'identité authentifiée de la requête. Le provisionnement persistant d'une ACL directe est une opération d'administration distincte, décrite ci-dessous.
- Restreindre l'exposition réseau et exposer uniquement APISIX en edge.
- Définir en production `APISIX_ROUTE_ALLOWED_UPSTREAM_HOSTS` et/ou
  `APISIX_ROUTE_ALLOWED_UPSTREAM_SUFFIXES`, `APISIX_ROUTE_ALLOWED_UPSTREAM_PORTS` et
  `APISIX_ROUTE_ALLOWED_UPSTREAMS`. Ce dernier contient les couples exacts
  `host:port` et empêche qu'une combinaison croisée des deux premières listes soit
  autorisée. Une destination doit être un nom DNS strict
  (jamais une IP, `localhost` ou une chaîne contenant des métacaractères), respecter
  une frontière DNS de l'allowlist et utiliser un port autorisé. Sans politique
  explicite, la publication dynamique échoue fermée en production. En développement
  seulement, l'allowlist est dérivée des destinations du manifest et de
  `APISIX_UPSTREAM_HOST` afin de préserver le contrat Compose. Des préfixes réservés
  supplémentaires peuvent être ajoutés avec `APISIX_ROUTE_RESERVED_PATH_PREFIXES` ;
  les préfixes système intégrés restent toujours actifs.
- Protéger le webhook GitHub avec `GITHUB_WEBHOOK_SECRET`.
- Configurer GitHub pour transmettre `X-GitHub-Delivery` : DEALHost déduplique les livraisons signées pendant 24 h afin d'éviter les publications de route rejouées.
- Restreindre les webhooks acceptés avec `GITHUB_ALLOWED_REPOSITORIES=Smartappli/ArchiDEAL`.
- La production refuse SQLite et exige PostgreSQL avec `DEALHOST_DATABASE_SSLMODE=verify-full` et une autorité de certification explicite via `DEALHOST_DATABASE_SSLROOTCERT`.
- La production refuse `redis://` et exige que `VALKEY_URL` utilise `rediss://`. Le profil Compose
  local conserve `redis://valkey:6379/1` uniquement pour le développement isolé.
- Sessions en backend `cached_db` (persistance DB + cache Valkey pour performance).
- L'image de production installe `requirements.lock` avec `--require-hashes` ; régénérer ce
  fichier depuis `uv.lock` avec `uv export --frozen --no-dev --no-emit-project --format
  requirements.txt --output-file requirements.lock` après toute mise à jour volontaire.

La dépublication n'est volontairement pas exposée tant qu'un endpoint opérateur ne
peut pas associer le `DELETE` APISIX à une autorisation, une précondition et un
événement d'audit persisté. Un `DELETE` ou une désactivation de `Module` ne retire
donc jamais une route. L'API bloque ces mutations pour tout module routable plutôt que
de laisser une route orpheline. Supprimer directement une route via l'API admin APISIX
contournerait ces garanties et reste une opération de runbook externe ; après ce
retrait externe, le catalogue ne dispose encore d'aucune preuve persistée permettant
de débloquer automatiquement la mutation.


## Runtime ASGI

- Entrée applicative: `dealhost.asgi:application`.
- Serveur applicatif: `granian --interface asgi dealhost.asgi:application`.
- Le projet est **ASGI-only** et ne contient pas d’entrée WSGI.

## Cache et sessions

- `SESSION_ENGINE=django.contrib.sessions.backends.cached_db` : sessions persistées en base Django.
- `CACHES["default"]` pointe vers Valkey via `VALKEY_URL` (`redis://valkey:6379/1` en local,
  `rediss://<hôte>:6380/1` obligatoire avec les settings de production).
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


## Visibilité des datasets dans le catalogue

- Le dashboard `/hosting/manage/` est protégé (utilisateur connecté requis).
- Les datasets affichés sont filtrés pour l'utilisateur connecté :
  - accès direct (`dataset.users`)
  - accès via groupes (`dataset.groups`)
  - uniquement `enabled=true`.
- Un superutilisateur voit tous les datasets actifs.

L'API `/api/hosting/datasets/` applique la même isolation aux utilisateurs non-staff.
Elle accepte les filtres `enabled`, `module_slug`, `search` et `ordering`. Les filtres
administratifs `user_id` et `group_id`, ainsi que les champs d'ACL `user_ids` et
`group_ids`, sont réservés au staff. Les écritures nécessitent également un compte
staff (ou un jeton d'administration équivalent).

Ces relations utilisateur/groupe sont uniquement des ACL de visibilité du catalogue
DEALHost. Elles n'accordent ni ne refusent l'accès data-plane aux événements GPS ou
Sensor de DEALData. Les listes d'événements sont protégées séparément par le groupe
administrateur de DEALData : cette frontière est commune au service et ne constitue
pas une ACL par dataset, objet observé ou ligne d'événement.

Une identité OIDC est reliée aux ACL directes par une clé locale stable dérivée de
`issuer + sub`, jamais par le `preferred_username` mutable. Les noms du claim OIDC
`groups` peuvent également correspondre à des groupes Django existants. Un jeton de
service statique conserve son `username` technique ; sans identité ou groupe local
correspondant, sa liste reste vide.

### Provisionner une ACL utilisateur OIDC stable

Après avoir appliqué les migrations (`python manage.py migrate`), un superutilisateur
ou un jeton `DEALHOST_ADMIN_API_TOKENS` peut appeler
`POST /api/iam/oidc-identities/` avec un document sans secret :

```json
{
  "issuer": "https://identity.example.com/realms/archideal",
  "subject": "248289761001",
  "display_name": "Ada Operator",
  "email": "ada@example.com"
}
```

L'API exige que `issuer` soit exactement l'issuer runtime approuvé par
`DEALHOST_OIDC_ISSUER`, lui-même sous forme HTTPS canonique (schéma et hôte en
minuscules, aucun identifiant dans l'URL, query, fragment, segment `.`/`..` ou port
`443` explicite). Le provisionnement échoue fermé avec `400` si cette configuration
est absente ou invalide, ou si l'issuer demandé est différent. Le `sub` doit être non
vide et sans espaces périphériques. L'API calcule elle-même la clé opaque
`oidc:<sha256(issuer + NUL + sub)>`, puis la lie à un `User` Django technique non-staff,
non-superutilisateur et sans mot de passe utilisable. Le client ne transmet ni cette
clé calculée, ni mot de passe, ni jeton OIDC ; tout champ non prévu est refusé.

La première requête renvoie `201` avec `created=true`, `user_id` et `acl_username`.
Une répétition pour la même paire renvoie `200` avec `created=false`; les seuls champs
rafraîchissables sont `display_name` et `email`, signalés par `metadata_updated`. Une
clé locale déjà occupée ou une liaison devenue incohérente renvoie un conflit `409`
au lieu de rattacher silencieusement un compte existant. `GET` sur la même collection
permet de retrouver les identités et leurs libellés humains, avec `Cache-Control:
no-store`.

Le `user_id` retourné peut ensuite être ajouté à `user_ids` lors d'un `PATCH` du
dataset, en fournissant l'ETag courant dans `If-Match`. La représentation existante de
`GET /api/iam/users/` reste compatible et ajoute seulement un champ nullable
`oidc_identity` (`display_name`, `email`, `issuer`, `subject`, `label`) pour que les
interfaces d'administration n'affichent pas uniquement la clé opaque. Pour préserver
la liaison, l'API User refuse avec `409` le changement de username ou de privilèges,
l'ajout d'un mot de passe et la suppression d'un User technique OIDC.

Le déprovisionnement passe exclusivement par
`DELETE /api/iam/oidc-identities/{id}/` et n'accepte aucun corps de requête : le client
ne renvoie donc jamais `issuer`, `subject`, mot de passe ou jeton pour choisir la cible.
L'opération est réservée aux superutilisateurs. Elle verrouille l'identité et son
`User`, puis refuse avec `409` tant que ce compte est encore présent dans une ACL
directe de dataset, un groupe ou une permission utilisateur, ou si la liaison locale
n'est plus conforme à la clé opaque passwordless et non privilégiée attendue. Sinon,
l'identité et son compte technique sont supprimés dans une seule transaction et la
réponse est `204`; une répétition sur le même identifiant renvoie `404`. Les réponses
portent `Cache-Control: no-store`. Le mécanisme de notification best-effort
`iam.oidc_acl_identity.deprovisioned` ne contient que les identifiants locaux, la clé
ACL opaque et l'acteur, jamais le `subject` brut.

Chaque dataset expose `revision` et `updated_at`. Les réponses de détail portent un
ETag fort (`"3"`) et tout `PATCH`/`PUT`/`DELETE` exige cette valeur dans `If-Match`.
Pour la suppression, l'absence renvoie `428`, un ETag faible ou mal formé `400`, et une
révision périmée `412` avec l'ETag et la révision courants ; seule la révision exacte
est supprimée avec `204`. DEALInterface affiche une confirmation puis envoie l'ETag
fort de l'entrée chargée, afin qu'une vue opérateur obsolète ne puisse pas supprimer
une version plus récente. Lorsque Core NATS est activé, les créations, modifications
et suppressions tentent également d'émettre une notification best-effort
`hosting.dataset.*` avec l'acteur et la révision.

Ces notifications Core NATS ne constituent pas un journal d'audit durable : elles sont
désactivées dans la baseline Kubernetes actuelle (`NATS_ENABLED=false`) et, même activées,
ne reposent ni sur un outbox transactionnel ni sur un accusé durable. Elles servent à
l'intégration en développement. Un GO production exige un journal d'audit persistant,
corrélé à l'acteur et à la requête, avec preuve de reprise, conformément au contrat de
préparation production racine.
