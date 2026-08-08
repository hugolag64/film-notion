# Synchronisation Jellyfin-Backstage et fiche série centrée Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchroniser automatiquement le catalogue Jellyfin avec Backstage, créer les fiches manquantes, corriger les états de disponibilité et rendre la fiche série visuellement identique à la fiche film.

**Architecture:** Jellyfin devient la source de vérité des médias présents et expose une bibliothèque paginée normalisée par TMDB ID. `MediaServerService` réconcilie cette bibliothèque avec SQLite, enrichit les nouveaux médias par TMDB, donne priorité à Jellyfin sur les états Arr et conserve Radarr/Sonarr pour les demandes et téléchargements. Le frontend réutilise `FilmDetailView` pour les séries, recharge le catalogue après les actions serveur et affiche une disponibilité commune aux deux types.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLite, pytest, React, Vite, JSX, Tailwind utility classes.

## Global Constraints

- Jellyfin est la source de vérité de la présence physique d’un média.
- Le rapprochement se fait par `ProviderIds.Tmdb` quand il est disponible.
- Une fiche Backstage absente est créée automatiquement puis enrichie par TMDB.
- Une présence Jellyfin force l’état de disponibilité à `available` et conserve le `jellyfin_id`.
- Radarr/Sonarr restent les sources des demandes, de la file de téléchargement et des erreurs d’acquisition.
- Le profil Radarr par défaut est `1080 FR - max 10go`.
- Les utilisateurs non-admin ne voient/utilisent que ce profil ; les admins conservent le choix des profils exposés par le service.
- La synchronisation périodique utilise `MEDIA_SYNC_INTERVAL_SEC`, avec 60 secondes par défaut.
- Une panne distante ne supprime ni fiche ni dernière disponibilité connue.
- Aucun fichier utilisateur existant hors des fichiers listés ci-dessous ne doit être modifié.

---

## File Map

- Modify `backend/core/jellyfin.py`: lecture paginée et normalisation de la bibliothèque Jellyfin.
- Modify `backend/core/media_server.py`: réconciliation Jellyfin/SQLite, priorité de disponibilité et options d’acquisition.
- Modify `backend/core/scheduler.py`: exécuter la synchronisation lorsque Jellyfin seul est configuré.
- Modify `backend/api.py`: synchronisation ciblée lors de la lecture d’une disponibilité et filtrage/validation du profil d’acquisition par rôle.
- Modify `proto-ui/src/api.js`: exposer les appels de synchronisation et gérer les réponses d’options enrichies.
- Modify `proto-ui/src/BackstagePrototype.jsx`: rafraîchir catalogue/disponibilités, présélectionner le profil par défaut et remplacer la fiche série latérale par une fiche centrée.
- Modify `proto-ui/src/components/FilmDetailView.jsx`: rendre le libellé accessible générique film/série si nécessaire, sans changer son comportement de fermeture.
- Modify `tests/test_jellyfin.py`: tests de lecture et normalisation Jellyfin.
- Modify `tests/test_media_server.py`: tests de création, liaison, disponibilité et profil par défaut.
- Modify `tests/test_auth_api.py`: tests des permissions de synchronisation ciblée et du profil non-admin.
- Modify `tests/test_catalogue_playback_ui.py`: contrats de rafraîchissement et d’utilisation de `FilmDetailView` par la série.
- Create `docs/superpowers/plans/2026-08-08-jellyfin-backstage-sync-and-series-view.md`: ce plan.

---

### Task 1: Lire et normaliser la bibliothèque Jellyfin

**Files:**
- Modify: `backend/core/jellyfin.py`
- Test: `tests/test_jellyfin.py`

**Interfaces:**
- Consumes: Jellyfin `/Items` API with `IncludeItemTypes=Movie,Series`, `Recursive=true`, `ProviderIds` and pagination fields.
- Produces: `JellyfinClient.list_library() -> list[dict[str, Any]]`, where each item contains `jellyfin_id`, `tmdb_id`, `title`, `media_type`, `year`, `overview`, `poster_tag`, and `backdrop_tag`.

**Test setup:** Add a local `_run_library_request(payloads)` helper in `tests/test_jellyfin.py`. It creates an `httpx.MockTransport` whose handler returns the successive payloads, opens an `httpx.AsyncClient`, constructs `JellyfinClient("http://127.0.0.1:8096", "secret", http_client)`, awaits `list_library()`, and closes the client. The helper also asserts that each request uses `IncludeItemTypes=Movie,Series`, `Recursive=true`, `Fields` containing `ProviderIds`, `Limit=1000`, and the expected `StartIndex`.

