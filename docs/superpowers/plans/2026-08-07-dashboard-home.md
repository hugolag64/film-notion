# Dashboard d’accueil Sprint 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un accueil dashboard connecté qui agrège reprise, recommandations, activité et disponibilité, puis l’afficher après connexion.

**Architecture:** Ajouter un assembleur pur dans `backend/core/dashboard.py`, testé indépendamment, puis une route `GET /api/dashboard` qui collecte les données utilisateur et délègue l’assemblage. Ajouter `DashboardHome.jsx` comme composant de présentation et intégrer un état de navigation `dashboard` dans `BackstagePrototype.jsx` sans réécrire la bibliothèque existante.

**Tech Stack:** FastAPI, Pydantic, SQLite store existant, React 19, Tailwind CSS 4, pytest, oxlint, Vite.

## Global Constraints

- Les données personnelles sont toujours filtrées par l’utilisateur courant.
- Les limites sont 6 reprises, 8 recommandations, 10 activités et 8 disponibilités.
- Les services optionnels indisponibles ne doivent pas faire échouer la route globale.
- Les tests de comportement sont écrits avant le code de production.
- Les modifications sont réalisées dans `codex/dashboard-home`, jamais dans le checkout `main` sale.

---

### Task 1: Assembleur de payload dashboard

**Files:**
- Create: `backend/core/dashboard.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Produces `build_dashboard_payload(medias, states, playback, availabilities, rentals, notifications, recommendations, now) -> dict`.
- The returned dictionary contains `continue_watching`, `recommendations`, `activity`, `availability`, and `last_synced_at`.

- [ ] **Step 1: Write the failing tests** for progress filtering, chronological mixed activity, and availability labels/data joins.
- [ ] **Step 2: Run `pytest tests/test_dashboard.py -q` and verify the tests fail because the module/function is missing.**
- [ ] **Step 3: Implement the smallest pure assembler using Pydantic models, joining media by id and excluding played/95%+ playback from `continue_watching`.**
- [ ] **Step 4: Run `pytest tests/test_dashboard.py -q` and verify all tests pass.**
- [ ] **Step 5: Commit `feat: assemble dashboard payload`.**

### Task 2: API dashboard agrégé

**Files:**
- Modify: `backend/api.py` near the existing playback/recommendation serializers and routes
- Modify: `proto-ui/src/api.js`
- Test: `tests/test_dashboard_api.py`

**Interfaces:**
- Adds `GET /api/dashboard` behind `get_current_user`.
- Adds `fetchDashboard()` returning the JSON payload.

- [ ] **Step 1: Write failing API tests** that use a temporary store and authenticated user, asserting user-scoped playback/rentals and a successful response when recommendation discovery raises an HTTP error.
- [ ] **Step 2: Run `pytest tests/test_dashboard_api.py -q` and verify the tests fail because the route is absent.**
- [ ] **Step 3: Implement parallel store reads, call `_recommendation_pool` with empty session preferences, catch optional TMDB/network failures, and pass all values to `build_dashboard_payload`.**
- [ ] **Step 4: Run `pytest tests/test_dashboard_api.py -q tests/test_dashboard.py -q` and verify all pass.**
- [ ] **Step 5: Commit `feat: expose dashboard aggregation endpoint`.**

### Task 3: Composant DashboardHome

**Files:**
- Create: `proto-ui/src/components/DashboardHome.jsx`
- Modify: `proto-ui/src/index.css` only if a small scrollbar/accessibility rule is needed

**Interfaces:**
- `DashboardHome({ data, isDarkMode, loading, error, onRetry, onOpenMedia, onResume, onAddWatchlist, onWhyRecommendation, onOpenLibrary, onOpenRecommendations })`.
- Renders the four approved sections and handles loading, error, empty and responsive states locally.

- [ ] **Step 1: Add a source-level component test only if the repository’s frontend test runner is already available; otherwise use the required lint/build checks as the executable verification for this presentation-only component.**
- [ ] **Step 2: Implement the component with semantic headings, accessible buttons, horizontal recommendation scrolling, progress bars, explicit availability text and large poster cards.**
- [ ] **Step 3: Run `npm run lint` and fix every new lint finding.**
- [ ] **Step 4: Commit `feat: add dashboard home presentation`.**

### Task 4: Integrate dashboard as authenticated home

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`

**Interfaces:**
- Adds dashboard state and `fetchDashboard()` loading tied to `user?.id`.
- Keeps existing library actions as callbacks, including film/series opening, playback, watchlist mutation and library navigation.

- [ ] **Step 1: Add the failing integration expectation to the existing behavior contract by making the dashboard view the initial `activeView` value and verifying the old library remains reachable through navigation.**
- [ ] **Step 2: Implement the header/sidebar navigation with `Accueil` and `Bibliothèque`, render `DashboardHome` when active, and preserve the current catalogue markup when the library view is active.**
- [ ] **Step 3: Connect recommendation cards to local TMDB detail data or the existing recommendation flow without introducing a second recommendation session.**
- [ ] **Step 4: Run `npm run lint` and `npm run build`.**
- [ ] **Step 5: Commit `feat: make dashboard the post-login home`.**

### Task 5: Full verification and handoff

**Files:**
- Modify: none unless verification reveals a defect

- [ ] **Step 1: Run `pytest` from the repository worktree using the existing project virtualenv.**
- [ ] **Step 2: Run `npm run lint` and `npm run build` from `proto-ui`.**
- [ ] **Step 3: Run `git diff --check` and inspect `git status --short`.**
- [ ] **Step 4: Review the diff against `docs/superpowers/specs/2026-08-07-dashboard-home-design.md`.**
- [ ] **Step 5: Use the finishing-a-development-branch workflow to report integration options.**
