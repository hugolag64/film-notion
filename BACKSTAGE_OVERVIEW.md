# Backstage — Vue d'ensemble pour analyse IA

> Document de référence factuel décrivant ce qu'est Backstage aujourd'hui : nature du projet, architecture technique, modèle de données, fonctionnalités livrées et état du dépôt. Destiné à être fourni en contexte à un outil d'IA (analyse, revue, planification) sans nécessiter d'explorer tout le code source.

## 1. Qu'est-ce que Backstage ?

Backstage est une application web personnelle de gestion de films et séries, développée en solo par un unique utilisateur (Hugo), hébergée à terme sur un serveur domestique (HP ProDesk 600 G4 Mini, Ubuntu Server + Docker). L'ambition est d'en faire un **« Netflix maison » multi-utilisateur**, intégré à un écosystème self-hosted de media management (Jellyfin, Radarr, Sonarr, Jellyseerr).

Le projet a évolué en plusieurs générations :

1. **V1 (obsolète)** : script d'enrichissement d'une base de films **Notion** via l'API TMDB (réalisateur, synopsis, genres, affiche…), avec une interface **NiceGUI** en Python pur. Cette version est décrite dans le `README.md` historique mais son code a été déplacé dans `legacy/2026-07-cleanup/` (dossiers `nicegui/` et `notion-enrichment/`) — elle n'est plus active.
2. **V2 (actuelle)** : application autonome avec sa propre base **SQLite**, backend **FastAPI** exposant une API REST, et frontend **React (Vite)** compilé et servi statiquement par le backend. NiceGUI est conservé uniquement comme conteneur d'app FastAPI (bootstrap ASGI), pas comme moteur d'UI.

**⚠️ Point important pour une analyse IA** : le `README.md` à la racine décrit encore majoritairement la V1 (Notion). Le document `BACKSTAGE_VISION_ARCHITECTURE_ROADMAP.md` est la source de vérité la plus récente sur l'état réel et la direction du produit. Le présent fichier reflète l'état du code tel qu'observé, pas seulement la documentation.

## 2. Stack technique

| Couche | Technologie |
|---|---|
| Backend | Python, **FastAPI** (routes REST), monté dans une app **NiceGUI/ASGI** (`main.py`) |
| Frontend | **React + Vite** (`proto-ui/`), compilé dans `proto-ui/dist/` et servi en statique par FastAPI |
| Base de données | **SQLite** (`backstage.db`), accès via `sqlite3` synchrone encapsulé dans des méthodes `async` (thread executor) |
| Auth | Système maison (hash de mot de passe, sessions par token, cookies « appareil mémorisé » 30 jours) |
| Métadonnées films/séries | API **TMDB** (v3) |
| Notes IMDb / classification d'âge | API **OMDB** (optionnel) |
| Recommandations IA | **Google Gemini** (optionnel, passerelle à quota) + moteur de scoring local (sans IA) |
| Lecture vidéo | **Jellyfin** (lecteur intégré, comptes utilisateurs liés) |
| Téléchargement automatisé | **Jellyseerr** (Seerr) → **Radarr** (films) / **Sonarr** (séries) |
| Notifications infra | **Gotify** |
| Supervision | **Uptime Kuma** sur l'endpoint `/health/backup` |
| Déploiement | **Docker** / **Docker Compose**, orchestré via **Portainer**, déployé depuis GitHub |
| Tests | `pytest` (dossier `tests/`, ~25 fichiers de tests) |

## 3. Point d'entrée et architecture applicative

