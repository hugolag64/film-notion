# Progression Jellyfin par utilisateur Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchroniser la progression Jellyfin séparément pour chaque compte Backstage associé et afficher ses reprises de lecture.

**Architecture:** Ajouter une table `playback_progress` par utilisateur et élément Jellyfin. Le client Jellyfin normalise les éléments d’un utilisateur, `MediaServerService` les rapproche des films et épisodes locaux, puis FastAPI expose un résumé limité à l’utilisateur connecté. Le scheduler synchronise tous les utilisateurs actifs associés.

**Tech Stack:** Python, SQLite, FastAPI, httpx, Pydantic, pytest, React 19, Vite.

## Global Constraints

- Les données d’Hugo et d’Ophélie ne doivent jamais être mélangées.
- Un élément est terminé si Jellyfin le signale lu ou si sa progression atteint 95 %.
- Une erreur Jellyfin conserve les données déjà enregistrées.
- Les notes, favoris et statuts locaux ne sont jamais modifiés par la synchronisation.
- Le proxy HLS actuel reste inchangé dans cette phase.

---

### Task 1: Modèle de progression, stockage et client Jellyfin

**Files:**
- Create: `backend/core/playback.py`
- Modify: `backend/core/store.py`
- Modify: `backend/core/jellyfin.py`
- Test: `tests/test_playback.py`
- Test: `tests/test_jellyfin.py`

**Interfaces:**
- `PlaybackProgress` contient `backstage_user_id`, `jellyfin_id`, `media_id`, `episode_id`, `title`, `series_title`, `season_number`, `episode_number`, `position_ticks`, `runtime_ticks`, `percent`, `played`, `last_played_at`, `synced_at`.
- `MediaStore.upsert_playback(progress)`, `list_resume_progress(user_id)`, `list_recently_completed(user_id)`, `list_next_episodes(user_id)`.
- `JellyfinClient.user_playback(user_id) -> list[dict]`.

- [ ] Écrire les tests de persistance multi-utilisateur, d’isolation et du seuil de 95 %.
- [ ] Écrire les tests HTTP pour `/Users/{user_id}/Items`, la normalisation `UserData` et les erreurs distantes.
- [ ] Créer la migration SQLite idempotente et les requêtes de résumé.
- [ ] Implémenter le rapprochement par `jellyfin_id`, puis TMDB et saison/épisode.
- [ ] Vérifier `py -m pytest -q tests/test_playback.py tests/test_jellyfin.py`.
- [ ] Committer `feat: add per-user Jellyfin playback storage`.

### Task 2: Synchronisation backend, routes et scheduler

**Files:**
- Modify: `backend/core/media_server.py`
- Modify: `backend/core/scheduler.py`
- Modify: `backend/api.py`
- Test: `tests/test_media_server.py`
- Test: `tests/test_auth_api.py`

**Interfaces:**
- `MediaServerService.sync_playback(backstage_user_id, jellyfin_user_id)`.
- `MediaServerService.playback_summary(backstage_user_id)`.
- `POST /api/playback/sync` et `GET /api/playback/summary`, authentifiés et limités à l’utilisateur courant.

- [ ] Ajouter les tests de synchronisation, de compte non associé, d’erreur Jellyfin et de séparation entre deux utilisateurs.
- [ ] Implémenter la synchronisation avec le `jellyfin_user_id` fourni par `AuthUser`.
- [ ] Faire parcourir au scheduler les utilisateurs actifs associés sans bloquer la synchronisation média existante.
- [ ] Vérifier `py -m pytest -q tests/test_media_server.py tests/test_auth_api.py`.
- [ ] Committer `feat: sync per-user Jellyfin playback`.

### Task 3: Résumé de progression dans React

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`

**Interfaces:**
- `fetchPlaybackSummary()` et `syncPlayback()` consomment les deux routes backend.
- Le résumé contient `resume`, `next_episodes`, `recently_completed`, `linked` et `last_synced_at`.

- [ ] Charger le résumé après authentification et déclencher une synchronisation légère avant affichage.
- [ ] Afficher uniquement les sections non vides avec titre, progression et action de lecture existante.
- [ ] Afficher un état explicite si aucun compte Jellyfin n’est associé.
- [ ] Vérifier `npm --prefix proto-ui run lint` et `npm --prefix proto-ui run build`.
- [ ] Committer `feat: show per-user Jellyfin playback`.

### Task 4: Validation et publication

**Files:**
- Modify: `docs/backstage-authentication.md`

- [ ] Exécuter `py -m pytest -q`.
- [ ] Exécuter `docker compose config --quiet`.
- [ ] Vérifier que les données existantes et le proxy HLS restent inchangés.
- [ ] Documenter la synchronisation et le comportement d’un compte non associé.
- [ ] Pousser `main` sur GitHub.
