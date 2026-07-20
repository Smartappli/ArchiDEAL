# Mise à jour automatique d'un VPS

`scripts/update-vps.sh` met à jour le stack Compose racine depuis une branche Git configurée. Il
est conçu pour un VPS mono-nœud d'intégration ou de démonstration. Compose reste explicitement
hors du périmètre de production supporté : une production ArchiDEAL doit utiliser la promotion
Kubernetes signée décrite dans [`docs/deployment.md`](../../docs/deployment.md).

## Garanties du script

À chaque exécution, le script :

1. prend un verrou non bloquant pour empêcher deux mises à jour concurrentes ;
2. refuse un dépôt contenant des modifications suivies ou non suivies, ainsi qu'un checkout qui
   n'est pas déjà sur la branche configurée, et n'exécute jamais `stash`, `reset --hard` ou un
   changement automatique de branche ;
3. récupère la branche distante puis n'accepte qu'une avance rapide ;
4. exécute la validation du monorepo et `docker compose config --quiet` ;
5. construit les images applicatives avec un tag dérivé du commit, démarre le Compose existant,
   puis exécute le contrôle de santé HTTP de toutes les applications ;
6. en cas d'échec, remet la branche locale et les images applicatives au commit précédent,
   redéploie celui-ci et contrôle de nouveau sa santé.

Les volumes Compose ne sont jamais supprimés et les anciennes images ne sont pas nettoyées par le
script. Le rollback applicatif ne peut pas annuler une migration de données : toute évolution de
schéma déployée par ce mécanisme doit rester compatible avec la version précédente (stratégie
expand/contract).

## Installation

Le VPS doit disposer de Git, Docker Engine, Docker Compose v2, Bash, `flock`, `timeout`, Python 3.12+
et PyYAML. Un daemon cron actif et compatible avec `/etc/cron.d` (par exemple `cron` sous
Debian/Ubuntu) est requis. Utilisez un compte de service non privilégié membre du groupe Docker,
un dépôt qui lui appartient et une clé Git de déploiement en lecture seule. Pré-enregistrez la clé
d'hôte SSH ; ne placez jamais de jeton dans l'URL du remote, cron ou les arguments du script.

Le checkout doit être placé à l'avance sur `ARCHIDEAL_BRANCH` (`git switch main` avec la
configuration d'exemple). Cette contrainte permet d'identifier sans ambiguïté le commit réellement
déployé et d'y revenir en cas d'échec.

### Installation automatisée

Depuis un checkout propre appartenant au compte de service, l'installateur configure les
répertoires, copie le fichier Compose secret, installe une copie root-owned stable de l'updater,
exécute son `--dry-run` sous le compte cible puis installe une tâche système dédiée dans
`/etc/cron.d/archideal-vps-auto-update`. Il ne modifie jamais la crontab du compte :

```bash
sudo ./deploy/vps/install-auto-update.sh \
  --user archideal \
  --repo /srv/archideal \
  --compose-env /srv/archideal/.env \
  --branch main \
  --interval-minutes 10
```

L'installation échoue avant d'activer cron si le dépôt est modifié, si le remote n'est pas
joignable, si Compose est invalide ou si le compte ne peut pas joindre Docker. Une réexécution
met à jour seulement la copie de l'updater et le fichier cron dédié ; elle conserve la crontab,
la configuration identique et le fichier secret. Si les options produisent une configuration
différente, relisez-les puis ajoutez explicitement `--replace-config`. Pour remplacer le secret,
ajoutez `--replace-compose-env --compose-env /chemin/vers/le/nouveau.env`. Le nouveau secret n'est
installé qu'après la réussite du dry-run.

La copie exécutée par cron se trouve dans `/usr/local/libexec/archideal/update-vps.sh`. Elle reste
stable pendant que le checkout Git est avancé ou restauré.

Si l'installation manuelle ci-dessous a déjà créé les répertoires au nom du compte de service,
transférez uniquement leur propriété et leur mode avant d'utiliser l'installateur automatisé (les
fichiers secrets qu'ils contiennent restent au compte de service en mode `0600`) :

```bash
sudo chown root:archideal /etc/archideal /var/log/archideal /var/lib/archideal
sudo chmod 0750 /etc/archideal /var/log/archideal /var/lib/archideal
```

Supprimez aussi toute ancienne ligne manuelle appelant `update-vps.sh` dans la crontab du compte
afin d'éviter deux planifications du même updater.

### Installation manuelle

Exemple, en adaptant l'utilisateur et les chemins :

```bash
sudo install -d -m 0750 -o archideal -g archideal /etc/archideal
sudo install -d -m 0750 -o archideal -g archideal /var/log/archideal
sudo install -d -m 0750 -o archideal -g archideal /var/lib/archideal
sudo install -m 0600 -o archideal -g archideal \
  deploy/vps/update-vps.env.example /etc/archideal/update-vps.env
sudo install -m 0600 -o archideal -g archideal \
  .env /etc/archideal/compose.env
```

Éditez `/etc/archideal/update-vps.env`, puis validez sans modifier Git, les images ou les conteneurs :

```bash
sudo -u archideal /srv/archideal/scripts/update-vps.sh \
  --config /etc/archideal/update-vps.env --dry-run
```

Ce mode valide le checkout courant et résout l'identifiant de la cible distante, mais il ne peut
pas valider le contenu de cette cible sans la récupérer ni la checkout ; la validation complète du
nouveau contenu reste donc la première étape bloquante d'une exécution réelle, avant le déploiement.

L'appel crontab suivant vérifie la branche toutes les dix minutes. Le script écrit lui-même dans
`ARCHIDEAL_LOG_FILE`; la redirection évite qu'une sortie complète soit envoyée par courriel :

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/10 * * * * /srv/archideal/scripts/update-vps.sh --config /etc/archideal/update-vps.env >/dev/null 2>&1
```

Installez cette entrée dans la crontab du même compte de service (`sudo crontab -u archideal -e`).
Le fichier de configuration et le fichier Compose de secrets doivent lui appartenir et avoir le
mode `0600`. Configurez une rotation de `/var/log/archideal/vps-update.log` avec `logrotate` selon
la politique de rétention du serveur.

## Codes de retour et intervention

| Code | Signification |
|---:|---|
| `0` | mise à jour réussie, ou commit déjà à jour et sain |
| `2` | configuration, permissions ou dépendance invalide |
| `10` | une autre exécution détient le verrou |
| `20` | état Git dangereux (modifications locales, divergence, branche absente) |
| `30` | validation ou construction échouée ; checkout précédent restauré |
| `40` | déploiement ou santé échoué ; rollback automatique réussi |
| `50` | rollback automatique échoué ; intervention immédiate requise |

Une erreur laisse les détails horodatés dans le journal sans activer de trace shell et sans
afficher les valeurs du fichier Compose. Si le code `50` est renvoyé, conservez les volumes,
inspectez `docker compose ps --all` et le journal, puis restaurez manuellement une version connue
compatible avant de relancer l'automatisation.
