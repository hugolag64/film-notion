# Media Server Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Backstage add TMDB-linked films and series to Radarr/Sonarr, track their availability, import existing libraries, and open matching items in Jellyfin.

**Architecture:** Keep media metadata in the existing `media` table and store remote-service state in a new `media_availability` table. Isolate outbound HTTP behind typed Radarr, Sonarr, and Jellyfin clients; a service layer maps those responses into Backstage states. The FastAPI routes expose only safe status and option data to the React UI, while all URLs and secrets stay in server-side environment variables.

**Tech Stack:** Python 3.10+, FastAPI/NiceGUI, Pydantic v2, SQLite, httpx, pytest, React 19, Vite 8.

## Global Constraints

- Radarr, Sonarr, Jellyfin, and Backstage run on the same HP ProDesk; use `127.0.0.1` defaults for service URLs.
- Never persist or return `RADARR_API_KEY`, `SONARR_API_KEY`, `JELLYFIN_API_KEY`, or any configured internal URL through a browser endpoint.
- The MVP does not configure indexers, providers, download clients, tunnels, reverse proxies, or public *arr access.
- Backstage may be reached remotely only through a private access layer or authenticated reverse proxy outside this application.
- Poll remote services every 60 seconds by default; a failed poll must retain the last successful local state and must not change rating or watched state.
- Preserve all pre-existing user changes and make focused commits after each independently testable task.

---

## Planned File Structure

| File | Responsibility |
|---|---|
| `backend/config.py` | Optional media-server configuration and enablement predicates. |
| `backend/core/media_server.py` | Typed availability model, pure response-to-state mapping, and orchestration service. |
| `backend/core/arr.py` | Shared Arr HTTP wrapper plus Radarr and Sonarr API adapters. |
| `backend/core/jellyfin.py` | Jellyfin availability lookup and safe browser playback-link construction. |
| `backend/core/store.py` | `media_availability` schema and CRUD/upsert methods. |
| `backend/core/scheduler.py` | Optional recurring media-server synchronisation, independent from metadata enrichment. |
| `backend/api.py` | Request models and authenticated-server-side REST routes. |
| `main.py` | Start and stop media-server scheduling alongside existing lifecycle hooks. |
| `proto-ui/src/api.js` | Fetch helpers for media-server endpoints. |
| `proto-ui/src/BackstagePrototype.jsx` | Availability badges, add dialog, activity panel, and Jellyfin link; remove simulated player. |
| `tests/test_arr.py` | Contract tests for Radarr/Sonarr payloads and errors. |
| `tests/test_jellyfin.py` | Jellyfin matching and safe playback-link tests. |
| `tests/test_media_server.py` | Availability state mapping and synchronisation tests. |
| `tests/test_store.py` | SQLite availability persistence tests. |
| `tests/test_api.py` | Endpoint tests using fake service dependencies. |
| `.env.example` | Document only variable names and localhost sample URLs; never a real key. |
| `README.md` | Setup, local-only API boundary, and operational behaviour. |

## API Contract

`Availability` is the public, non-secret shape:

```python
class Availability(BaseModel):
    media_id: str
    provider: Literal["radarr", "sonarr"]
    arr_id: int | None = None
    jellyfin_id: str | None = None
    state: Literal["requested", "searching", "downloading", "imported", "available", "error"]
    progress_percent: int | None = None
    root_folder: str | None = None
    quality_profile_id: int | None = None
    language_profile_id: int | None = None
    last_error: str | None = None
    last_synced_at: datetime | None = None
```

Routes added to `/api`:

```text
GET  /media-server/status
GET  /media-server/options?media_type=Film|Série
GET  /medias/{media_id}/availability
POST /medias/{media_id}/acquisition
POST /media-server/sync
GET  /media-server/activity
```

`POST /medias/{media_id}/acquisition` consumes:

```json
{
  "quality_profile_id": 5,
  "language_profile_id": 1,
  "root_folder": "D:\\Media\\Films",
  "monitor": "all"
}
```

