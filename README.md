# Backstage

Backstage est une application web personnelle et familiale pour gerer un catalogue de films et series, suivre les preferences de chaque utilisateur, trouver quoi regarder et piloter un serveur media local.

## Stack

- FastAPI + SQLite pour l'API et la persistance ;
- React + Vite pour l'interface ;
- TMDB pour les metadonnees ;
- Jellyfin pour la lecture et la progression ;
- Jellyseerr/Seerr, Radarr et Sonarr pour les demandes et telechargements ;
- Docker Compose pour le deploiement.

## Fonctionnalites

- catalogue partage et etats personnels ;
- favoris, watchlist, historique et notes ;
- fiche media avec note TMDB ;
- recommandations interactives ;
- disponibilite, locations temporaires et quotas ;
- demandes de films/series, lecture Jellyfin et reprise ;
- suivi des episodes par utilisateur ;
- notifications, administration, sauvegardes et supervision.

## Installation locale

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python main.py

Pour le frontend :

    cd proto-ui
    npm install
    npm run dev

En production, construire le frontend puis lancer le serveur avec Docker Compose.

## Configuration

Copier .env.example vers .env et renseigner au minimum :

    TMDB_API_KEY=
    DB_PATH=backstage.db
    BACKSTAGE_PUBLIC_URL=http://localhost:8090
    BACKSTAGE_COOKIE_SECURE=0

Les integrations media sont optionnelles. Les secrets restent cote serveur et ne doivent jamais etre commites.

Les quotas de recommandation et de rate limiting sont configurables avec :

    RECOMMENDATION_DAILY_LIMIT=5
    RECOMMENDATION_TIMEZONE=Europe/Paris
    AUTH_RATE_LIMIT_WINDOW_SEC=300
    AUTH_RATE_LIMIT_MAX_ATTEMPTS=5
    AUTH_RATE_LIMIT_BLOCK_SEC=900

### Lecture directe dans Jellyfin Web

Une fois cette version de Backstage déployée, activez le script côté Jellyfin pour lancer son lecteur officiel depuis Backstage.

1. Installez le plugin communautaire [JavaScript Injector](https://github.com/n00bcodr/Jellyfin-JavaScript-Injector#-installation) et redémarrez Jellyfin.
2. Dans **Tableau de bord → Plugins → JavaScript Injector**, ajoutez un script. Collez le contenu de [backstage-autoplay.js](integrations/jellyfin/backstage-autoplay.js) dans le champ JavaScript, activez-le et enregistrez.
3. Connectez-vous à Jellyfin Web, puis ouvrez un film ou un épisode avec **Lire** depuis Backstage.

Backstage ouvre Jellyfin dans un nouvel onglet puis lui transmet une demande de lecture contrôlée par l'identifiant du média. Le script attend que la fiche Jellyfin soit prête et choisit **Reprendre** quand c'est disponible, sinon **Lire**. Il confirme le démarrage uniquement quand Jellyfin ouvre son lecteur vidéo ; si le script n'est pas actif ou si le lecteur ne démarre pas, Backstage affiche une erreur au lieu de prétendre que la lecture a réussi. Une mise à jour de Jellyfin Web peut nécessiter d'ajuster le script.

## Deploiement securise

Lire [docs/SECURE_DEPLOYMENT.md](docs/SECURE_DEPLOYMENT.md) avant toute exposition hors LAN. Le profil de production requiert HTTPS, VPN ou reverse proxy, BACKSTAGE_COOKIE_SECURE=1, des secrets hors Git, une sauvegarde hors volume et un exercice de restauration.

## Verification

    .venv\Scripts\python.exe -m pytest

    cd proto-ui
    npm run lint
    npm run build

## Documentation produit

- [Guide de deploiement securise](docs/SECURE_DEPLOYMENT.md)
- [Plan Sprint 1](docs/superpowers/plans/2026-08-07-sprint-1-hardening.md)
