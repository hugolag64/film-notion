# Locations temporaires V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user temporary film rentals with a five-film active quota, 21-day availability expiry, seven-day post-first-play expiry, and conservation requests without automatic deletion.

**Architecture:** Store rentals in a dedicated SQLite table linked to `media` and `users`. Keep the existing global media-server availability separate from per-user rental state. Update rentals at acquisition, media synchronization, and Jellyfin playback synchronization; expose only the current user’s rentals to regular users.

**Tech Stack:** FastAPI, SQLite, Pydantic, React/Vite, existing AuthStore/MediaStore, Jellyfin playback sync.

## Global Constraints

- Maximum five active rentals per Backstage user.
- Active states are `requested`, `downloading`, `available`, and `keep_requested`.
- Initial expiry is 21 days from Jellyfin availability.
- First playback changes expiry to seven days from first playback.
- No file deletion, Radarr deletion, cleanup job, or automatic expiration mutation beyond status/display in this V1.
- All timestamps are UTC and all API access is authenticated.

---

### Task 1: Rental persistence

**Files:**
- Modify: `backend/core/store.py`
- Modify: `backend/core/models.py` if shared response models are needed
- Test: `tests/test_store.py`

**Interfaces:**
- Produce `Rental` and `RentalStatus` models.
- Produce `create_rental`, `get_rental`, `list_user_rentals`, `count_active_rentals`, `find_active_rental`, `update_rental`, and `mark_rental_available` store methods.

- [ ] Write failing tests for schema creation, five-rental counting, duplicate active rental lookup, and per-user isolation.
- [ ] Run the focused store tests and verify they fail because the rental table and methods do not exist.
- [ ] Add the additive `media_rentals` table, active partial unique index, Pydantic model, and store methods.
- [ ] Run the focused store tests and verify they pass.
- [ ] Commit the persistence slice.

### Task 2: Acquisition and rental API

**Files:**
- Modify: `backend/api.py`
- Modify: `backend/core/media_server.py`
- Modify: `proto-ui/src/api.js`
- Test: `tests/test_auth_api.py`, `tests/test_media_server.py`

**Interfaces:**
- `POST /api/medias/{media_id}/acquisition` uses the authenticated user, rejects a sixth active rental with HTTP 409, reuses an existing active rental, and creates a rental after a successful media request.
- `GET /api/rentals` returns only the current user’s rentals.
- `POST /api/rentals/{rental_id}/keep` changes only the owner’s rental to `keep_requested`.

- [ ] Write failing API tests for quota rejection, duplicate reuse, owner isolation, and keep requests.
- [ ] Run the focused API tests and verify they fail.
- [ ] Implement authenticated rental creation, quota checking, serialization, and keep-request authorization.
- [ ] Run the focused API tests and verify they pass.
- [ ] Commit the API slice.

### Task 3: Media and playback synchronization

**Files:**
- Modify: `backend/core/media_server.py`
- Modify: `backend/core/store.py`
- Test: `tests/test_media_server.py`, `tests/test_auth_api.py`

**Interfaces:**
- When global availability becomes `available`, active rentals for the media receive `available_at` and `expires_at = available_at + 21 days`.
- When playback sync resolves a rental owner’s first playback, set `first_played_at` and `expires_at = first_played_at + 7 days`.
- `keep_requested` rentals do not receive a new expiry.

- [ ] Write failing synchronization tests for 21-day availability, seven-day first playback, and conservation suspension.
- [ ] Run the focused synchronization tests and verify they fail.
- [ ] Implement store updates at the existing media-sync and playback-sync seams.
- [ ] Run the focused synchronization tests and verify they pass.
- [ ] Commit the synchronization slice.

### Task 4: Rental interface

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/api.js`
- Test: `tests/test_catalogue_playback_ui.py`

**Interfaces:**
- Load the current user’s rentals and show the owner’s state and expiry in the relevant film detail view.
- Show `Demander à conserver` only for the owner’s available rental.
- Replace the acquisition action with the rental state when an active rental exists.

- [ ] Write failing source-level UI tests for rental state labels, expiry, and conservation action.
- [ ] Run the UI tests and verify they fail.
- [ ] Implement rental loading, formatting, conservation submission, and scoped display.
- [ ] Run the UI tests, frontend lint, and frontend build.
- [ ] Commit the interface slice.

### Task 5: Full verification and delivery

**Files:**
- Modify: none beyond the task slices
- Test: all existing tests

- [ ] Run the complete Python test suite.
- [ ] Run `npm run lint` and `npm run build` in `proto-ui`.
- [ ] Run `git diff --check` and inspect the final diff.
- [ ] Push `codex/temporary-rentals`, then fast-forward `main` and `agent/backstage-docker-deployment` only after verification.
