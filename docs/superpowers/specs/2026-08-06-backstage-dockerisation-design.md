# Backstage — Dockerisation sur le serveur domestique

## Objectif

Permettre d’exécuter Backstage sur le home server avec Docker Compose, sans
coupler les données persistantes au conteneur ni au disque système définitif.
Le premier déploiement utilisera le SSD du serveur. Le chemin de données devra
ensuite pouvoir être déplacé vers le futur disque sans modifier le code.

## Périmètre

Cette étape concerne uniquement Backstage :

- backend Python existant ;
- frontend React compilé avec Vite ;
- base SQLite et fichiers persistants ;
- variables d’environnement ;
- contrôle de santé ;
- documentation de déploiement et de migration.

Jellyfin, Radarr, Sonarr, Seerr, Portainer et le client de téléchargement ne
sont pas ajoutés à cette stack. Ils restent des services externes référencés par
leurs URLs et leurs clés API.

## Architecture cible

```text
SSD du serveur
├── /srv/apps/backstage       code source et fichiers Compose
└── /srv/data/backstage       base SQLite et données persistantes

Docker Compose
└── backstage
    ├── backend Python/FastAPI
    └── frontend React/Vite compilé
```

Le conteneur ne contient aucune donnée utilisateur indispensable à sa
reconstruction. Le volume `/srv/data/backstage` est monté dans le conteneur
sur `/data`, et `DB_PATH=/data/backstage.db` devient la configuration par
défaut du déploiement Docker.

## Image Docker

L’image sera construite en deux étapes :

1. une étape Node.js qui installe les dépendances de `proto-ui` et produit
   `proto-ui/dist` ;
2. une étape Python qui installe `requirements.txt`, copie le code Backstage
   et récupère le frontend compilé.

L’image finale n’embarque pas `node_modules`, les caches npm, les tests ou la
base SQLite locale du poste de développement.

## Compose

Le service Backstage :

- expose le port interne 8090 ;
- mappe le port hôte via `BACKSTAGE_PORT`, 8090 par défaut ;
- charge `.env` avec `env_file` ;
- monte le répertoire de données persistant ;
- utilise `restart: unless-stopped` ;
- fournit un healthcheck HTTP sans exposer de secret.

Le healthcheck vérifiera une route `/health` renvoyant un statut JSON minimal,
indépendant de Jellyfin, Radarr et Sonarr. Une panne d’un service média ne doit
pas faire déclarer Backstage lui-même comme indisponible.

## Migration future du stockage

Le code et la configuration ne contiendront pas de chemin vidéo matériel. Pour
passer au futur disque, l’administrateur déplacera le contenu du répertoire de
données, modifiera le chemin du volume dans Compose, puis redémarrera le
service. La procédure documentera un arrêt propre, une copie, une vérification
de la base et un redémarrage.

Tant que le second disque n’est pas installé, aucune politique de suppression
automatique de contenu ne sera activée et le SSD ne sera pas considéré comme
sauvegardé.

## Sécurité et limites

- `.env` reste hors Git ; `.env.example` ne contient que des valeurs vides ou
  non sensibles.
- Les clés API restent côté serveur.
- Le CORS permissif existant sera conservé pour ne pas modifier le périmètre
  fonctionnel de cette étape ; son durcissement fera l’objet de la future
  étape comptes/sessions.
- La stack Docker ne publie pas directement les ports Radarr, Sonarr ou
  Jellyfin.

## Vérification

Avant de considérer l’étape terminée :

- les 53 tests Python existants passent ;
- le lint et le build du frontend passent depuis `proto-ui` ;
- `docker build` produit l’image ;
- `docker compose config` est valide ;
- le conteneur démarre avec un répertoire de données vide ;
- la base reste présente après reconstruction du conteneur ;
- `/health` répond sans dépendre des services média.

