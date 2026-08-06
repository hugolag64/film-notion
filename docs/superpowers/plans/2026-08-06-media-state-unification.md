# Media State Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify personal status, Watchlist, and server support so the film detail view and the general catalogue always display the same canonical state.

**Architecture:** Keep the media catalogue object as the shared UI projection, with `selectedMovie` updated from the same canonical mapped media after each mutation. Store Watchlist as a separate per-user boolean in `user_media_state`; keep `status` for watched/unwatched state. Return user-merged media from personal API mutations, and refresh the canonical media list after server synchronization.

**Tech Stack:** FastAPI, Pydantic, SQLite, React, Vite, pytest.

## Global Constraints

- Une note personnelle non vide implique le statut `Terminé`.
- `À regarder` désigne les films non vus.
- `Watchlist` est une sélection volontaire indépendante et personnalisée par utilisateur.
- Radarr/Jellyfin présent signifie support `Serveur` dans la fiche et la collection.
- Ne pas inclure les fichiers locaux non suivis `_backstage-backstage-1_logs.txt` et `stripe-x-a24.md`.

---

### Task 1: Add a durable per-user Watchlist flag

**Files:**
- Modify: `backend/core/models.py:6-35,72-82`
- Modify: `backend/core/store.py:168-185,307-313,414-449`
- Modify: `backend/api.py:90-98,229-291`
- Test: `tests/test_user_media_state.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `UserMediaState.is_watchlist: bool` is the persisted user-facing flag.
- `UpdatePersonalMediaRequest.is_watchlist: Optional[bool]` accepts Watchlist changes.
- `Media.is_watchlist: bool` is a response-only user projection; it is not stored in the shared `media` table.
- `_media_for_user` returns the user’s Watchlist state in `Media.is_watchlist` without changing shared catalogue tags.

- [x] **Step 1: Write failing persistence and API tests**

Add a test that upserts `{"is_watchlist": True}` and reads it back as `True`, then updates a rated film with `is_watchlist=True` and asserts the returned `Media` is `Terminé` and has `is_watchlist is False`. Add the explicit inverse case: setting `is_watchlist=False` leaves an unwatched film in `À regarder`.

- [x] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
py -m pytest tests/test_user_media_state.py tests/test_api.py -q
```

Expected: failures because the SQLite table, Pydantic model, request model, and store allow-list do not yet contain `is_watchlist`.

- [x] **Step 3: Add the schema-compatible model and store field**

Add `is_watchlist: bool = False` to the `Media` response model and `is_watchlist INTEGER NOT NULL DEFAULT 0` to the `CREATE TABLE IF NOT EXISTS user_media_state` definition. Add a guarded migration for existing databases:

```python
columns = {row[1] for row in conn.execute("PRAGMA table_info(user_media_state)")}
if "is_watchlist" not in columns:
    conn.execute(
        "ALTER TABLE user_media_state ADD COLUMN is_watchlist INTEGER NOT NULL DEFAULT 0"
    )
```

Include the field in `_row_to_user_media_state`, the store allow-list, boolean encoding, and upsert assignments. In `_media_for_user`, set `Media.is_watchlist` from the per-user state; for an admin without a personal state, return the default `False`.

- [x] **Step 4: Normalize personal API updates**

Add `is_watchlist` to `UpdatePersonalMediaRequest`. In `update_personal_media`, normalize aliases (`watched` → `Terminé`) and apply:

```python
if fields.get("rating") is not None and str(fields["rating"]).strip():
    fields["status"] = "Terminé"
    fields["is_watchlist"] = False
```

In `_media_for_user`, return `status="Terminé"` whenever the user has a non-empty rating, set `is_watchlist` from the state, and force it to `False` whenever a rating is saved.

- [x] **Step 5: Run the focused tests and verify they pass**

Run:

```powershell
py -m pytest tests/test_user_media_state.py tests/test_api.py -q
```

Expected: all focused tests pass.

- [x] **Step 6: Commit the persistence slice**

```powershell
git add backend/core/models.py backend/core/store.py backend/api.py tests/test_user_media_state.py tests/test_api.py
git commit -m "feat(media): separate personal watchlist state"
```

