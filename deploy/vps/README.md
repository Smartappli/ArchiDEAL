# Mise à jour automatique d'un VPS

`scripts/update-vps.sh` met à jour le stack Compose racine depuis une branche Git configurée. Il
est conçu pour un VPS mono-nœud d'intégration ou de démonstration. Compose reste explicitement
hors du périmètre de production supporté : une production ArchiDEAL doit utiliser la promotion
Kubernetes signée décrite dans [`docs/deployment.md`](../../docs/deployment.md).

## Garanties du script

À chaque exécution, le script :

1. prend un verrou non bloquant pour empêcher deux mises à jour concurrentes ;
2. refuse un dépôt contenant des modifications suivies ou non suivies et n'exécute jamais
   `stash`, `reset --hard` ou un pull forcé ;
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
et PyYAML. Utilisez un compte de service non privilégié membre du groupe Docker, un dépôt qui lui
appartient et une clé Git de déploiement en lecture seule. Pré-enregistrez la clé d'hôte SSH ; ne
placez jamais de jeton dans l'URL du remote, la crontab ou les arguments du script.

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
