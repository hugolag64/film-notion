# Media Storage Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only, confirmation-based storage cleanup flow that removes selected films and their files from Radarr while preserving their Backstage records.

**Architecture:** Add a Radarr delete primitive, a backend storage-cleanup service/API that produces protected candidates and executes validated deletions, and an AdminCenter section that previews candidates before deletion. The existing media sync then reconciles Jellyfin and makes deleted films requestable again.

**Tech Stack:** FastAPI, Pydantic, SQLite MediaStore, Radarr v3 API, React/Vite, pytest, oxlint, Vite build.

## Global Constraints

- Only authenticated administrators may list candidates or delete media.
- Deletion must call Radarr with `deleteFiles=true`; the frontend must never delete paths directly.
- Favorites, active rentals, media added within 14 days, media watched within 30 days, and manually protected media are not deletable.
- Backstage media rows remain after deletion.
- Every deletion must be confirmed in the UI and recorded in the admin activity log.

### Task 1: Define protection and candidate data

**Files:**
- Modify: `backend/core/media_server.py`
- Modify: `backend/core/store.py`
- Test: `tests/test_media_server.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produce `StorageCandidate` with `media_id`, `title`, `tmdb_id`, `radarr_id`, `size_bytes`, `added_at`, `last_played_at`, `is_favorite`, `has_active_rental`, `protected`, and `protection_reasons`.
- Produce `MediaServerService.storage_candidates()` returning `list[StorageCandidate]`.
- Produce `MediaStore.get_storage_protection(media_id)` and `MediaStore.set_storage_protection(media_id, protected)`.

- [ ] Write tests for a candidate with a Radarr file and no protection.
- [ ] Write tests proving favorites, active rentals, recent additions, recent playback, and manual protection set `protected=True` with explicit reasons.
- [ ] Run `python -m pytest tests/test_media_server.py tests/test_store.py -q` and verify the new tests fail before implementation.
- [ ] Add the minimal SQLite protection table/migration and candidate aggregation logic.
- [ ] Run the same targeted tests and verify they pass.
- [ ] Run `python -m pytest tests/test_media_server.py tests/test_store.py -q`.

### Task 2: Add safe Radarr deletion and admin API

**Files:**
- Modify: `backend/core/arr.py`
- Modify: `backend/api.py`
- Test: `tests/test_arr.py`
- Test: `tests/test_auth_api.py`

**Interfaces:**
- Add `RadarrClient.delete_movie(movie_id: int, *, delete_files: bool = True) -> dict[str, Any]` using `DELETE /api/v3/movie/{movie_id}?deleteFiles=true`.
- Add `GET /api/admin/storage/candidates` returning serialized candidates.
- Add `POST /api/admin/storage/candidates/{media_id}/protection` accepting `{protected: bool}`.
- Add `DELETE /api/admin/storage/candidates/{media_id}` returning `{media_id, freed_bytes, synced}`.

- [ ] Write API-client tests asserting the DELETE path and `deleteFiles=true` query parameter.
- [ ] Write authorization tests asserting non-admin requests receive 403.
- [ ] Write deletion tests asserting protected media and missing Radarr entries are rejected.
- [ ] Run `python -m pytest tests/test_arr.py tests/test_auth_api.py -q` and verify the new tests fail before implementation.
- [ ] Implement the Radarr delete call and admin routes with validation, protection checks, audit logging, and post-delete sync.
- [ ] Run the targeted tests and verify they pass.

### Task 3: Build the AdminCenter storage interface

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/components/AdminCenter.jsx`
- Test: `tests/test_catalogue_playback_ui.py`

**Interfaces:**
- Add API helpers `fetchStorageCandidates`, `setStorageProtection`, and `deleteStorageCandidate`.
- Add an AdminCenter section named `storage-cleanup` with refresh, protection toggle, and delete confirmation actions.

- [ ] Add source-contract tests for the new API helpers, admin section, protected state, confirmation text, and displayed size.
- [ ] Run `python -m pytest tests/test_catalogue_playback_ui.py -q` and verify the new assertions fail before implementation.
- [ ] Implement the table, filters, protected badges, size formatting, confirmation dialog, success/error feedback, and refresh behavior.
- [ ] Run the UI contract tests.
- [ ] Run `npm run lint` and `npm run build` from `proto-ui`.

### Task 4: Verify integration and deployment readiness

**Files:**
- Test: `tests/test_media_server.py` for the post-delete resynchronization regression case.
- Modify: `docs/superpowers/specs/2026-08-08-media-storage-cleanup-design.md` only when an implementation decision changes an approved rule.

- [ ] Run the complete Python suite with `python -m pytest -q`.
- [ ] Run `npm run lint` and `npm run build` from `proto-ui`.
- [ ] Verify `git diff --check` and inspect the candidate/deletion diff for unintended file changes.
- [ ] Document the deployment command using the tracked `compose.yml`/`stack.env` workflow.
