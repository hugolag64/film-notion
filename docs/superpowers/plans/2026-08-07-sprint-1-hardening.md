# Sprint 1 Hardening Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: sécuriser les autorisations, la progression utilisateur, le playback, les limites de requêtes et le déploiement de Backstage sans réécriture globale.

Architecture: conserver FastAPI/SQLite et les dépendances actuelles. Ajouter des garde-fous au niveau des routes, une table SQLite personnelle pour les épisodes, un limiter mémoire isolé dans un module d’authentification et une documentation de déploiement V2. Chaque comportement sera introduit par un test rouge puis une implémentation minimale.

Tech Stack: Python 3.11, FastAPI, Pydantic, SQLite, pytest, React/Vite, Docker Compose.

## Global Constraints

- Ne pas écraser les modifications utilisateur de main.
- Ne pas modifier la sémantique des actions personnelles existantes.
- Toute production code nouvelle doit avoir un test qui échoue avant l’implémentation.
- Ne pas ajouter de dépendance de rate limiting externe pour une instance unique.
- Les migrations SQLite doivent rester rétrocompatibles.

---

### Task 1: Dépendance timezone et configuration sécurisée

Files: requirements.txt, .env.example, docker-compose.yml, backend/config.py, tests/test_config.py.

- [ ] Écrire les tests vérifiant les limites login/reset et la présence de tzdata dans requirements.txt.
- [ ] Lancer .venv/Scripts/python.exe -m pytest tests/test_config.py -q et constater l’échec.
- [ ] Ajouter tzdata==2025.2, les paramètres AUTH_RATE_LIMIT_WINDOW_SEC, AUTH_RATE_LIMIT_MAX_ATTEMPTS, AUTH_RATE_LIMIT_BLOCK_SEC, puis les variables au compose et à .env.example.
- [ ] Relancer le test ciblé et obtenir PASS.
- [ ] Commit : chore: make timezone and security config reproducible.

### Task 2: Protéger les mutations du catalogue partagé

Files: backend/api.py, tests/test_auth_api.py ou tests/test_api.py.

- [ ] Écrire des tests HTTP avec un utilisateur normal sur PATCH media, POST create-from-TMDB, POST relink-TMDB et POST refresh-series ; attendre 403 avant tout appel externe.
- [ ] Lancer les tests ciblés et constater l’échec.
- [ ] Ajouter Depends(require_admin) aux routes de catalogue ; ne pas modifier update_personal_media.
- [ ] Relancer tests/test_auth_api.py et tests/test_api.py.
- [ ] Commit : fix: restrict shared catalog mutations to admins.

### Task 3: Rendre le suivi d’épisodes personnel

Files: backend/core/models.py, backend/core/store.py, backend/api.py, tests/test_series.py, tests/test_store.py.

- [ ] Écrire un test avec deux utilisateurs, une série et un épisode : user A marque vu, user B reste non vu.
- [ ] Lancer le test et constater l’échec causé par l’état partagé.
- [ ] Ajouter UserEpisodeState, la table user_episode_state, les méthodes store get/set/list et les réponses user-aware.
- [ ] Faire utiliser current.user par GET /medias/{media_id}/episodes et PATCH /episodes/{episode_id}.
- [ ] Relancer les tests de série et de store.
- [ ] Commit : fix: scope episode progress per user.

### Task 4: Enforcer les droits de playback

Files: backend/api.py, éventuellement backend/core/store.py, tests/test_auth_api.py, tests/test_media_server.py.

- [ ] Écrire les tests : location active autorisée, location expirée refusée, autre utilisateur refusé, location conservée autorisée, contenu permanent autorisé.
- [ ] Lancer les tests ciblés et constater l’échec.
- [ ] Ajouter un helper _ensure_playback_access(current, media_id, store) ; appliquer les règles avant URL ou proxy Jellyfin.
- [ ] Retourner 404 pour média absent et 403 pour utilisateur authentifié sans droit ; ne pas appeler Jellyfin dans le cas refusé.
- [ ] Relancer les tests ciblés.
- [ ] Commit : fix: enforce rental access on playback.

### Task 5: Ajouter le rate limiting login/reset

Files: backend/core/rate_limit.py, backend/auth_api.py, backend/config.py, tests/test_rate_limit.py, tests/test_auth_api.py.

- [ ] Écrire les tests de fenêtre, blocage, remise à zéro après succès et réponses HTTP 429.
- [ ] Lancer les tests et constater l’échec.
- [ ] Créer RateLimiter(max_attempts, window_seconds, block_seconds), RateLimitDecision et purger les entrées expirées.
- [ ] Utiliser une clé combinant identifiant normalisé et IP ; inclure Retry-After ; charger la configuration.
- [ ] Relancer les tests ciblés et les tests d’authentification.
- [ ] Commit : feat: rate limit authentication endpoints.

### Task 6: Documenter le déploiement sécurisé

Files: README.md, BACKSTAGE_OVERVIEW.md, docs/SECURE_DEPLOYMENT.md, tests/test_documentation.py.

- [ ] Écrire un test qui exige HTTPS/reverse proxy ou VPN, BACKSTAGE_COOKIE_SECURE=1, rotation des secrets, sauvegarde hors volume, restauration et limite mono-instance du limiter.
- [ ] Lancer le test et constater l’échec.
- [ ] Rédiger le guide, relier README et OVERVIEW à ce guide et documenter rollback, health checks et logs.
- [ ] Relancer le test documentaire.
- [ ] Commit : docs: document secure deployment and recovery.

### Task 7: Vérification complète

- [ ] Lancer .venv/Scripts/python.exe -m pytest et obtenir zéro échec.
- [ ] Lancer npm run lint et npm run build dans proto-ui.
- [ ] Relire le diff sécurité pour confirmer que les mutations personnelles restent accessibles et qu’aucun chemin playback non protégé ne subsiste.
- [ ] Ne pas ajouter de logs générés ni de secrets.