`monitor` is ignored for films and restricted to `all` or `future` for series. The options route returns profile IDs, labels and root folders, never headers, keys or configured base URLs.

### Task 1: Configuration and availability persistence

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/core/store.py`
- Modify: `tests/test_store.py`
- Create: `backend/core/media_server.py`

**Interfaces:**
- Produces `Config.media_server_enabled() -> bool`, `Config.radarr_enabled() -> bool`, `Config.sonarr_enabled() -> bool`, and `Config.jellyfin_enabled() -> bool`.
- Produces `Availability`, `AvailabilityState`, and `MediaStore.get_availability(media_id)`, `MediaStore.upsert_availability(availability)`, `MediaStore.list_availabilities()`.
- Consumes existing `MediaStore.init_schema()` and asynchronous `asyncio.to_thread` persistence style.

- [ ] **Step 1: Write persistence tests before changing the schema**

```python
from backend.core.media_server import Availability

def test_upsert_and_fetch_availability(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    saved = asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", arr_id=42,
        state="downloading", progress_percent=63,
    )))

    assert saved.arr_id == 42
    assert asyncio.run(store.get_availability(media.id)).state == "downloading"
```

- [ ] **Step 2: Run the new test and verify it fails because the availability interface does not exist**

Run: `pytest tests/test_store.py::test_upsert_and_fetch_availability -v`

Expected: FAIL with an import or attribute error for `Availability` or `upsert_availability`.

- [ ] **Step 3: Add optional configuration and the typed availability model**

```python
# backend/config.py
RADARR_URL = os.getenv("RADARR_URL", "http://127.0.0.1:7878")
RADARR_API_KEY = os.getenv("RADARR_API_KEY")
SONARR_URL = os.getenv("SONARR_URL", "http://127.0.0.1:8989")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")
JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY")
MEDIA_SYNC_INTERVAL_SEC = int(os.getenv("MEDIA_SYNC_INTERVAL_SEC", "60"))
```

Define `Availability` and its six literal states in `backend/core/media_server.py`. Add `media_availability` with a primary key on `media_id`, a unique index on `(provider, arr_id)` when `arr_id` is not null, ISO timestamps, and nullable technical fields. Follow the existing SQLite migration pattern and expose async wrappers around synchronous CRUD methods.

- [ ] **Step 4: Run persistence tests and the current store suite**

Run: `pytest tests/test_store.py -v`

Expected: PASS, including creation, retrieval, and replacement of the same media availability row.

- [ ] **Step 5: Commit the self-contained persistence layer**

```bash
git add backend/config.py backend/core/store.py backend/core/media_server.py tests/test_store.py
git commit -m "feat: persist media server availability"
```

### Task 2: Radarr and Sonarr API adapters

**Files:**
- Create: `backend/core/arr.py`
- Create: `tests/test_arr.py`
- Modify: `requirements-dev.txt` only if a test-only HTTP transport helper is absent; otherwise use `httpx.MockTransport`.

**Interfaces:**
- Consumes `Config` and shared `backend.core.http.get_client()`.
- Produces `RadarrClient.list_options()`, `RadarrClient.add_movie(tmdb_id, quality_profile_id, root_folder)`, `RadarrClient.list_library()`, `RadarrClient.list_queue()`.
- Produces `SonarrClient.list_options()`, `SonarrClient.add_series(tmdb_id, quality_profile_id, language_profile_id, root_folder, monitor)`, `SonarrClient.list_library()`, `SonarrClient.list_queue()`.
- Every public method returns parsed safe dictionaries or raises `MediaServerError(kind, message)` without including a URL, API key, or raw remote body.

- [ ] **Step 1: Write Radarr and Sonarr request-contract tests**

```python
async def test_radarr_add_movie_posts_tmdb_profile_and_root(mock_transport):
    client = RadarrClient("http://127.0.0.1:7878", "secret", http_client=mock_transport)
    await client.add_movie(tmdb_id=438631, quality_profile_id=5, root_folder="D:/Media/Films")

    assert mock_transport.last_request.url.path == "/api/v3/movie"
    assert mock_transport.last_json == {
        "tmdbId": 438631, "qualityProfileId": 5,
        "rootFolderPath": "D:/Media/Films", "monitored": True,
        "addOptions": {"searchForMovie": True},
    }