```
main.py                      → bootstrap NiceGUI/FastAPI, monte le frontend React compilé,
                                initialise les schémas SQLite, démarre le scheduler de sync
backend/
  config.py                  → configuration via variables d'environnement (Config)
  api.py                     → routes REST principales (médias, recos, locations, admin, playback…)
  auth_api.py                → routes REST d'authentification (/api/auth/*)
  core/
    models.py                → modèles Pydantic (Media, Rental, Notification, UserMediaState,
                                RecommendationEvent, RecommendationSession…)
    store.py                 → MediaStore : accès SQLite (médias, locations, notifications,
                                épisodes, playback, recommandations)
    auth.py                  → AuthStore : comptes, rôles, sessions, mots de passe, reset par e-mail
    tmdb.py                  → client TMDB (httpx async)
    tmdb_relink.py           → re-liaison / correction de métadonnées TMDB
    jellyfin.py              → intégration Jellyfin (comptes, playback, disponibilité)
    arr.py                   → intégration Radarr / Sonarr
    seerr.py                 → intégration Jellyseerr (demandes de contenu)
    media_server.py          → orchestration de la synchronisation multi-services
    playback.py              → suivi de progression de lecture
    recommendations.py       → moteur de recommandation local (règles + scoring)
    gemini_recommendations.py→ passerelle optionnelle vers Gemini (quota, fallback local)
    scheduler.py             → tâches périodiques (sync média, nettoyage locations)
    backup.py                → sauvegardes SQLite automatiques + vérification d'intégrité
    email.py                 → envoi d'e-mails (SMTP Gmail) pour réinitialisation de mot de passe
    http.py                  → client HTTP partagé avec retry
    stats.py                 → agrégats statistiques
    mapping.py                → mapping/normalisation de données
frontend/                    → **legacy** : ancienne UI NiceGUI (Ivoire & Bordeaux), fichiers
                                sources absents du dépôt actuel (seuls les .pyc restent) ; remplacée
                                par proto-ui/
proto-ui/                    → application React (Vite) — UI actuelle
  src/
    App.jsx, main.jsx        → bootstrap React
    AuthGate.jsx              → garde d'authentification / écran de connexion
    AccountPanel.jsx          → gestion de compte utilisateur
    PasswordResetPage.jsx    → réinitialisation de mot de passe
    BackstagePrototype.jsx   → composant principal / bibliothèque
    components/
      FilmDetailView.jsx     → fiche film détaillée
      RecommendationFlow.jsx → parcours « Choisir un film » (questions adaptatives)
      AdminCenter.jsx        → centre d'administration
    library.js, series.js    → logique de bibliothèque et séries côté client
    api.js                   → client HTTP vers l'API FastAPI
legacy/2026-07-cleanup/      → code de la V1 archivé (NiceGUI, enrichissement Notion, scripts)
docs/
  backstage-authentication.md  → procédure d'authentification et de déploiement
  recommendation-optimizer.md  → conception du moteur de recommandation
tests/                       → suite pytest (API, auth, TMDB, Jellyfin, Radarr/Sonarr, locations,
                                recommandations, sauvegardes, playback…)
```

## 4. Modèle de données (Pydantic — `backend/core/models.py`)

- **`Media`** : entité film/série unique dans le catalogue commun (titre, type, statut, support, note, genres, synopsis, cast, affiche/backdrop, `tmdb_id`, `tmdb_ok`…). Le champ `is_watchlist` est une projection dépendant de l'utilisateur courant.
- **`Rental`** : location temporaire d'un contenu par un utilisateur.
  - `RentalStatus` : `requested → downloading → available → keep_requested → kept → expired / cancelled`.
  - `storage_policy` : `temporary` ou `permanent`.
  - `rental_scope` : `movie` ou `series`.
  - Traçabilité de décision admin (`decided_by`, `decided_at`, `keep_decision`).