- [ ] **Step 1: Write the failing tests**

```python
def test_list_library_reads_movies_and_series_across_pages():
    items = asyncio.run(_run_library_request([
        {"Items": [{
            "Id": "movie-1", "Type": "Movie", "Name": "Dune", "ProductionYear": 2021,
            "Overview": "Sable.", "ProviderIds": {"Tmdb": "438631"},
            "ImageTags": {"Primary": "poster-1"}, "BackdropImageTags": {"Backdrop": "backdrop-1"},
        }]},
        {"Items": [{
            "Id": "series-1", "Type": "Series", "Name": "Game of Thrones", "ProductionYear": 2011,
            "Overview": "Westeros.", "ProviderIds": {"Tmdb": "1399"},
            "ImageTags": {"Primary": "poster-2"}, "BackdropImageTags": {"Backdrop": "backdrop-2"},
        }]},
    ]))

    assert items == [
        {
            "jellyfin_id": "movie-1", "tmdb_id": 438631, "title": "Dune",
            "media_type": "Film", "year": 2021, "overview": "Sable.",
            "poster_tag": "poster-1", "backdrop_tag": "backdrop-1",
        },
        {
            "jellyfin_id": "series-1", "tmdb_id": 1399, "title": "Game of Thrones",
            "media_type": "Série", "year": 2011, "overview": "Westeros.",
            "poster_tag": "poster-2", "backdrop_tag": "backdrop-2",
        },
    ]


def test_list_library_skips_items_without_tmdb_id():
    assert asyncio.run(_run_library_request([{"Items": [
        {"Id": "unknown", "Type": "Movie", "Name": "Sans TMDB", "ProviderIds": {}},
    ]}])) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_jellyfin.py -k "list_library" -v`

Expected: FAIL because `JellyfinClient.list_library` is not defined.

- [ ] **Step 3: Implement the minimal client method**

Add a paginated `/Items` request with `IncludeItemTypes=Movie,Series`, `Recursive=true`, `Fields=ProviderIds,Overview,ProductionYear,ImageTags,BackdropImageTags`, `Limit=1000`, and `StartIndex`. Stop when the returned page contains fewer than the limit. Normalize `Movie` to `Film` and `Series` to `Série`; parse numeric TMDB IDs only; skip invalid items; do not swallow HTTP errors other than the existing client error policy.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_jellyfin.py -k "list_library" -v`

Expected: PASS.

- [ ] **Step 5: Commit the isolated change**

```bash
git add backend/core/jellyfin.py tests/test_jellyfin.py
git commit -m "feat: expose normalized Jellyfin library"
```

### Task 2: Réconcilier Jellyfin, TMDB, Arr et SQLite

**Files:**
- Modify: `backend/core/media_server.py`
- Test: `tests/test_media_server.py`

**Interfaces:**
- Consumes: `JellyfinClient.list_library()`, `MediaStore.fetch_all()`, `TMDBClient.get_details()`, and existing Arr library/queue methods.
- Produces: `MediaServerService.import_existing_libraries() -> dict[str, int]` that imports both Arr and Jellyfin; `MediaServerService.sync_all() -> dict[str, int]`; updated `sync_media(media_id: str) -> Optional[Availability]`.

**Test setup:** Add local test doubles in `tests/test_media_server.py`: `FakeJellyfinLibrary(items)` with `list_library()` and `find_by_tmdb()` methods, `FakeRadarrWithoutJellyfinMatch` with an empty `list_library()` and `list_queue()`, `FailingArr` and `FailingJellyfin` that raise `httpx.HTTPError`, and a `FakeTMDB` monkeypatch only in the creation test when metadata enrichment must be asserted. These doubles return the exact normalized item dictionaries used by the tests below.

- [ ] **Step 1: Write the failing tests**

```python
def test_import_creates_missing_series_from_jellyfin(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    jellyfin = FakeJellyfinLibrary([{
        "jellyfin_id": "series-1", "tmdb_id": 1399, "title": "Game of Thrones",
        "media_type": "Série", "year": 2011, "overview": "Westeros.",
        "poster_tag": None, "backdrop_tag": None,
    }])
    service = MediaServerService(store, jellyfin=jellyfin)

    summary = asyncio.run(service.import_existing_libraries())

    media = asyncio.run(store.fetch_all())[0]
    availability = asyncio.run(store.get_availability(media.id))
    assert summary["created"] == 1
    assert media.type == "Série"
    assert media.tmdb_id == 1399
    assert availability.state == "available"
    assert availability.jellyfin_id == "series-1"


def test_jellyfin_presence_overrides_stale_arr_state(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({
        "id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631,
    }))
    asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", arr_id=42, state="imported",
    )))
    service = MediaServerService(store, radarr=FakeRadarrWithoutJellyfinMatch(), jellyfin=FakeJellyfinLibrary([{
        "jellyfin_id": "jelly-dune", "tmdb_id": 438631, "title": "Dune",
        "media_type": "Film", "year": 2021, "overview": "Sable.",
        "poster_tag": None, "backdrop_tag": None,
    }]))

    result = asyncio.run(service.sync_media(media.id))

    assert result.state == "available"
    assert result.jellyfin_id == "jelly-dune"


