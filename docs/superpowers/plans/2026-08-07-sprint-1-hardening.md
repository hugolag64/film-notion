# Sprint 1 Hardening Implementation Plan

Goal: secure authorization, personal progress, playback, auth limits and deployment without a global rewrite.

Architecture: keep FastAPI/SQLite and current dependencies. Add route guardrails, a per-user episode table, a small in-process limiter and a V2 deployment guide. Every behavior is introduced by a failing test and a minimal implementation.

Tech stack: Python 3.11, FastAPI, Pydantic, SQLite, pytest, React/Vite and Docker Compose.

## Constraints

- Preserve user changes on main.
- Keep personal mutations working.
- New production behavior requires a test-first cycle.
- Do not add an external rate-limit dependency.
- Keep SQLite migrations idempotent.

## Task 1 - Timezone and secure configuration

Files: requirements.txt, .env.example, docker-compose.yml, backend/config.py, tests/test_config.py.

- [ ] Test rate-limit defaults and tzdata presence.
- [ ] Run tests and observe the failure.
- [ ] Add pinned tzdata, auth limit settings, BACKSTAGE_COOKIE_SECURE and Compose propagation.
- [ ] Run focused tests.
- [ ] Commit: chore: make timezone and security config reproducible.

## Task 2 - Shared catalog authorization

Files: backend/api.py, tests/test_auth_api.py.

- [ ] Test regular-user 403 responses for media update, TMDB creation, relink and series refresh.
- [ ] Run tests and observe the failure.
- [ ] Add route-level require_admin dependencies without changing personal update routes.
- [ ] Run API and auth tests.
- [ ] Commit: fix: restrict shared catalog mutations to admins.

## Task 3 - Per-user episode progress

Files: backend/core/models.py, backend/core/store.py, backend/api.py, tests/test_series.py and tests/test_store.py.

- [ ] Test two users viewing the same episode with independent watched states.
- [ ] Run tests and observe the failure.
- [ ] Add UserEpisodeState, user_episode_state, store methods and user-aware API responses.
- [ ] Run series and store tests.
- [ ] Commit: fix: scope episode progress per user.

## Task 4 - Playback access

Files: backend/api.py, backend/core/store.py, tests/test_auth_api.py and tests/test_media_server.py.

- [ ] Test active owner rental, expired rental, unrelated user, kept rental and administrative media.
- [ ] Run tests and observe the failure.
- [ ] Add _ensure_playback_access and call it before availability, manifest and resource proxying.
- [ ] Keep 404 for missing media and 403 for authenticated users without access.
- [ ] Run focused tests.
- [ ] Commit: fix: enforce rental access on playback.

## Task 5 - Authentication rate limiting

Files: backend/core/rate_limit.py, backend/auth_api.py, backend/config.py, tests/test_rate_limit.py and tests/test_auth_api.py.

- [ ] Test sliding window, block expiration, clear and HTTP 429 responses.
- [ ] Run tests and observe the failure.
- [ ] Implement RateLimiter and apply it to login and forgot-password using normalized identity plus client IP.
- [ ] Include Retry-After and clear successful login attempts.
- [ ] Run auth tests.
- [ ] Commit: feat: rate limit authentication endpoints.

## Task 6 - Secure deployment documentation

Files: README.md, docs/SECURE_DEPLOYMENT.md, tests/test_documentation.py.

- [ ] Test the required production guardrails.
- [ ] Run the documentation test and observe the failure.
- [ ] Document HTTPS/VPN or reverse proxy, cookie security, secrets, backup destination, restoration, rollback and the single-instance limiter.
- [ ] Run documentation tests.
- [ ] Commit: docs: document secure deployment and recovery.

## Task 7 - Full verification

- [ ] Run .venv/Scripts/python.exe -m pytest with zero failures.
- [ ] Run npm run lint and npm run build in proto-ui.
- [ ] Review the security diff and confirm personal mutation routes remain available.
- [ ] Do not add generated logs or secrets.

End of plan.