async def test_sonarr_rejects_unknown_monitor_value():
    client = SonarrClient("http://127.0.0.1:8989", "secret", http_client=mock_client())
    with pytest.raises(ValueError, match="monitor"):
        await client.add_series(1, 2, 3, "D:/Media/Series", "invalid")
```

- [ ] **Step 2: Run the adapter tests and verify they fail**

Run: `pytest tests/test_arr.py -v`

Expected: FAIL because `backend.core.arr` is not present.

- [ ] **Step 3: Implement the common Arr wrapper and both focused clients**

Use header `X-Api-Key` only inside `_request`. Query `/api/v3/qualityprofile`, `/api/v3/languageprofile` where supported, `/api/v3/rootfolder`, `/api/v3/movie` or `/api/v3/series`, and `/api/v3/queue`. For a remote 409 or an existing matching TMDB ID, return an explicit `DuplicateRemoteMedia` result so the service layer can link it rather than create it again. Limit request timeout to 10 seconds and convert connection, timeout, non-2xx, and malformed JSON failures to `MediaServerError`.

- [ ] **Step 4: Run adapter tests**

Run: `pytest tests/test_arr.py -v`

Expected: PASS for payloads, profile parsing, duplicate mapping, and non-secret error mapping.

- [ ] **Step 5: Commit the Arr adapters**

```bash
git add backend/core/arr.py tests/test_arr.py requirements-dev.txt
git commit -m "feat: add Radarr and Sonarr clients"
```

### Task 3: Jellyfin lookup and synchronisation service

**Files:**
- Create: `backend/core/jellyfin.py`
- Modify: `backend/core/media_server.py`
- Create: `tests/test_jellyfin.py`
- Create: `tests/test_media_server.py`

**Interfaces:**
- Consumes `RadarrClient`, `SonarrClient`, `JellyfinClient`, `MediaStore`, `Media`, and `Availability`.
- Produces `JellyfinClient.find_by_tmdb(tmdb_id, media_type) -> JellyfinMatch | None` and `JellyfinClient.playback_url(item_id) -> str`.
- Produces `MediaServerService.add(media, request) -> Availability`, `sync_media(media_id) -> Availability | None`, `sync_all() -> SyncSummary`, `activity() -> list[ActivityItem]`.

- [ ] **Step 1: Write state mapping and Jellyfin-link tests**

```python
def test_imported_arr_item_becomes_available_when_jellyfin_matches():
    service = MediaServerService(store, radarr=fake_radarr(imported=True), jellyfin=fake_jellyfin("abc"))
    availability = asyncio.run(service.sync_media("dune"))

    assert availability.state == "available"
    assert availability.jellyfin_id == "abc"

def test_playback_url_contains_only_public_jellyfin_item_path():
    client = JellyfinClient("https://jellyfin.example.test", "secret", http_client=mock_client())
    assert client.playback_url("abc") == "https://jellyfin.example.test/web/index.html#!/details?id=abc"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_jellyfin.py tests/test_media_server.py -v`

Expected: FAIL because the client and service do not exist.

- [ ] **Step 3: Implement Jellyfin matching and idempotent state synchronisation**

Query Jellyfin server-side with the API key header, match `ProviderIds.Tmdb` to the media TMDB ID and constrain item type to Movie or Series. Map remote data in this strict precedence: matching Jellyfin item → `available`; imported Arr item without Jellyfin → `imported`; queued item with a valid percentage → `downloading`; queued item without percentage → `searching`; successful add with no queue item → `requested`; remote failure → retain persisted state and set a safe `last_error`. Set support to `Serveur` only when the current support is empty or already `Serveur`; otherwise leave it unchanged.

- [ ] **Step 4: Run service and client tests**

Run: `pytest tests/test_jellyfin.py tests/test_media_server.py tests/test_store.py -v`

Expected: PASS, including idempotent upserts and preservation of local status fields on failures.

- [ ] **Step 5: Commit the synchronisation service**

```bash
git add backend/core/jellyfin.py backend/core/media_server.py tests/test_jellyfin.py tests/test_media_server.py
git commit -m "feat: sync media availability with Jellyfin"
```

### Task 4: FastAPI endpoints and recurring scheduling

**Files:**
- Modify: `backend/api.py`
- Modify: `backend/core/scheduler.py`
- Modify: `main.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes `MediaServerService`, `Availability`, and the existing `router`.
- Produces the six documented REST routes and `scheduler.start_media_server_sync()` / `scheduler.stop_media_server_sync()`.
- Endpoint dependency construction reads configuration only on the server; endpoint responses use `Availability`, safe options, and safe health fields.

