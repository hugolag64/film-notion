# Media Server Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize real Radarr/Sonarr libraries and queues into Backstage, expose complete activity and availability, and show it in the React library.

**Architecture:** Extend the Arr adapters with queue and disk data, then centralize state derivation and idempotent imports in `MediaServerService`. FastAPI returns one safe activity view; React consumes it for badges, queue activity and acquisition choices.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, httpx, pytest, React 19, Vite 8.

## Global Constraints

- Use TMDB ID plus media type as the cross-service identity.
- Preserve local notes, ratings, watched state and user-selected support on all sync paths.
- Never expose remote URLs or API keys to the browser.
- Keep Jellyfin playback links; Jellyfin progress and notifications remain out of scope.

---

### Task 1: Queue, disk and state normalization

**Files:**
- Modify: `backend/core/arr.py`, `backend/core/media_server.py`
- Modify: `tests/test_arr.py`, `tests/test_media_server.py`

**Interfaces:**
- Produces `ArrClient.disk_space() -> list[dict]` and `MediaServerService.sync_media(media_id) -> Availability` with states `requested`, `searching`, `downloading`, `imported`, `available`, `error`.

- [ ] **Step 1: Write failing state tests**

```python
def test_queue_progress_maps_to_downloading(tmp_path):
    service = service_with_queue({"movieId": 42, "sizeleft": 50, "size": 100})
    assert asyncio.run(service.sync_media("dune")).state == "downloading"

def test_queue_error_maps_to_error(tmp_path):
    service = service_with_queue({"movieId": 42, "errorMessage": "Import failed"})
    assert asyncio.run(service.sync_media("dune")).state == "error"
```

- [ ] **Step 2: Run failing tests**

Run: `py -3.13 -m pytest tests/test_media_server.py -v`

Expected: FAIL because queue data is ignored.

- [ ] **Step 3: Implement queue lookup and deterministic mapping**

Map matching queue error to `error`; a positive size and sizeleft to `downloading` with rounded percentage; any matching queue without both sizes to `searching`; then imported and Jellyfin states. Implement `disk_space()` with `/api/v3/diskspace` and safe failure conversion.

- [ ] **Step 4: Run focused tests**

Run: `py -3.13 -m pytest tests/test_arr.py tests/test_media_server.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/arr.py backend/core/media_server.py tests/test_arr.py tests/test_media_server.py
git commit -m "feat: sync media server queue states"
```

### Task 2: Idempotent remote-library import

**Files:**
- Modify: `backend/core/media_server.py`, `backend/api.py`
- Modify: `tests/test_media_server.py`, `tests/test_api.py`

**Interfaces:**
- Produces `MediaServerService.import_existing_libraries() -> ImportSummary` and `POST /api/media-server/import`.

- [ ] **Step 1: Write failing creation tests**

```python
def test_import_creates_missing_film_from_remote_tmdb_id(tmp_path):
    summary = asyncio.run(service_with_radarr_movie(438631).import_existing_libraries())
    created = asyncio.run(store.fetch_all())
    assert summary["created"] == 1
    assert created[0].tmdb_id == 438631
```

- [ ] **Step 2: Run the test and verify failure**

Run: `py -3.13 -m pytest tests/test_media_server.py::test_import_creates_missing_film_from_remote_tmdb_id -v`

Expected: FAIL because unknown remote items are skipped.

- [ ] **Step 3: Create minimal local media and enrich from TMDB**

For unknown remote items, create `title`, `type`, `tmdb_id`, `status="À regarder"` and availability. If a TMDB client is configured, replace minimal metadata and create series episodes; failures retain the minimal record. Avoid duplicates with existing availability and `(type, tmdb_id)`.

- [ ] **Step 4: Expose manual import and test idempotence**

Run: `py -3.13 -m pytest tests/test_media_server.py tests/test_api.py -q`

Expected: PASS; a second import reports zero creations.

- [ ] **Step 5: Commit**

```bash
git add backend/core/media_server.py backend/api.py tests/test_media_server.py tests/test_api.py
git commit -m "feat: import remote media libraries"
```

### Task 3: Complete activity and acquisition UI

**Files:**
- Modify: `backend/core/media_server.py`, `backend/api.py`
- Modify: `proto-ui/src/api.js`, `proto-ui/src/BackstagePrototype.jsx`
- Modify: `tests/test_media_server.py`

**Interfaces:**
- `GET /api/media-server/activity` returns `{items, disks}` where each item is a safe availability object.
- React displays states, percentage, last errors, imports and disk free space; acquisition exposes monitor `all` / `future` for series.

- [ ] **Step 1: Write failing activity-shape test**

```python
def test_activity_returns_availability_items_and_disks(tmp_path):
    activity = asyncio.run(service.activity())
    assert set(activity) == {"items", "disks"}
```

- [ ] **Step 2: Run test and verify failure**

Run: `py -3.13 -m pytest tests/test_media_server.py::test_activity_returns_availability_items_and_disks -v`

Expected: FAIL because activity currently returns only a list.

- [ ] **Step 3: Implement response and UI**

Add disks to the backend activity result. In React, render availability badges on cards and detail drawers, activity items with state/percentage/error, disks with free/total values, and a select for Sonarr monitor. Reload availability after sync/import.

- [ ] **Step 4: Verify backend and frontend**

Run: `py -3.13 -m pytest -q`

Expected: PASS.

Run from `proto-ui/`: `npm run build && npm run lint`

Expected: PASS with no lint warnings.

- [ ] **Step 5: Commit**

```bash
git add backend/core/media_server.py backend/api.py proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx tests/test_media_server.py
git commit -m "feat: show media server activity and badges"
```

## Plan Self-Review

- Queue state, remote import, activity data, UI monitor selection and badges each map to a separate task.
- Local user data is protected by the service-level update rules in every task.
- The plan deliberately excludes Jellyfin progress, notifications, smart watchlists and multiple locations.
