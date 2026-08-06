# Bibliothèque React Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire de React l'interface unique et permettre de trier, filtrer, changer les statuts et ajouter des films enrichis par TMDB.

**Architecture:** SQLite reçoit une date de création et l'API FastAPI centralise la création à partir de TMDB et les règles de statut. React adapte les médias de l'API dans des fonctions pures, puis compose recherche, filtres et tri avant le rendu de la grille. La modale d'ajout utilise la recherche TMDB existante et l'endpoint de création.

**Tech Stack:** Python 3, FastAPI, SQLite, Pydantic, React 19, Vite, pytest.

## Global Constraints

- React est l'unique interface utilisateur ; `frontend/` NiceGUI n'est plus importé ni servi.
- Les affiches ne montrent que les supports et le favori ; le statut est placé dans le pied de carte.
- `À regarder` vide la note et indique non vu ; `Terminé` indique vu et garde la note.
- Le tri par défaut est la date d'ajout décroissante ; titre, année et note sont aussi disponibles.
- Les filtres genre, réalisateur, statut et support se combinent avec la recherche textuelle.
- L'ajout sélectionne un résultat TMDB et crée un média local enrichi avec le statut `À regarder`.

---

### Task 1: Persister la date d'ajout et normaliser les statuts

**Files:**
- Modify: `backend/core/models.py`
- Modify: `backend/core/store.py`
- Modify: `backend/api.py`
- Modify: `tests/test_store.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Produces: `Media.created_at: datetime` et les valeurs API `À regarder` ou `Terminé`.
- Produces: `POST /api/medias/from_tmdb` avec corps `{"tmdb_id": 123}` et réponse `Media`.

- [ ] **Step 1: Write failing persistence and API tests**

```python
def test_create_sets_created_at(tmp_path):
    media = asyncio.run(_store(tmp_path).create({"title": "Dune"}))
    assert media.created_at is not None

def test_watching_later_clears_rating(client, stored_media):
    response = client.patch(f"/api/medias/{stored_media.id}", json={"status": "À regarder"})
    assert response.json()["rating"] is None
    assert response.json()["status"] == "À regarder"
```

- [ ] **Step 2: Run tests and observe the missing date/status behavior**

Run: `py -m pytest tests/test_store.py::test_create_sets_created_at tests/test_api.py::test_watching_later_clears_rating -v`

Expected: FAIL because `created_at` and the status rule do not exist.

- [ ] **Step 3: Implement the schema, migration and API rule**

Add `created_at` to `Media`, `_COLUMNS`, the table definition and a migration using an ISO UTC timestamp. In `update_media`, translate legacy `watched` to `Terminé`, legacy `watchlist` to `À regarder`, and when the normalized status is `À regarder`, set `rating` to `None`. Add `CreateFromTMDBRequest(tmdb_id: int)` and create the media from `TMDBClient.get_movie_details`, including title, poster, backdrop, cast, director, genres, release date, `tmdb_ok=True`, `status="À regarder"` and `rating=None`.

- [ ] **Step 4: Run focused tests**

Run: `py -m pytest tests/test_store.py tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add backend/core/models.py backend/core/store.py backend/api.py tests/test_store.py tests/test_api.py && git commit -m "feat: add TMDB movie creation and status rules"`

### Task 2: Isoler l'adaptation, le tri et les filtres React

**Files:**
- Create: `proto-ui/src/library.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Consumes: liste de médias API et `filters = {genre, director, status, support, query}`.
- Produces: `normalizeMovie(media)`, `filterAndSortMovies(movies, filters, sort)` et les options uniques de filtre.

- [ ] **Step 1: Write a failing source-level regression test**

```python
def test_react_library_uses_shared_sorting_and_filters():
    source = (PROJECT_ROOT / "proto-ui/src/BackstagePrototype.jsx").read_text(encoding="utf-8")
    helpers = (PROJECT_ROOT / "proto-ui/src/library.js").read_text(encoding="utf-8")
    assert "filterAndSortMovies" in source
    assert "export function filterAndSortMovies" in helpers
```

- [ ] **Step 2: Run test and observe the absent module**

Run: `py -m pytest tests/test_theme.py::test_react_library_uses_shared_sorting_and_filters -v`