- [ ] **Step 1: Add endpoint tests with fake services**

```python
def test_acquisition_returns_409_for_media_without_tmdb_id(client, fake_service):
    response = client.post("/api/medias/local-only/acquisition", json={
        "quality_profile_id": 5, "root_folder": "D:/Media/Films", "monitor": "all",
    })
    assert response.status_code == 409
    assert response.json()["detail"] == "Associez d'abord ce média à TMDB"

def test_status_never_contains_api_key(client):
    response = client.get("/api/media-server/status")
    assert response.status_code == 200
    assert "secret" not in response.text
```

- [ ] **Step 2: Run endpoint tests and verify they fail**

Run: `pytest tests/test_api.py -v`

Expected: FAIL because the routes and dependencies are missing.

- [ ] **Step 3: Implement routes and the independent scheduler loop**

Validate media type and TMDB linkage before calling the service. Map disabled configuration to HTTP 503 with `"Service non configuré"`, not an internal error. Let `POST /media-server/sync` launch one awaited synchronisation for the requesting user; return its safe summary. Start one additional `asyncio.Task` only when at least one Arr service is configured and `MEDIA_SYNC_INTERVAL_SEC > 0`; cancel and await it during shutdown without affecting the existing enrichment scheduler.

- [ ] **Step 4: Run API and scheduler tests**

Run: `pytest tests/test_api.py tests/test_scheduler.py -v`

Expected: PASS; confirm disabled configuration does not create a recurring task.

- [ ] **Step 5: Commit API and scheduling work**

```bash
git add backend/api.py backend/core/scheduler.py main.py tests/test_api.py tests/test_scheduler.py
git commit -m "feat: expose media server controls"
```

