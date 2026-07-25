# Backstage Jellyfin Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Open an available Jellyfin movie directly in a full-screen Backstage player using a browser-compatible HLS stream.

**Architecture:** The backend keeps the Jellyfin API key private, resolves the local media availability, and proxies Jellyfin's HLS manifest and media segments. The React UI opens a full-screen player overlay and uses `hls.js` for browsers without native HLS support. The existing acquisition/detail behavior remains unchanged when playback is unavailable.

**Tech Stack:** FastAPI, httpx, Jellyfin Web API/HLS, React 19, hls.js, Vite, pytest.

## Global Constraints

- The browser never receives the Jellyfin API key.
- Playback starts in Backstage without opening the Jellyfin details page.
- The player must support Interstellar's 4K HEVC HDR source through Jellyfin transcoding.
- Missing availability and playback failures show readable UI errors without sensitive details.
- Sonarr remains out of scope.

---

### Task 1: Define the backend HLS playback contract

**Files:**
- Modify: `backend/core/jellyfin.py`
- Modify: `backend/core/media_server.py`
- Test: `tests/test_jellyfin.py`
- Test: `tests/test_media_server.py`

**Interfaces:**
- `JellyfinClient.playback_manifest_url(item_id: str) -> str` returns an internal Jellyfin HLS manifest URL only for server-side use.
- `MediaServerService.playback_manifest(media_id: str) -> Optional[dict[str, str]]` returns `{"item_id": ..., "url": ...}` when a linked Jellyfin item exists, otherwise `None`.

- [ ] **Step 1: Write the failing tests**

Add a Jellyfin client test asserting that `playback_manifest_url("abc")` contains `/Videos/abc/master.m3u8`, requests H.264/AAC HLS transcoding, and does not put the API key in the returned URL. Add a media-server test asserting that an available media returns the Jellyfin item id and that an unavailable media returns `None`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -m pytest -q tests/test_jellyfin.py tests/test_media_server.py
```

Expected: FAIL because the new methods do not exist.

- [ ] **Step 3: Implement the minimal URL and service methods**

Build the URL with `urllib.parse.urlencode` and parameters equivalent to:

```python
{
    "VideoCodec": "h264",
    "AudioCodec": "aac",
    "Container": "ts",
    "TranscodingContainer": "ts",
    "TranscodingProtocol": "hls",
    "MaxWidth": "1920",
    "MaxHeight": "1080",
}
```

Keep authentication in the backend request headers rather than returning it to React. Use the stored `Availability.jellyfin_id` to connect the service method to the Jellyfin method.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same pytest command. Expected: all tests in both files pass.

- [ ] **Step 5: Commit the backend contract**

```powershell
git add backend/core/jellyfin.py backend/core/media_server.py tests/test_jellyfin.py tests/test_media_server.py
git commit -m "feat: define Jellyfin HLS playback contract"
```

### Task 2: Add a private HLS proxy route

**Files:**
- Modify: `backend/api.py`
- Modify: `backend/core/jellyfin.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `GET /api/medias/{media_id}/playback/manifest` returns a rewritten HLS manifest with relative resource URLs pointing back to Backstage.
- `GET /api/medias/{media_id}/playback/resource/{resource_path:path}` proxies a Jellyfin HLS playlist or segment after resolving the media's Jellyfin id.

- [ ] **Step 1: Write failing API tests**

Add tests that verify the route set contains both playback routes, that a missing Jellyfin availability returns HTTP 404, and that the manifest response never contains `api_key`, `X-Emby-Token`, or the Jellyfin origin.

- [ ] **Step 2: Run the API tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -m pytest -q tests/test_api.py
```

Expected: FAIL because the routes do not exist.

- [ ] **Step 3: Implement the proxy**

Use the existing `httpx` client and `JellyfinClient` authentication. Fetch the manifest server-side, rewrite each non-comment URI in the playlist to a URL-encoded Backstage resource path, and proxy segments/playlists with their upstream `Content-Type`, `Content-Length`, `Content-Range`, `Accept-Ranges`, and `Cache-Control` headers. Reject path traversal and media ids without a stored Jellyfin availability.

- [ ] **Step 4: Run the API tests and verify GREEN**

Run the same command and confirm all API tests pass.

- [ ] **Step 5: Commit the proxy**

```powershell
git add backend/api.py backend/core/jellyfin.py tests/test_api.py
git commit -m "feat: proxy Jellyfin HLS playback"
```

### Task 3: Add the full-screen React player

**Files:**
- Modify: `proto-ui/package.json`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/api.js`

**Interfaces:**
- `api.js` exports `getPlaybackManifest(mediaId)` returning the manifest endpoint URL.
- The detail view stores `playerMedia` as `{ id, title, manifestUrl } | null` and renders a full-screen player when non-null.

- [ ] **Step 1: Add the player dependency and UI behavior test seam**

Add `hls.js` to `proto-ui/package.json`. Keep the player logic in a small local component or helper so it can be mounted with a media id and title. The component must expose an `onClose` callback and render a native `<video controls autoPlay playsInline>` element.

- [ ] **Step 2: Run the frontend build before implementation changes**

Run:

```powershell
npm --prefix proto-ui run build
```

Expected: the dependency is installed/available and the existing UI still builds.

- [ ] **Step 3: Implement the player**

When the user clicks the green available-media button, set `playerMedia` instead of opening a new Jellyfin tab. Use native HLS when `video.canPlayType('application/vnd.apple.mpegurl')` succeeds; otherwise construct `new Hls()`, load the Backstage manifest URL, attach it to the video element, and destroy the instance on unmount. Show a spinner while the first frame loads, a clear error on `Hls.Events.ERROR` fatal errors, and a visible `Retour à Backstage` button.

- [ ] **Step 4: Build the frontend and verify GREEN**

Run:

```powershell
npm --prefix proto-ui run build
```

Expected: Vite exits with code 0.

- [ ] **Step 5: Commit the player UI**

```powershell
git add proto-ui/package.json proto-ui/package-lock.json proto-ui/src/BackstagePrototype.jsx proto-ui/src/api.js
git commit -m "feat: add full-screen Jellyfin player"
```

### Task 4: Wire, restart, and validate with Interstellar

**Files:**
- Modify: `restart_server.bat` only if the current build/start flow does not include the new frontend bundle.
- Test: `tests/test_jellyfin.py`, `tests/test_media_server.py`, `tests/test_api.py`

- [ ] **Step 1: Run the complete backend regression suite**

```powershell
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -m pytest -q
```

Expected: zero failures.

- [ ] **Step 2: Build the production frontend**

```powershell
npm --prefix proto-ui run build
```

Expected: exit code 0.

- [ ] **Step 3: Restart Backstage**

```powershell
cmd /c restart_server.bat
```

- [ ] **Step 4: Validate the real media contract**

Query Interstellar's availability using its local media id and confirm it is `available`. Request the manifest endpoint and confirm it returns HLS content without the Jellyfin API key. Open Backstage, click « Lire » on Interstellar, and verify the full-screen player begins playback without opening a Jellyfin tab.

- [ ] **Step 5: Commit the integrated result**

```powershell
git add backend proto-ui tests
git commit -m "feat: play Jellyfin media directly in Backstage"
```
