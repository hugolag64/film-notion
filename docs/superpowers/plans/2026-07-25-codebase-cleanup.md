# Backstage Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive retired NiceGUI/Notion functionality and leave a minimal React, FastAPI, SQLite, TMDB and media-server application.

**Architecture:** Move retired source, scripts, tests and historical design documents below `legacy/2026-07-cleanup/` without retaining imports from the active tree. Simplify runtime configuration, scheduling and dependencies before removing the fake stream surface. The active application retains only modules on the FastAPI/React execution path.

**Tech Stack:** Python 3.10+, FastAPI/NiceGUI host, SQLite, httpx, React 19, Vite 8, pytest.

## Global Constraints

- Never move `.env`, `backstage.db`, cache files, installed dependencies, or generated user data.
- Never commit a real API key.
- Keep `proto-ui/dist`: `main.py` serves it at runtime.
- Keep TMDB, SQLite, series/episode tracking and Sonarr/Radarr/Jellyfin integration.
- Every moved file must live under `legacy/2026-07-cleanup/` with a README stating it is inactive.

---

### Task 1: Remove the simulated streaming surface

**Files:**
- Modify: `backend/api.py`
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes the real `GET /medias/{id}/availability` payload and its `playback_url`.
- Produces no `/medias/{id}/stream`, `triggerStream`, `localStreamUrl`, `isPlaying`, or `hp-prodesk.local` reference.

- [ ] **Step 1: Write a regression test asserting the fake route is absent**

```python
def test_api_module_has_no_simulated_stream_route():
    import backend.api as api
    paths = {route.path for route in api.router.routes}
    assert "/api/medias/{media_id}/stream" not in paths
```

- [ ] **Step 2: Run the regression test and verify it fails**

Run: `py -3.13 -m pytest tests/test_api.py::test_api_module_has_no_simulated_stream_route -v`

Expected: FAIL because the legacy route is still registered.

- [ ] **Step 3: Delete only the fake-stream endpoint and React simulation**

Remove `trigger_stream` in `backend/api.py`, `triggerStream` in `proto-ui/src/api.js`, and the synthetic stream URL/state/modal in `BackstagePrototype.jsx`. Preserve the existing Jellyfin button that uses `mediaAvailability.playback_url`.

- [ ] **Step 4: Verify the focused test and text audit**

Run: `py -3.13 -m pytest tests/test_api.py -q`

Expected: PASS.

Run: `rg -n "triggerStream|localStreamUrl|isPlaying|hp-prodesk" backend proto-ui/src`

Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add backend/api.py proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx tests/test_api.py
git commit -m "refactor: remove simulated streaming"
```

### Task 2: Simplify active configuration and scheduling

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/core/scheduler.py`
- Modify: `main.py`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces only `TMDB_API_KEY`, SQLite, port, development and media-server configuration in `Config`.
- Produces `scheduler.start_media_server_sync()` as the only optional periodic task.

- [ ] **Step 1: Write a failing active-configuration test**