- **`Notification`** : notification interne utilisateur (avec `dedupe_key`).
- **`UserMediaState`** : relation utilisateur↔média (statut personnel, note, avis, favori, watchlist, dates).
- **`RecommendationEvent` / `RecommendationSession`** : traçabilité fine du moteur de recommandation (types d'événements : `shown`, `picked`, `dismissed`, `more_like_this`, `less_like_this`, `question_answered`, `session_completed`, `skipped`, `not_now`, `hard_reject`, `already_seen`, `confirmed`).

Principe clé : **un contenu n'existe qu'une fois** dans le catalogue partagé ; chaque utilisateur a sa propre relation avec ce contenu (`UserMediaState`) — pas de duplication de la base par utilisateur.

## 5. API REST (`backend/api.py`, `backend/auth_api.py`)

Domaines de routes principaux :

- **Santé** : `GET /health`, `GET /health/backup` (supervisé par Uptime Kuma).
- **Médias** : CRUD `/medias`, recherche TMDB (`/tmdb/search`, `/tmdb/search/tv`, `/tmdb/search/person`), re-liaison TMDB, création depuis TMDB (films et séries), gestion des épisodes.
- **Personnel** : `PATCH /medias/{id}/personal` (statut, note, favori, watchlist propres à l'utilisateur).
- **Recommandations** : sessions et événements (`/recommendations/sessions`, `.../answers`, `.../confirm`, `.../finish`, `/recommendations/events`).
- **Disponibilité & lecture** : `/medias/{id}/availability`, `/medias/{id}/playback/manifest`, `/medias/{id}/playback/resource/...`, `/playback/sync`, `/playback/summary`.
- **Acquisition/locations** : `POST /medias/{id}/acquisition` (déclenche une demande), `/rentals`, `/rentals/{id}/keep`.
- **Administration** (protégées par `require_admin`) : file de demandes de conservation, aperçu de nettoyage, décisions (`keep`/`refuse`/`extend`), statut de stockage, tableau de bord admin, sauvegarde manuelle et vérification, synchronisation/import media-server, activité serveur.
- **Notifications** : liste et marquage lu.
- **Authentification** (`/api/auth/*`) : setup initial (création admin), login, changement de mot de passe, mot de passe oublié / reset par e-mail, `me`, gestion des appareils/sessions (liste, révocation, révocation des autres sessions), gestion des utilisateurs (liste, création, modification, suppression, association à un compte Jellyfin) — réservée aux administrateurs pour la gestion multi-utilisateurs.

## 6. Fonctionnalités livrées (état au 06/08/2026)

D'après `BACKSTAGE_VISION_ARCHITECTURE_ROADMAP.md` (section « État de référence ») :

- Dockerisation et déploiement Portainer depuis GitHub.
- Comptes, rôles admin/utilisateur, sessions, appareils mémorisés, changement de mot de passe, reset par e-mail (Gmail SMTP).
- Catalogue commun, listes personnelles, favoris, historique de lecture.
- Liaison individuelle Jellyfin + synchronisation de progression.
- Demandes de films/séries via Jellyseerr, Radarr, Sonarr.
- Détection de contenu déjà disponible + bouton lecture dans la fiche.
- Locations temporaires : quota (5 locations actives/utilisateur), expiration, suivi de lecture ; comptes admin exclus (demandes permanentes).
- Demandes de conservation définitive avec validation/refus/prolongation admin + notifications.
- Protection contre suppression automatique des contenus permanents.
- Quotas de stockage, seuil d'espace libre, simulation de nettoyage.
- Tableau de bord et activité serveur (admin uniquement).
- Notifications automatiques (expiration, disponibilité, alerte stockage).
- Prise en charge initiale des locations de séries.
- Sauvegardes SQLite automatiques + vérification d'intégrité + endpoint santé public.
- Supervision Uptime Kuma + alertes Gotify.
- Mode **« Choisir un film »** (recommandation interactive) : persistance SQLite par utilisateur, signaux distincts (affiché/choisi/ignoré/déjà vu/refus durable), moteur de scoring local (notes, genres TMDB, favoris, watchlist, nouveauté, diversité), questions adaptatives (max 5, anti-répétition), 2 sessions quotidiennes/utilisateur (admin illimité, fuseau Europe/Paris), passerelle Gemini optionnelle (2 appels max/session, validation des IDs TMDB, fallback local).

## 7. En cours / à venir

- **Phase 14 (conception validée, implémentation à faire)** : fiche film centrée/plein écran (remplace le panneau latéral), Centre d'administration unifié (vue d'ensemble, activité serveur, demandes/locations, conservation, utilisateurs, stockage, services, paramètres).
- Gestion avancée des séries par saison/épisode (au-delà du modèle initial).
- Sauvegardes sur disque dédié (en attente de réception/montage matériel).
- Déploiement versionné via GitHub Container Registry + stratégie dev/stable (non prioritaire).

## 8. Règles métier notables (pour toute analyse ou modification)

- **Séparation catalogue / données utilisateur** : ne jamais dupliquer un `Media` par utilisateur ; passer par `UserMediaState`/`Rental`.
- **Suppression sécurisée** : un contenu ne doit être supprimé que si aucune location active, aucune demande de conservation en attente, aucun visionnage en cours, pas de marquage protégé/permanent, pas d'incohérence de sync — la suppression suit la *dernière* location active, pas la première.
- **Durées de location par défaut** : 21 jours avant première lecture, recalcul à 7 jours après le début, suppression programmable 48h après la fin, sauf demande de conservation en attente.
- **Comptes Jellyfin individuels obligatoires** : jamais de compte Jellyfin admin partagé pour plusieurs utilisateurs Backstage.
- **Aucune commande requise pour les utilisateurs finaux** : toute action courante doit être possible depuis l'UI Backstage (le rôle de Backstage est de masquer Jellyfin/Radarr/Sonarr/Seerr/Docker).
- **Secrets** : jamais commités dans GitHub ; uniquement dans `.env` ou l'environnement Portainer.
- **Mapping Notion (V1 legacy uniquement)** : les noms de propriétés Notion étaient codés en dur dans l'ancien `backend/core/notion.py` (désormais dans `legacy/`) — non pertinent pour la V2 mais utile si on doit comprendre l'historique de migration.

## 9. Environnement / configuration (`backend/config.py`)

Variables d'environnement principales : `TMDB_API_KEY`, `DB_PATH`, `PORT` (défaut 8090), `GEMINI_API_KEY`/`GEMINI_MODEL`, `RADARR_URL`/`RADARR_API_KEY`, `SONARR_URL`/`SONARR_API_KEY`, `SEERR_URL`/`SEERR_API_KEY`, `JELLYFIN_URL`/`JELLYFIN_API_KEY`/`JELLYFIN_SERVER_ID`, `MEDIA_SYNC_INTERVAL_SEC`, `MIN_FREE_GB`, `TEMPORARY_MAX_GB`, `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, `BACKUP_INTERVAL_HOURS`, `SMTP_*` (reset mot de passe par e-mail), `BACKSTAGE_PUBLIC_URL`. Chaque intégration externe (Radarr/Sonarr/Seerr/Jellyfin) est activable indépendamment selon la présence de sa clé API (`*_enabled()`).

## 10. Déploiement de référence

- Dépôt GitHub : `film-notion` (nom historique du dépôt, projet renommé Backstage).
- Branche suivie par Portainer : `agent/backstage-docker-deployment`.
- Branche stable : `main`.
- Serveur cible : HP ProDesk 600 G4 Mini (i5-8500T, 16 Go RAM, SSD 500 Go + disque média séparé), Ubuntu Server, Docker + Portainer.
- Volume de données : `/srv/data/backstage` monté sur `/data` dans le conteneur ; base SQLite à `/data/backstage.db` (ou `/srv/data/backstage/backstage.db` côté hôte).
- Mise à jour actuelle : `git pull` + `docker compose up -d --build`, puis « Pull and redeploy » dans Portainer.
- Santé : `/health` (public) et `/health/backup` (surveillé par Uptime Kuma toutes les 5 min, alertes via Gotify).

## 11. Ce qu'une IA doit garder à l'esprit avant de proposer des changements

1. Le vrai frontend actif est `proto-ui/` (React/Vite) — pas `frontend/` (NiceGUI, legacy et incomplet dans le dépôt).
2. Le `README.md` racine est partiellement obsolète (décrit la V1 Notion) ; privilégier `BACKSTAGE_VISION_ARCHITECTURE_ROADMAP.md` et ce document pour l'état réel.
3. Toute nouvelle fonctionnalité multi-utilisateur doit respecter la séparation catalogue commun / état par utilisateur.
4. Le projet est mono-développeur, usage domestique réel (pas un produit commercial) — privilégier simplicité et fiabilité sur l'abstraction.
5. Le disque de sauvegarde dédié n'est pas encore installé : ne pas considérer le SSD système comme une stratégie de sauvegarde fiable à long terme.