### Task 5: React client, media detail actions, and activity page

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/App.css` only for component-specific availability styles

**Interfaces:**
- Consumes `GET /media-server/options`, `GET /medias/{id}/availability`, `POST /medias/{id}/acquisition`, `POST /media-server/sync`, and `GET /media-server/activity`.
- Produces `fetchAvailability`, `fetchMediaServerOptions`, `requestAcquisition`, `syncMediaServer`, and `fetchMediaServerActivity` API helpers.
- Replaces the simulated `isPlaying` modal and synthetic `localStreamUrl` with an ordinary `window.open(playback_url, "_blank", "noopener,noreferrer")` action only when the backend provides a Jellyfin link.

- [ ] **Step 1: Add the API helper functions with strict response handling**

```javascript
export async function requestAcquisition(mediaId, payload) {
  const response = await fetch(`${API_BASE_URL}/medias/${mediaId}/acquisition`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error((await response.json()).detail || 'Demande impossible');
  return response.json();
}
```

Add equivalent helpers for availability, options, sync, and activity. Do not embed any server URL, profile ID, or API secret in source constants.

- [ ] **Step 2: Build the React project and record the baseline**

Run: `npm run build`

Working directory: `proto-ui`

Expected: PASS before UI edits; use the current working UI as the visual baseline.

- [ ] **Step 3: Implement the acquisition and availability UI**

In both film and series detail drawers, fetch availability on opening. Render a compact badge for all six states and a refresh control. Add an “Ajouter au serveur” modal that fetches service options on open, requires a quality profile and root folder, conditionally offers language/profile and `all`/`future` monitor choices for series, disables submission during the request, and displays the safe API error. Replace the fake HP ProDesk card and simulated player with a “Lire dans Jellyfin” button when `playback_url` exists.

Add a top-level “Activité” view or modal showing recent requests, queue items, errors, imports, and reported disk space. Its manual refresh calls `syncMediaServer()` and reloads the activity list. Keep the current movie and series drawers functional when the media-server feature is disabled.

- [ ] **Step 4: Build and lint the UI after the changes**

Run: `npm run build && npm run lint`

Working directory: `proto-ui`

Expected: PASS with no simulated stream modal or `hp-prodesk.local` reference remaining.

- [ ] **Step 5: Commit the UI integration**

```bash
git add proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx proto-ui/src/App.css
git commit -m "feat: add media server controls to library"
```

### Task 6: Initial library import, documentation, and full verification

**Files:**
- Modify: `backend/core/media_server.py`
- Modify: `backend/api.py`
- Modify: `tests/test_media_server.py`
- Create: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces `MediaServerService.import_existing_libraries() -> SyncSummary` and an idempotent import action available through the synchronisation endpoint.
- Consumes Arr library responses and existing local `media.tmdb_id` values.

- [ ] **Step 1: Write the idempotent import test**

```python
def test_import_links_existing_tmdb_media_without_creating_duplicate(tmp_path):
    store = _store(tmp_path)
    dune = asyncio.run(store.create({"title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=fake_radarr(library=[{"id": 42, "tmdbId": 438631}]))

    summary = asyncio.run(service.import_existing_libraries())

    assert summary.linked == 1
    assert asyncio.run(store.get_availability(dune.id)).arr_id == 42
    assert len(asyncio.run(store.fetch_all())) == 1
```

- [ ] **Step 2: Run the import test and verify it fails**

Run: `pytest tests/test_media_server.py::test_import_links_existing_tmdb_media_without_creating_duplicate -v`

Expected: FAIL because `import_existing_libraries` is not implemented.

- [ ] **Step 3: Implement import and write operational documentation**

For every known Radarr/Sonarr item, match a local record by `(type, tmdb_id)`. Link exactly one matching local record; if none exists, create a minimal TMDB-linked record only when the remote response contains a non-empty title and type. Never create a second row for an already-linked `(provider, arr_id)`. Document the environment variables, localhost-only API expectation, connection-test page, state meanings, manual sync, and that users configure lawful sources and download clients outside Backstage.

- [ ] **Step 4: Run full project verification**

Run: `pytest -v`

Expected: PASS.

Run: `npm run build && npm run lint`

Working directory: `proto-ui`

Expected: PASS.

- [ ] **Step 5: Commit documentation and import behaviour**

```bash
git add backend/core/media_server.py backend/api.py tests/test_media_server.py .env.example README.md
git commit -m "docs: document media server setup"
```

## Plan Self-Review

- **Spec coverage:** Tasks 1–4 cover local configuration, safe server-side calls, state persistence, synchronisation, error handling, and status/options/activity endpoints. Task 5 covers the film/series controls, availability badges, playback link, and activity UI. Task 6 covers initial existing-library import, setup documentation, and end-to-end verification.
- **Deliberately deferred:** Jellyfin playback-progress import, notifications, multi-location policies, automatic cleanup, public-access configuration, and indexer/provider/download-client configuration remain out of scope exactly as specified.
- **No-placeholder check:** The plan defines each new public interface, endpoint payload, tests, commands, expected outcomes, and commit scope. The only intentionally generic values are fake API credentials and test media IDs.
- **Type consistency:** `Availability`, six states, `MediaServerService`, route names, and `monitor` values are defined once in the API contract and reused unchanged by all tasks.