```python
from backend.config import Config

def test_active_config_exposes_media_server_and_not_notion_or_ai():
    assert hasattr(Config, "RADARR_URL")
    assert not hasattr(Config, "NOTION_TOKEN")
    assert not hasattr(Config, "ANTHROPIC_API_KEY")
    assert not hasattr(Config, "OMDB_API_KEY")
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `py -3.13 -m pytest tests/test_config.py::test_active_config_exposes_media_server_and_not_notion_or_ai -v`

Expected: FAIL because legacy configuration still exists.

- [ ] **Step 3: Remove legacy configuration and enrichment schedule**

Delete Notion, Anthropic, OMDb and `SYNC_INTERVAL_MIN` fields/methods; remove the enrichment processor imports and loop from `scheduler.py`; remove `anthropic` from requirements. Update `.env.example` and README to describe TMDB plus the three local media services only.

- [ ] **Step 4: Verify active configuration**

Run: `py -3.13 -m pytest tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/core/scheduler.py main.py requirements.txt .env.example README.md tests/test_config.py
git commit -m "refactor: keep only active runtime configuration"
```

### Task 3: Archive retired Python and NiceGUI code

**Files:**
- Create: `legacy/2026-07-cleanup/README.md`
- Move: `frontend/` to `legacy/2026-07-cleanup/nicegui/frontend/`
- Move: `backend/core/{notion,processor,cache_service,diff,history,ai,omdb}.py` to `legacy/2026-07-cleanup/notion-enrichment/backend/core/`
- Move: `scripts/` and `backend/scripts/` to `legacy/2026-07-cleanup/scripts/`
- Move: retired test files to `legacy/2026-07-cleanup/notion-enrichment/tests/`

**Interfaces:**
- Consumes the reduced active imports from Task 2.
- Produces an active `backend/core/` containing only `arr`, `http`, `jellyfin`, `mapping`, `media_server`, `models`, `scheduler`, `stats`, `store`, and `tmdb`.

- [ ] **Step 1: Create an archive manifest before moving files**

```markdown
# Retired code archive

This directory is not imported by Backstage and is excluded from active tests.
It preserves the former NiceGUI/Notion enrichment implementation for reference.
```

- [ ] **Step 2: Move files with Git-aware renames**

Run the explicit `git mv` commands from the Files list. Move tests that import archived modules (`test_cache.py`, `test_diff.py`, `test_processor_*.py`, `test_history.py`, and NiceGUI-only tests) with their source family.

- [ ] **Step 3: Verify no active import reaches the archive**

Run: `rg -n "frontend|notion|processor|cache_service|anthropic|omdb" main.py backend tests --glob '!legacy/**'`

Expected: no active import matches.

- [ ] **Step 4: Run the retained active test suite**

Run: `py -3.13 -m pytest -q`

Expected: PASS with only active tests collected.

- [ ] **Step 5: Commit**

```bash
git add -A frontend backend/core scripts backend/scripts tests legacy
git commit -m "refactor: archive retired NiceGUI and Notion code"
```

### Task 4: Archive historical documentation and validate the lean application

**Files:**
- Move: completed historical files in `docs/superpowers/plans/` and `docs/superpowers/specs/` to `legacy/2026-07-cleanup/docs/`
- Keep: `docs/superpowers/specs/2026-07-25-codebase-cleanup-design.md` and this plan until cleanup is complete.
- Move: `stripe-x-a24.md` to `legacy/2026-07-cleanup/notes/`

**Interfaces:**
- Produces a compact active `docs/` containing only current cleanup documentation and a root README.

- [ ] **Step 1: Move only superseded historical documents**

Keep this design and plan in place during execution. Move dated designs/plans for the completed UI, Notion, restart and media-server iterations into the archive after adding a short index in `legacy/2026-07-cleanup/docs/README.md`.

- [ ] **Step 2: Run complete verification**

Run: `py -3.13 -m pytest -q`

Expected: PASS.

Run from `proto-ui/`: `npm run build && npm run lint`

Expected: build succeeds; resolve the existing React key warning before declaring lint clean.

- [ ] **Step 3: Verify active-tree references and working tree**

Run: `rg -n "Notion|Anthropic|OMDB|triggerStream|hp-prodesk" --glob '!legacy/**' --glob '!docs/**' .`

Expected: no active matches.

Run: `git status --short`

Expected: no uncommitted files.

- [ ] **Step 4: Commit**

```bash
git add -A docs legacy stripe-x-a24.md proto-ui/src/BackstagePrototype.jsx
git commit -m "docs: archive historical project material"
```

## Plan Self-Review

- **Coverage:** the plan removes the fake stream, legacy configuration/dependency/scheduler path, archives retired source/tests/scripts/documents, and verifies the remaining React/FastAPI application.
- **Safety:** user data and secrets remain outside every move; only source and documentation are archived.
- **Consistency:** the only stream interface retained is `playback_url` from Jellyfin availability, and the only scheduler retained is the media-server sync task.