def test_sync_media_keeps_existing_state_when_jellyfin_is_unavailable(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    existing = Availability(media_id="dune", provider="radarr", state="downloading", progress_percent=42)
    asyncio.run(store.upsert_availability(existing))
    service = MediaServerService(store, radarr=FailingArr(), jellyfin=FailingJellyfin())

    result = asyncio.run(service.sync_media("dune"))

    assert result.state == "downloading"
    assert result.progress_percent == 42
    assert result.last_error == "Synchronisation indisponible"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_media_server.py -k "jellyfin or stale_arr or existing_state" -v`

Expected: FAIL because the service does not list Jellyfin content and `sync_media` currently exits when Arr has no matching item.

- [ ] **Step 3: Implement the reconciliation**

Add a helper that indexes `list_library()` by `(media_type, tmdb_id)`. Make `import_existing_libraries` process Jellyfin items before/alongside Arr items. For a missing local item, create it with the Jellyfin title/type/TMDB ID and enrich missing fields from TMDB using the existing poster/backdrop/genre/cast helpers; never overwrite non-empty local fields. Upsert `Availability(state="available", jellyfin_id=...)` for each Jellyfin match and call `mark_rentals_available` with the current timestamp.

Update `sync_media` to fetch the targeted Jellyfin item first. If found, use it as the authoritative availability result even when Arr is missing or stale. If not found, retain the existing Arr queue/library mapping. Keep the current error behavior that upserts the previous availability with `last_error` instead of deleting it. Ensure `sync_all` counts Jellyfin-only creations and still visits all local TMDB-linked media.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_media_server.py -k "jellyfin or stale_arr or existing_state" -v`

Expected: PASS, including the existing media-server suite cases for Arr-only imports and playback.

- [ ] **Step 5: Commit the isolated change**

```bash
git add backend/core/media_server.py tests/test_media_server.py
git commit -m "feat: reconcile Backstage catalog with Jellyfin"
```

### Task 3: Corriger les déclencheurs backend et le profil d’acquisition

**Files:**
- Modify: `backend/core/scheduler.py`
- Modify: `backend/api.py`
- Modify: `backend/config.py` only if a named default constant is needed
- Test: `tests/test_auth_api.py`
- Test: `tests/test_media_server.py`

**Interfaces:**
- Consumes: `MediaServerService.sync_all`, `MediaServerService.acquisition_defaults`, current auth role from `AuthContext`.
- Produces: availability reads that refresh the targeted media; admin-only full sync/import routes; acquisition options with a default profile; server-side non-admin enforcement of `1080 FR - max 10go`.

**Test setup:** Add `should_sync_media_servers() -> bool` as the named scheduler predicate. In `tests/test_auth_api.py`, reuse the existing `_client(tmp_path, monkeypatch)` and `_setup(client)` helpers; create a regular user through `/api/auth/users`, log in as that user, and override `get_media_server_service` with a small `RecordingService` whose `sync_media(media_id)` appends to `synced_media_ids`, whose `store` points to the test `MediaStore`, and whose `add()` records the submitted profile. Define all test doubles locally in the test module rather than relying on undeclared pytest fixtures.

- [ ] **Step 1: Write the failing tests**

```python
def test_scheduler_syncs_when_only_jellyfin_is_configured(monkeypatch):
    monkeypatch.setattr(Config, "media_server_enabled", classmethod(lambda cls: False))
    monkeypatch.setattr(Config, "jellyfin_enabled", classmethod(lambda cls: True))
    assert should_sync_media_servers() is True


def test_non_admin_acquisition_rejects_a_non_default_quality_profile(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user = client.post("/api/auth/users", json={
        "username": "paul", "display_name": "Paul", "email": "paul@example.com",
        "password": "password123", "role": "user",
    }).json()
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "paul@example.com", "password": "password123"})
    response = client.post(
        "/api/medias/dune/acquisition",
        json={"quality_profile_id": 4, "root_folder": "/media/movies"},
    )
    assert response.status_code == 422
    assert "1080 FR - max 10go" in response.json()["detail"]


def test_availability_read_refreshes_the_targeted_media(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    recording_service = RecordingService(MediaStore(Config.DB_PATH))
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: recording_service
    response = client.get("/api/medias/dune/availability")
    assert response.status_code == 200
    assert recording_service.synced_media_ids == ["dune"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_auth_api.py -k "quality_profile or availability_read" -v` and `pytest tests/test_media_server.py -k "scheduler" -v`

Expected: FAIL because the scheduler gates sync on Arr/Seerr, acquisition trusts the browser payload, and the availability route only reads SQLite.

- [ ] **Step 3: Implement the backend behavior**

Extract a small `should_sync_media_servers()` predicate in `backend/core/scheduler.py` or use the equivalent direct condition so the loop invokes `sync_all()` when any of Radarr, Sonarr, Seerr, or Jellyfin is configured. Keep `MEDIA_SYNC_INTERVAL_SEC` as the only periodic interval.

In `/medias/{media_id}/availability`, call `await service.sync_media(media_id)` before reading the availability, then return the refreshed record and playback URL. Preserve access checks before synchronization.

Make the options route role-aware. Return the existing service options plus `default_quality_profile_id` and `default_quality_profile_name`. For non-admin callers, return only the profile named `1080 FR - max 10go` and reject acquisition payloads that specify another quality profile or replace the value with the configured default after validating the requested media. Keep admin selection unchanged and preserve the existing Seerr fallback.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_auth_api.py tests/test_media_server.py -k "quality_profile or availability_read or scheduler" -v`

Expected: PASS, with all existing authentication and acquisition tests still green.

- [ ] **Step 5: Commit the isolated change**

```bash
git add backend/core/scheduler.py backend/api.py backend/config.py tests/test_auth_api.py tests/test_media_server.py
git commit -m "fix: refresh Jellyfin availability and enforce defaults"
```

### Task 4: Brancher le rafraîchissement frontend sur la nouvelle synchro

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Test: `tests/test_catalogue_playback_ui.py`

**Interfaces:**
- Consumes: `fetchMedias`, `fetchAvailability`, enriched media-server options, and existing acquisition callbacks.
- Produces: `syncMediaServer()` and `syncMediaForMedia(mediaId)` API helpers; periodic refresh lifecycle; immediate catalog/availability refresh after acquisition; acquisition form filtered/preset by role.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_catalogue_refreshes_after_server_action():
    source = UI_SOURCE.read_text(encoding="utf-8")
    assert "syncMediaServer" in source
    assert "await loadRealMedias()" in source


def test_acquisition_defaults_are_used_and_non_admin_options_are_filtered():
    source = UI_SOURCE.read_text(encoding="utf-8")
    assert "default_quality_profile_id" in source
    assert "user?.role === 'admin'" in source


def test_availability_is_refreshed_periodically_with_cleanup():
    source = UI_SOURCE.read_text(encoding="utf-8")
    assert "setInterval" in source
    assert "clearInterval" in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_catalogue_playback_ui.py -k "refreshes_after_server_action or acquisition_defaults or periodically" -v`

Expected: FAIL because the frontend has no sync helper, no periodic catalogue refresh, and does not use an explicit default profile.

- [ ] **Step 3: Implement the frontend refresh flow**

Add `syncMediaServer()` for `POST /media-server/sync` and `syncMediaForMedia(mediaId)` only if the API exposes the targeted route; otherwise rely on the availability GET refresh introduced in Task 3. In `BackstagePrototype`, create one cancellable `refreshLibraryState` callback that fetches media, availability/activity where permitted, and dashboard data as needed. Register a 60-second interval only while the authenticated app is mounted; clear it on cleanup. Call it after acquisition, on window focus, and when switching to the library.

When opening acquisition, select `default_quality_profile_id` if present, falling back to the first option only for admin users and legacy responses. Render only the server-returned quality profiles, so non-admin callers cannot select another profile. After submit, close the modal, refresh the selected media availability, reload the catalogue, and refresh the activity badge without losing the open detail.

- [ ] **Step 4: Run the tests/build to verify they pass**

Run: `pytest tests/test_catalogue_playback_ui.py -k "refreshes_after_server_action or acquisition_defaults or periodically" -v`

Run: `npm run build` in `proto-ui`

Expected: PASS and a successful Vite production build.

- [ ] **Step 5: Commit the isolated change**

```bash
git add proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx tests/test_catalogue_playback_ui.py
git commit -m "feat: refresh catalogue availability from the UI"
```

### Task 5: Rendre la fiche série centrée et commune à la fiche film

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/components/FilmDetailView.jsx` only if the accessible label needs to accept a generic media type
- Test: `tests/test_catalogue_playback_ui.py`

**Interfaces:**
- Consumes: existing `selectedSeries`, `seriesEpisodes`, `seriesProgress`, `mediaAvailability`, `mediaAction`, episode handlers, and `FilmDetailView`.
- Produces: a centered series detail overlay with the same shell, server action area, notes area, and footer behavior as the film detail; existing episode tab behavior remains available.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_series_detail_uses_the_centered_film_detail_shell():
    source = UI_SOURCE.read_text(encoding="utf-8")
    series = source[source.index("{selectedSeries && ("):source.index("{/* TMDB Search & Relink Modal */}")]
    assert "<FilmDetailView" in series
    assert "FICHE SÉRIE" in series
    assert "Statut & support de stockage" in series
    assert "selectedSeries" in series


def test_series_detail_keeps_details_and_episodes_tabs():
    source = UI_SOURCE.read_text(encoding="utf-8")
    series = source[source.index("{selectedSeries && ("):source.index("{/* TMDB Search & Relink Modal */}")]
    assert "Détails" in series
    assert "Épisodes" in series
    assert "groupEpisodesBySeason" in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_catalogue_playback_ui.py -k "series_detail" -v`

Expected: FAIL because the current series branch renders a right-side drawer and does not use `FilmDetailView`.

- [ ] **Step 3: Implement the centered series view**

Replace only the `selectedSeries` right-side drawer branch with the same outer `<FilmDetailView media={selectedSeries} isDarkMode={isDarkMode} onClose={closeSeries}>` used by the film experience. Keep the existing episode data loading and handlers. Rebuild the inner markup with the film shell order: hero, status/support controls, availability/action card, rating/notes, then the centered `details`/`episodes` tab content and footer. Use `selectedSeries` for all series-specific fields and `selectedMedia`/`mediaAvailability` for shared server actions. Ensure every nested button stops propagation where needed so the overlay only closes when clicking outside the card.

Use responsive classes matching the film shell (`w-full`, `max-w-5xl`, bounded viewport height, rounded card, scrollable content). Remove the old `fixed ... justify-end`, `max-w-xl`, and `border-l` layout classes so the series cannot render as a side drawer.

- [ ] **Step 4: Run the tests/build to verify they pass**

Run: `pytest tests/test_catalogue_playback_ui.py -k "series_detail" -v`

Run: `npm run build` in `proto-ui`

Expected: PASS and a successful Vite production build.

- [ ] **Step 5: Commit the isolated change**

```bash
git add proto-ui/src/BackstagePrototype.jsx proto-ui/src/components/FilmDetailView.jsx tests/test_catalogue_playback_ui.py
git commit -m "feat: center series details like films"
```

### Task 6: Vérification intégrée et régression

**Files:**
- Modify: `tests/test_media_server.py` only if a regression discovered by the full suite needs a focused assertion.
- Modify: `tests/test_catalogue_playback_ui.py` only if a contract assertion needs to reflect the final shared shell.

**Interfaces:**
- Consumes: all interfaces produced by Tasks 1–5.
- Produces: verified backend/frontend behavior with no regression in existing Arr, Jellyfin playback, series episode, authentication, and dashboard tests.

- [ ] **Step 1: Run the focused backend suite**

Run: `pytest tests/test_jellyfin.py tests/test_media_server.py tests/test_auth_api.py tests/test_series.py -v`

Expected: PASS with no unexpected warnings or collection errors.

- [ ] **Step 2: Run the complete Python suite**

Run: `pytest -q`

Expected: PASS. If a pre-existing unrelated test fails, record its exact failure separately and do not alter unrelated files.

- [ ] **Step 3: Build the frontend**

Run: `npm run build` in `proto-ui`

Expected: Vite completes successfully.

- [ ] **Step 4: Inspect the final diff and status**

Run: `git diff HEAD~5 --stat; git status --short`

Expected: only the planned backend/frontend/tests/docs files are changed by this work; the user’s pre-existing dirty files remain untouched.

- [ ] **Step 5: Commit any final focused regression fix**

```bash
git add backend proto-ui/src tests
git commit -m "test: verify Jellyfin synchronization and unified media views"
```

Only create this final commit if Task 6 required a focused regression correction; otherwise leave the task commits intact.
