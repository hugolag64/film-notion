# Jellyfin Playback Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize one Jellyfin user's playback state into Backstage and show resume, next-episode and recently-completed views.

**Architecture:** Persist a compact playback record in SQLite, expose Jellyfin user-data through the existing client and synchronize it through `MediaServerService`. FastAPI returns safe local summaries; React renders them without querying Jellyfin directly.

**Tech Stack:** Python 3.10+, SQLite, FastAPI, httpx, pytest, React 19, Vite 8.

## Global Constraints

- One Jellyfin account only.
- Match records by `jellyfin_id`, then by TMDB ID.
- Mark complete when Jellyfin says played or progress is at least 95%.
- Never overwrite rating, review, favorites or local watched episode state on a remote failure.

---

### Task 1: Playback persistence and Jellyfin user-data adapter

**Files:**
- Modify: `backend/core/store.py`, `backend/core/jellyfin.py`
- Create: `tests/test_playback.py`

**Interfaces:**
- Produces `PlaybackProgress(media_id, jellyfin_id, position_ticks, runtime_ticks, percent, played, last_played_at)`.
- Produces `MediaStore.upsert_playback(progress)`, `list_resume_progress()`, `list_recently_completed()` and `JellyfinClient.user_playback()`.

- [ ] **Step 1: Write a failing persistence test**

```python
def test_resume_progress_is_persisted(tmp_path):
    store = make_store(tmp_path)
    saved = asyncio.run(store.upsert_playback(PlaybackProgress(
        media_id="dune", jellyfin_id="j1", position_ticks=50, runtime_ticks=100,
        percent=50, played=False,
    )))
    assert asyncio.run(store.list_resume_progress())[0].media_id == "dune"
```

- [ ] **Step 2: Run it and verify failure**

Run: `py -3.13 -m pytest tests/test_playback.py::test_resume_progress_is_persisted -v`

Expected: FAIL because the model/table/method do not exist.

- [ ] **Step 3: Add table, model and Jellyfin user-data request**

Create `playback_progress` with `media_id` primary key and ISO timestamp. Request `/Users/{user_id}/Items` using `IsResumable=true` and `/Users/{user_id}/Items/Latest`; normalize `UserData.PlaybackPositionTicks`, `RunTimeTicks`, `Played` and `LastPlayedDate` into safe dictionaries.

- [ ] **Step 4: Run focused tests**

Run: `py -3.13 -m pytest tests/test_playback.py tests/test_jellyfin.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/store.py backend/core/jellyfin.py tests/test_playback.py tests/test_jellyfin.py
git commit -m "feat: persist Jellyfin playback progress"
```

### Task 2: Synchronization, completion and next episode

**Files:**
- Modify: `backend/core/media_server.py`, `backend/core/scheduler.py`, `backend/api.py`
- Modify: `tests/test_media_server.py`, `tests/test_series.py`

**Interfaces:**
- Produces `MediaServerService.sync_playback() -> PlaybackSummary` and `GET /api/playback/summary`.

- [ ] **Step 1: Write failing state tests**

```python
def test_progress_at_95_percent_is_completed(tmp_path):
    summary = asyncio.run(service_with_jellyfin_progress(95).sync_playback())
    assert summary.completed == 1

def test_next_episode_is_first_unwatched_in_season_order(tmp_path):
    assert asyncio.run(service.next_episode("series-id"))["episode_number"] == 3
```

- [ ] **Step 2: Run and verify failure**

Run: `py -3.13 -m pytest tests/test_media_server.py tests/test_series.py -q`

Expected: FAIL because playback sync and next-episode summary do not exist.

- [ ] **Step 3: Implement safe synchronization**

Map user playback to local media. Calculate percentage, apply the 95% rule, upsert local progress, and return resume/recent lists plus the first uncompleted non-special episode per active series. Add playback sync to the existing media-server periodic loop and a manual API route.

- [ ] **Step 4: Run backend tests**

Run: `py -3.13 -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/media_server.py backend/core/scheduler.py backend/api.py tests/test_media_server.py tests/test_series.py
git commit -m "feat: sync Jellyfin playback state"
```

### Task 3: React resume and episode views

**Files:**
- Modify: `proto-ui/src/api.js`, `proto-ui/src/BackstagePrototype.jsx`

**Interfaces:**
- Consumes `GET /api/playback/summary` and `POST /api/playback/sync`.
- Produces `Reprendre`, `Prochain épisode` and `Récemment terminé` sections using Jellyfin playback links.

- [ ] **Step 1: Add typed fetch helpers**

```javascript
export async function fetchPlaybackSummary() {
  const response = await fetch(`${API_BASE_URL}/playback/summary`);
  if (!response.ok) throw new Error('Progression indisponible');
  return response.json();
}
```

- [ ] **Step 2: Render local fallback and progression cards**

Add a compact homepage section for each summary list. Every resume card shows title, percentage and “Lire dans Jellyfin”; every next-episode card shows series, season and episode. When data is absent, render no empty dashboard block.

- [ ] **Step 3: Verify frontend**

Run from `proto-ui/`: `npm run build && npm run lint`

Expected: PASS with no warnings.

- [ ] **Step 4: Commit**

```bash
git add proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx
git commit -m "feat: show Jellyfin resume progress"
```

## Plan Self-Review

- Persistence, remote synchronization and UI are isolated into independently verifiable tasks.
- The plan preserves user-owned local fields and deliberately excludes notifications, multi-user support, watchlists and storage rules.
