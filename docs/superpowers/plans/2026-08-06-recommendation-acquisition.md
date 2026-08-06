# Recommendation Confirmation and Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm the selected recommendation into the library and request its download using administrator defaults while guaranteeing a different Gemini question path per session.

**Architecture:** A protected confirmation endpoint validates the completed session, creates or reuses the TMDB media, then delegates acquisition to the existing `MediaServerService`. Provider defaults are resolved server-side from Radarr/Seerr configuration. Plan markers are recorded at session start so abandoned sessions also influence future Gemini planning.

**Tech Stack:** FastAPI/Python, Pydantic, SQLite, Radarr/Seerr adapters, React/Vite.

## Global Constraints

- Quality profile name: `1080 FR - max 10go`.
- Two Gemini calls remain mandatory per non-empty recommendation session.
- Confirmation must be idempotent and user-scoped.
- A failed remote acquisition must not remove a successfully created library item.

---

### Task 1: Persist varied Gemini plans

**Files:** `backend/api.py`, `backend/core/gemini_recommendations.py`, `tests/test_recommendation_integration.py`, `tests/test_gemini_recommendations.py`

- [ ] Add a planner `recent_plans` payload and record `plan:<axis>` events immediately after plan selection.
- [ ] Reject an exact recent plan and rotate locally while retaining two Gemini calls.
- [ ] Test an abandoned session influencing the next plan and test that repeated plan output is replaced.
- [ ] Commit `fix: vary recommendation plans across sessions`.

### Task 2: Resolve administrator acquisition defaults

**Files:** `backend/config.py`, `.env.example`, `backend/core/media_server.py`, `tests/test_media_server.py`

- [ ] Add `RADARR_DEFAULT_QUALITY_PROFILE_NAME=1080 FR - max 10go` and an optional root-folder default.
- [ ] Resolve the exact quality profile by name and the configured/first root folder without accepting client overrides.
- [ ] Test missing profile, configured root folder, and first-folder fallback.
- [ ] Commit `feat: resolve administrator acquisition defaults`.

### Task 3: Confirm a recommendation and request acquisition

**Files:** `backend/api.py`, `backend/core/models.py`, `tests/test_recommendation_acquisition.py`

- [ ] Add the confirmation request model and protected endpoint.
- [ ] Validate owner and completed recommendation TMDB ID.
- [ ] Create or reuse the library media with no rating, then call the existing acquisition service once.
- [ ] Return the media plus availability or a retryable download error.
- [ ] Test success, duplicate confirmation, invalid TMDB ID, and provider failure after local creation.
- [ ] Commit `feat: confirm recommendations with automatic acquisition`.

### Task 4: Wire the result action and verify

**Files:** `proto-ui/src/api.js`, `proto-ui/src/components/RecommendationFlow.jsx`, tests/docs as needed

- [ ] Add the confirm request client and a modern `Ajouter et télécharger` result action.
- [ ] Show success, existing-download, and download-error states without losing the result.
- [ ] Run `py -m pytest -q`, `npm run lint`, `npm run build`, and `git diff --check`.
- [ ] Commit `feat: add recommendation acquisition action`.