### Task 2: Make the frontend use one canonical media projection

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx:423-510,545-680,1023-1145,1435-1475`
- Modify: `proto-ui/src/library.js:1-25`
- Test: `tests/test_api.py` for canonical API response behavior; verify UI with build/lint.

**Interfaces:**
- Add a local `replaceMappedMedia(updatedRawMedia)` path that maps one API `Media` object using the same mapping rules as `loadRealMedias`.
- Personal mutations (`handleRate`, `handleStatusChange`, `handleNotesChange`, Watchlist toggle) update `movies` and `selectedMovie` from the API response, not optimistic partial copies.

- [x] **Step 1: Write a failing API test for the canonical response**

Extend the personal update test so a request containing `rating="4"` and `is_watchlist=True` returns `status == "Terminé"`, `rating == "4"`, and `is_watchlist == False` in the user-visible representation.

- [x] **Step 2: Run the focused test and verify it fails**

```powershell
py -m pytest tests/test_api.py::test_personal_rating_marks_media_as_watched -q
```

- [x] **Step 3: Refactor the UI mapping into a reusable canonical mapper**

Extract the existing `loadRealMedias` item mapping into a function that maps one raw `Media` object. Use it both for the initial list and mutation responses. Ensure the mapped object computes:

```javascript
status: numericRating > 0 ? 'Terminé' : normalizeStatus(media.status || 'À regarder'),
        isWatchlist: Boolean(media.is_watchlist),
```

Replace the local optimistic status/rating/support updates with a shared function that replaces the matching `movies` item and the selected item by `id`.

- [x] **Step 4: Make Watchlist and status controls independent**

Keep `À regarder` and `Terminé` as status controls. Change the Watchlist control to call `updatePersonalMedia(id, {is_watchlist: !selectedMovie.isWatchlist})`. Use `isWatchlist` for the Watchlist sidebar count/filter, and use `status !== 'Terminé'` for the `À regarder` filter/count.

- [x] **Step 5: Run build and lint**

```powershell
cd proto-ui
npm run build
npm run lint
cd ..
```

Expected: build succeeds and lint reports no errors.

### Task 3: Synchronize server support and administration navigation

**Files:**
- Modify: `backend/core/media_server.py:120-121`
- Modify: `proto-ui/src/BackstagePrototype.jsx:234-250,363-401,1000-1045,1120-1140,1856-1863`
- Modify: `proto-ui/src/components/AdminCenter.jsx` only if the existing activity section needs the moved refresh/import controls.
- Test: `tests/test_media_server.py`

**Interfaces:**
- `MediaServerService.sync_media` sets `support="Serveur"` whenever Radarr reports `hasFile` or Jellyfin returns an item.
- `openMediaActivity` is no longer rendered in the main catalogue; AdminCenter owns server activity.

- [x] **Step 1: Write the server canonical-state regression test**

Use an existing media with `support="Streaming"`, sync it against `FakeRadarr(hasFile=True)` and `FakeJellyfin`, then assert the stored media support is exactly `Serveur`.

- [x] **Step 2: Run the focused server test and verify it fails if the guard regresses**

```powershell
py -m pytest tests/test_media_server.py::test_imported_arr_item_becomes_available_when_jellyfin_matches -q
```

- [x] **Step 3: Refresh canonical media after server sync**

After `syncMediaServer`/`refreshMediaActivity`, call `loadRealMedias()` before updating activity badges. When a selected media availability is `imported` or `available`, refresh the same canonical media projection so both the card and detail view receive `support="Serveur"`.

- [x] **Step 4: Move the activity entry point into Administration**

Remove the main catalogue header button and the standalone activity modal from the library shell. Keep the activity section inside `AdminCenter`, including refresh and import actions. Do not remove the server activity API calls used by `AdminCenter`.

- [x] **Step 5: Add the sidebar actions and filters**

Remove the top-bar `Choisir un film` button. Add a visually prominent purple gradient CTA inside the sidebar below navigation that opens `RecommendationFlow`. Add two navigation entries:

- `À regarder`: filters `movie.status !== 'Terminé'` and counts all unwatched items.
- `Watchlist`: filters `movie.isWatchlist` and counts explicit user selections.

- [x] **Step 6: Run all verification commands**

```powershell
py -m pytest -q
cd proto-ui
npm run build
npm run lint
cd ..
git diff --check
```

Expected: 155 or more tests pass, UI build/lint succeed, and `git diff --check` is clean.

- [x] **Step 7: Commit the integrated UI and server slice**

```powershell
git add backend/core/media_server.py proto-ui/src/BackstagePrototype.jsx proto-ui/src/components/AdminCenter.jsx proto-ui/src/library.js tests/test_media_server.py
git commit -m "fix(ui): unify media detail and catalogue state"
```