Expected: FAIL because `library.js` is absent.

- [ ] **Step 3: Implement pure library helpers and controls**

Implement compatibility mapping (`watched` → `Terminé`, `watchlist` → `À regarder`), numeric note/year comparison, nulls last, and creation-date descending as default. Replace static sidebar genres with derived options. Add compact selects for sort, direction, genre, réalisateur, statut and support plus a reset button above the grid. Use `filterAndSortMovies` for the rendered cards.

- [ ] **Step 4: Run regression test, lint and build**

Run: `py -m pytest tests/test_theme.py::test_react_library_uses_shared_sorting_and_filters -v; Push-Location proto-ui; npm run lint; npm run build; Pop-Location`

Expected: test PASS and Vite build succeeds.

- [ ] **Step 5: Commit**

Run: `git add proto-ui/src/library.js proto-ui/src/BackstagePrototype.jsx tests/test_theme.py && git commit -m "feat: add React library sorting and filters"`

### Task 3: Rendre les statuts et badges cohérents sur les cartes

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Consumes: `handleStatusChange(id, "À regarder" | "Terminé")`.
- Produces: cartes sans badge de statut sur l'image et statut textuel sous les métadonnées.

- [ ] **Step 1: Write a failing card-layout regression test**

```python
def test_react_card_keeps_only_support_badges_over_poster():
    source = (PROJECT_ROOT / "proto-ui/src/BackstagePrototype.jsx").read_text(encoding="utf-8")
    assert "{/* Left: Film Status Badge */}" not in source
    assert "movie.status === 'Terminé' ? 'Vu' : 'À regarder'" in source
```

- [ ] **Step 2: Run the regression test**

Run: `py -m pytest tests/test_theme.py::test_react_card_keeps_only_support_badges_over_poster -v`

Expected: FAIL because the status badge is still over the poster.

- [ ] **Step 3: Implement the card and status transition changes**

Remove the left poster status badge. Preserve support pills and favorite action. Render `Vu` or `À regarder` in the card footer. Make `handleRate` persist `status: "Terminé"`; make `handleStatusChange` clear local rating and send `{status: "À regarder", rating: null}` for the unwatched choice, and send only `{status: "Terminé"}` for the watched choice.

- [ ] **Step 4: Verify card test and build**

Run: `py -m pytest tests/test_theme.py::test_react_card_keeps_only_support_badges_over_poster -v; Push-Location proto-ui; npm run build; Pop-Location`

Expected: PASS and successful build.

- [ ] **Step 5: Commit**

Run: `git add proto-ui/src/BackstagePrototype.jsx tests/test_theme.py && git commit -m "fix: align React movie statuses"`

### Task 4: Ajouter un film depuis TMDB et retirer NiceGUI

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `main.py`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Consumes: `createMediaFromTMDB(tmdbId)`.
- Produces: modale de recherche/résultats et rafraîchissement après création.

- [ ] **Step 1: Write a failing regression test for the React-only shell**

```python
def test_app_serves_react_without_nicegui_frontend_import():
    app_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "import frontend.ui" not in app_source
    assert "createMediaFromTMDB" in (PROJECT_ROOT / "proto-ui/src/api.js").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test and observe the missing API client**

Run: `py -m pytest tests/test_theme.py::test_app_serves_react_without_nicegui_frontend_import -v`

Expected: FAIL because `createMediaFromTMDB` is absent.

- [ ] **Step 3: Implement the TMDB creation modal and React-only serving**

Add `createMediaFromTMDB(tmdbId)` as `POST /api/medias/from_tmdb`. Wire the header button to a dialog with query, loading/error state, result rows and selection action. After successful creation, close the dialog, reload movies and select the created movie. Remove the NiceGUI fallback import while retaining FastAPI and static React serving; keep the unserved `frontend/` modules because existing tests still import their shared helpers.

- [ ] **Step 4: Run all checks**

Run: `py -m pytest -q; Push-Location proto-ui; npm run lint; npm run build; Pop-Location`

Expected: Python suite passes and Vite build succeeds.

- [ ] **Step 5: Commit**

Run: `git add main.py proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx tests/test_theme.py frontend && git commit -m "feat: add TMDB movie dialog and remove NiceGUI UI"`
