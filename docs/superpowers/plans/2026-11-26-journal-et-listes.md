# Journal « Vu » et listes partagées — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un journal « Vu » privé et des listes de films partagées entre colocs, tous deux hors bibliothèque, identifiés par `tmdb_id`.

**Architecture:** Nouvelles tables SQLite dans `MediaStore` (cache TMDB, entrées de journal, listes, films de liste) ; un nouveau routeur FastAPI `backend/journal_api.py` monté sous `/api` ; synchronisation ciblée avec `user_media_state` et les recommandations dans `backend/api.py`. Côté UI : un module de logique testable `journal.js`, deux vues (`JournalView`, `ListsView`) et une fenêtre `SeenDialog`, branchées dans `BackstagePrototype.jsx`.

**Tech Stack:** FastAPI, SQLite (`sqlite3` + `asyncio.to_thread`), pytest ; React 19, Vite, Tailwind, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-26-journal-et-listes-design.md`

## Global Constraints

- Rien n'est jamais inséré dans la table `media` par le journal ou les listes. La seule création de fiche reste la demande Seerr existante (`POST /api/seerr/requests`), déclenchée explicitement par l'utilisateur.
- Journal privé : toute route du journal ne lit/écrit que les entrées de l'utilisateur connecté, admin compris. Une entrée d'un autre → 404 (pas 403).
- Films uniquement (pas de séries).
- Note : `null` ou un multiple de 0,5 entre 0,5 et 5.
- Libellés exacts : « Journal », « Listes », « Vu au cinéma », « Date inconnue », « Demander aussi sur le serveur ? », « Sort le JJ/MM », « Au cinéma », « Demandé », « Sur le serveur », « ✓ Vu ».
- Python : `.venv/Scripts/python.exe -m pytest` (le `python` du PATH n'a pas pytest).
- Fins de ligne : `backend/api.py`, `proto-ui/src/api.js`, `proto-ui/src/library.js` sont en CRLF ; `BackstagePrototype.jsx`, `rentals.js` en LF. Ne pas réécrire un fichier entier avec une autre fin de ligne (éditions Python : `newline=''`). Nouveaux fichiers : LF.
- Aucune nouvelle dépendance.
- Ne jamais lancer la config `backstage` de `.claude/launch.json` (vrai serveur, vraie base). Vérification manuelle uniquement sur une copie de la base, port 8091, intégrations pointées vers `127.0.0.1:9`.
- Tests préexistants en échec sur `main` (11 : `test_auth_api` ×8, `test_auth_store` ×2, `test_catalogue_playback_ui` ×1) : ne pas les compter comme régressions, ne pas les corriger ici.

## Review Focus

1. Un coloc qui appelle `GET/PATCH/DELETE /api/journal/{id}` sur l'entrée d'un autre doit recevoir 404 et ne rien modifier → test en Task 2.
2. Un film ajouté au journal ou à une liste sans être sur le serveur ne doit créer aucune ligne `media` (sinon il réapparaît dans la grille) → tests en Tasks 2 et 4.
3. Changer plusieurs fois la note d'un film de la bibliothèque ne doit pas créer une entrée de journal à chaque fois → test en Task 3.
4. TMDB injoignable à l'ajout : erreur claire (502), rien de créé ; un film déjà en cache s'ajoute sans appeler TMDB → tests en Task 2.
5. Ajouter deux fois le même film à une liste (deux colocs en même temps) → un seul film, pas d'erreur 500 → test en Task 4.

## File Structure

- `backend/core/models.py` — modèles `DiaryEntry`, `FilmList`, `FilmListItem`.
- `backend/core/store.py` — tables et méthodes de stockage.
- `backend/journal_api.py` (nouveau) — routes `/api/journal` et `/api/lists`, cache TMDB, synchro bibliothèque.
- `backend/api.py` — `_media_for_user` (vu via journal), `PATCH /medias/{id}/personal` (écrit le journal), recommandations (journal = déjà vu ; « déjà vu » → journal), helper `_library_states`.
- `main.py` — monte `journal_router`.
- `backend/scripts/backfill_journal.py` (nouveau) — reprise de l'existant.
- `proto-ui/src/journal.js` + `journal.test.js` (nouveaux) — logique pure.
- `proto-ui/src/api.js` — fonctions d'appel.
- `proto-ui/src/components/SeenDialog.jsx`, `JournalView.jsx`, `ListsView.jsx` (nouveaux).
- `proto-ui/src/BackstagePrototype.jsx` — navigation, bouton « Vu » bibliothèque.

---

### Task 1: Stockage du journal, du cache TMDB et des listes

**Files:**
- Modify: `backend/core/models.py`, `backend/core/store.py` (`init_schema`, nouvelles méthodes en fin de classe)
- Test: `tests/test_journal_store.py`

**Interfaces:**
- Produces (models):
  - `DiaryEntry(id: str, backstage_user_id: str, tmdb_id: int, watched_on: date | None, rating: float | None, review: str | None, in_cinema: bool = False, source: str = "manual", created_at: datetime, updated_at: datetime)` — `source` ∈ `manual | library | recommendation | backfill`.
  - `FilmList(id: str, name: str, created_by: str, created_at: datetime)`
  - `FilmListItem(list_id: str, tmdb_id: int, added_by: str, added_at: datetime)`
- Produces (tables): `tmdb_movie_cache(tmdb_id INTEGER PRIMARY KEY, title TEXT NOT NULL, year INTEGER, release_date TEXT, poster_url TEXT, genres TEXT NOT NULL DEFAULT '[]', fetched_at TEXT NOT NULL)` ; `diary_entries` (colonnes du modèle, index `(backstage_user_id, tmdb_id)`) ; `film_lists` ; `film_list_items(list_id, tmdb_id, added_by, added_at, PRIMARY KEY(list_id, tmdb_id), FOREIGN KEY(list_id) REFERENCES film_lists(id) ON DELETE CASCADE)`.
- Produces (async `MediaStore` methods, each with a `_..._sync` twin, same pattern as rentals):
  - `upsert_tmdb_movie(movie: dict) -> dict` (clés : `tmdb_id, title, year, release_date, poster_url, genres: list[str]`) ; `get_tmdb_movies(tmdb_ids: list[int]) -> dict[int, dict]`
  - `create_diary_entry(entry: DiaryEntry) -> DiaryEntry` ; `get_diary_entry(entry_id: str) -> DiaryEntry | None` ; `list_diary_entries(user_id: str) -> list[DiaryEntry]` ; `update_diary_entry(entry_id: str, fields: dict) -> DiaryEntry | None` (met à jour `updated_at`) ; `delete_diary_entry(entry_id: str) -> bool` ; `latest_diary_entry(user_id: str, tmdb_id: int) -> DiaryEntry | None` ; `list_diary_tmdb_ids(user_id: str) -> set[int]`
  - `create_film_list(name: str, created_by: str) -> FilmList` ; `list_film_lists() -> list[dict]` (champs du modèle + `item_count`) ; `get_film_list(list_id) -> FilmList | None` ; `rename_film_list(list_id, name) -> FilmList | None` ; `delete_film_list(list_id) -> bool` ; `add_film_list_item(list_id, tmdb_id, added_by) -> bool` (False si déjà présent, via `INSERT OR IGNORE`) ; `remove_film_list_item(list_id, tmdb_id) -> bool` ; `list_film_list_items(list_id) -> list[FilmListItem]` (plus récents d'abord)
- Ordre « plus récent » du journal partout : `watched_on` décroissant, `NULL` en dernier, puis `created_at` décroissant. Ouvrir les connexions avec `PRAGMA foreign_keys = ON` pour la cascade (ou supprimer les items explicitement dans `delete_film_list`).

- [ ] **Step 1: Write the failing tests** in `tests/test_journal_store.py` (helper `make_store(tmp_path)` comme `tests/test_user_media_state.py`):
  - `test_diary_entries_are_per_user_and_ordered` : hugo a 3 entrées (2026-11-22, 2026-11-14, `None`), paul 1 → `list_diary_entries("hugo")` renvoie les 3 dans l'ordre 22/11, 14/11, None ; `list_diary_tmdb_ids("paul")` == {id de paul}.
  - `test_latest_diary_entry_prefers_most_recent_watch` : deux entrées même film (2026-01-01 note 3, 2026-11-01 note 4.5) → `latest_diary_entry(...).rating == 4.5`.
  - `test_update_and_delete_diary_entry` : `update_diary_entry(id, {"rating": 2.0})` → note 2.0 et `updated_at` avancé ; `delete_diary_entry` → True puis `get_diary_entry` None ; second delete → False.
  - `test_tmdb_cache_roundtrip` : upsert puis `get_tmdb_movies([id, 999])` → seul `id`, `genres == ["SF"]` ; un second upsert remplace le titre.
  - `test_film_list_items_unique_and_cascade` : `add_film_list_item` deux fois → True puis False, `item_count == 1` ; `delete_film_list` → items supprimés.
  - `test_diary_does_not_touch_media_table` : après création d'entrées et d'items, `fetch_all()` vide.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_journal_store.py -q` — Expected: FAIL (`ImportError` / `AttributeError` sur `DiaryEntry` ou les méthodes).

- [ ] **Step 3: Implement** models, tables (dans `init_schema`, `CREATE TABLE IF NOT EXISTS`) et méthodes. Dates : `watched_on` stocké `YYYY-MM-DD`, datetimes ISO comme ailleurs ; `genres` en JSON.

- [ ] **Step 4: Run** the same command — Expected: 6 passed. Puis `.venv/Scripts/python.exe -m pytest tests/test_store.py tests/test_user_media_state.py -q` — Expected: pass.

- [ ] **Step 5: Commit** `git add backend/core/models.py backend/core/store.py tests/test_journal_store.py && git commit -m "Ajoute le stockage du journal et des listes"`

---

### Task 2: Routes du journal

**Files:**
- Create: `backend/journal_api.py`
- Modify: `main.py` (monter `journal_router` comme `api_router`)
- Test: `tests/test_journal_api.py`

**Interfaces:**
- Consumes: Task 1 store methods and models.
- Produces:
  - `journal_router = APIRouter(prefix="/api", tags=["journal"], dependencies=[Depends(get_current_user)])` ; utiliser `get_store` de `backend.api`.
  - `async def ensure_cached_movie(store: MediaStore, tmdb_id: int) -> dict` : renvoie le cache s'il existe, sinon `TMDBClient().get_movie_details` → `upsert_tmdb_movie` (titre `title`, année depuis `release_date`, `poster_url` via `TMDBClient.poster_url_from_path`, genres via `get_genres`) ; détails `None` → `HTTPException(502, "TMDB est injoignable, réessaie plus tard.")`. `TMDBClient` importé au niveau module (pour `monkeypatch.setattr(journal_api, "TMDBClient", Fake)`).
  - `async def sync_library_state(store: MediaStore, user_id: str, tmdb_id: int) -> None` : si une ligne `media` de type « Film » a ce `tmdb_id`, `upsert_user_media_state(user, media.id, {"status": "Terminé", "is_watchlist": False, **({"rating": f"{latest.rating:g}"} if latest.rating is not None else {})})` avec `latest = latest_diary_entry(...)`. Ne crée jamais de ligne `media`.
  - `GET /api/journal` → `{"entries": [{id, tmdb_id, watched_on, rating, review, in_cinema, source, created_at, movie: {title, year, release_date, poster_url}, media_id: str | None}]}` (ordre de Task 1 ; `media_id` = film de la bibliothèque avec ce `tmdb_id`, sinon `null`).
  - `POST /api/journal` body `DiaryEntryCreate {tmdb_id: int, watched_on: date | None = <aujourd'hui si champ absent>, rating: float | None = None, review: str | None = None, in_cinema: bool = False}` → 201 + entrée sérialisée. Valide la note (Global Constraints) et `watched_on <= date.today()` → sinon 422. Appelle `ensure_cached_movie` puis `sync_library_state`.
  - `PATCH /api/journal/{entry_id}` body partiel (mêmes champs sauf `tmdb_id`) → entrée ; 404 si absente ou d'un autre ; puis `sync_library_state`.
  - `DELETE /api/journal/{entry_id}` → 204 ; 404 si absente ou d'un autre ; ne touche pas `user_media_state`.

- [ ] **Step 1: Write the failing tests** in `tests/test_journal_api.py`. Client : comme `tests/test_auth_api._client` mais en montant aussi `journal_router` ; `_setup(client)` (admin Hugo) ; `_login_as_new_user` importé de `tests.test_coloc_rentals` pour un coloc. `FakeTMDB` avec `get_movie_details` → `{"id": 550, "title": "Dune 2", "release_date": "2024-02-28", "poster_path": "/d.jpg", "genres": [{"id": 1, "name": "SF"}]}` et un compteur d'appels.
  - `test_add_entry_outside_library_creates_no_media` : POST `{tmdb_id: 550, watched_on: "2026-11-22", rating: 4.5, in_cinema: true}` → 201, `movie.title == "Dune 2"`, `media_id is None` ; `MediaStore(...).fetch_all()` vide.
  - `test_watched_on_defaults_to_today_and_future_is_rejected` : sans `watched_on` → aujourd'hui ; `watched_on` = demain → 422 ; `rating: 4.2` → 422.
  - `test_cached_movie_skips_tmdb` : deux POST même film → `get_movie_details` appelé une seule fois.
  - `test_tmdb_down_creates_nothing` : FakeTMDB renvoie `None` → 502, `GET /api/journal` vide.
  - `test_journal_is_private` : Hugo crée une entrée ; coloc → `GET` ne la voit pas ; `PATCH`/`DELETE /api/journal/{id}` → 404 ; l'entrée de Hugo inchangée.
  - `test_entry_on_library_film_marks_it_seen` : créer une ligne media Film `tmdb_id=550` ; POST note 4 → `GET /api/medias` : ce film a `status == "Terminé"`, `rating == "4"` ; `media_id` renseigné dans le journal.
  - `test_delete_keeps_library_state` : suite du précédent, DELETE → 204, le film reste « Terminé ».

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_journal_api.py -q` — Expected: FAIL (`ModuleNotFoundError: backend.journal_api`).

- [ ] **Step 3: Implement** `backend/journal_api.py` et le montage dans `main.py`.

- [ ] **Step 4: Run** the same command — Expected: 7 passed.

- [ ] **Step 5: Commit** `git add backend/journal_api.py main.py tests/test_journal_api.py && git commit -m "Ajoute les routes du journal Vu"`

---

### Task 3: Bibliothèque et recommandations reliées au journal

**Files:**
- Modify: `backend/api.py` — `_media_for_user` (~546), `list_medias` (~576) et `get_media` (~746), `update_personal_media` (~795), bloc `seen_tmdb_ids` (~952-985), route des réponses de recommandation (~1344-1410)
- Test: `tests/test_journal_api.py` (ajouts)

**Interfaces:**
- Consumes: `list_diary_tmdb_ids`, `latest_diary_entry`, `create_diary_entry`, `update_diary_entry` (Task 1) ; `ensure_cached_movie` (Task 2, importé paresseusement dans la fonction pour éviter un import circulaire).
- Produces:
  - `_media_for_user(..., seen_tmdb_ids: set[int] | None = None)` : après le calcul existant, si `media.tmdb_id in seen_tmdb_ids` et que le statut n'est pas déjà « Terminé »/« Terminée » → `status="Terminé"`, `is_watchlist=False` (y compris dans la branche du propriétaire du catalogue). `list_medias` et `get_media` chargent `list_diary_tmdb_ids` une fois et le passent.
  - `update_personal_media` : après l'upsert, si le film a un `tmdb_id` et que `fields` contient une note non vide ou `status == "Terminé"` : `latest = latest_diary_entry(...)` ; s'il existe → `update_diary_entry(latest.id, {rating?, review?})` (uniquement les champs présents ; note convertie par `_rating_value`) ; sinon → `create_diary_entry(source="library", watched_on=today, rating, review)` après `ensure_cached_movie` (si TMDB échoue : journaliser un warning, ne pas faire échouer le PATCH).
    *Ruling du plan :* la spec dit « crée une entrée datée du jour » ; on met à jour la plus récente si elle existe, pour qu'une correction de note ne crée pas un faux revisionnage.
  - Recommandations : `seen_tmdb_ids` et `hard_seen_tmdb_ids` reçoivent `await store.list_diary_tmdb_ids(user_id)`.
  - Réponse `already_seen` (route des réponses, et `POST /recommendations/events` si `event_type == "already_seen"`) avec `value` numérique : si `latest_diary_entry` est `None` → créer une entrée `source="recommendation"`, `watched_on=None`, sans note (cache TMDB via `ensure_cached_movie` ; échec TMDB = warning, la réponse continue).

- [ ] **Step 1: Write the failing tests** (ajoutés à `tests/test_journal_api.py`) :
  - `test_library_rating_writes_one_journal_entry` : media Film `tmdb_id=550` ; `PATCH /api/medias/{id}/personal {"rating": "4"}` puis `{"rating": "4.5"}` → `GET /api/journal` : exactement 1 entrée, note 4.5, `source == "library"`, `watched_on` = aujourd'hui.
  - `test_journal_film_arriving_later_shows_as_seen` : POST journal pour 550 sans media ; puis créer la ligne media Film 550 → `GET /api/medias` la montre « Terminé ».
  - `test_journal_feeds_recommendation_seen_set` : tester la fonction qui construit `seen_tmdb_ids` (ou le pool) avec une entrée de journal 550 → 550 exclu des candidats. Utiliser le même point d'entrée que `tests/test_recommendation_pool.py`.
  - `test_already_seen_answer_creates_dateless_entry` : enregistrer un événement `already_seen` valeur `"550"` via `POST /api/recommendations/events` deux fois → 1 entrée, `watched_on is None`, `source == "recommendation"`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_journal_api.py -q` — Expected: les 4 nouveaux FAIL, les 7 anciens passent.

- [ ] **Step 3: Implement** les changements de `backend/api.py` (CRLF préservé).

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_journal_api.py tests/test_user_media_state.py tests/test_recommendation_pool.py tests/test_recommendation_events.py tests/test_coloc_rentals.py -q` — Expected: tout passe.

- [ ] **Step 5: Commit** `git add backend/api.py tests/test_journal_api.py && git commit -m "Relie le journal à la bibliothèque et aux recommandations"`

---

### Task 4: Routes des listes partagées

**Files:**
- Modify: `backend/journal_api.py`, `backend/api.py` (extraire `_library_states`)
- Test: `tests/test_film_lists_api.py`

**Interfaces:**
- Consumes: Task 1 list methods, `ensure_cached_movie` (Task 2), `list_diary_tmdb_ids`.
- Produces:
  - `backend/api.py`: `async def _library_states(store: MediaStore) -> dict[str, dict]` — exactement le dictionnaire `states` que renvoie aujourd'hui `list_available_media` (mêmes règles d'exclusion des films retirés) ; `list_available_media` l'utilise.
  - `GET /api/lists` → `[{id, name, created_by_name, item_count}]`, plus récentes d'abord.
  - `POST /api/lists {name}` → 201 ; nom nettoyé, 1 à 60 caractères, sinon 422.
  - `PATCH /api/lists/{id} {name}` → liste ; `DELETE /api/lists/{id}` → 204 ; 404 si inconnue. Tout utilisateur connecté peut tout faire.
  - `GET /api/lists/{id}` → `{id, name, items: [{tmdb_id, title, year, release_date, poster_url, added_by_name, added_by_me, added_at, seen_by_me, library}]}` où `library` = `{media_id, state, progress_percent, ready}` pour un film « Film » de la bibliothèque ayant cet `tmdb_id` et présent dans `_library_states`, sinon `null` ; `seen_by_me` = `tmdb_id in list_diary_tmdb_ids(current user)`. Noms affichés via `AuthStore.list_users()` (`display_name`).
  - `POST /api/lists/{id}/items {tmdb_id}` → `{"added": bool, "item": <item sérialisé>}` (`added: false` si déjà présent, statut 200) ; `ensure_cached_movie` d'abord.
  - `DELETE /api/lists/{id}/items/{tmdb_id}` → 204 / 404.

- [ ] **Step 1: Write the failing tests** in `tests/test_film_lists_api.py` (client et FakeTMDB comme Task 2 ; un coloc via `_login_as_new_user`) :
  - `test_lists_are_shared_between_flatmates` : Hugo crée « Films à voir au ciné » et ajoute 550 ; le coloc voit la liste (`item_count == 1`, `added_by_name == "Hugo"`, `added_by_me` faux pour lui), la renomme et retire le film → 204.
  - `test_adding_twice_keeps_one_item` : deux POST 550 → `added` True puis False, un seul item.
  - `test_list_item_outside_library_creates_no_media` : après ajout, `fetch_all()` vide et `library is None`.
  - `test_list_item_shows_library_state` : ligne media Film 550 + `Availability(state="downloading", progress_percent=40)` → `library.state == "downloading"`, `ready` faux.
  - `test_seen_mark_is_personal` : Hugo a une entrée de journal 550 → `seen_by_me` vrai pour Hugo, faux pour le coloc ; le film reste dans la liste.
  - `test_list_name_validation` : nom vide ou 61 caractères → 422.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_film_lists_api.py -q` — Expected: FAIL (404 sur `/api/lists`).

- [ ] **Step 3: Implement** les routes et `_library_states`.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_film_lists_api.py tests/test_coloc_rentals.py -q` — Expected: tout passe (le test d'états de `test_coloc_rentals.py` couvre le refactor).

- [ ] **Step 5: Commit** `git add backend/journal_api.py backend/api.py tests/test_film_lists_api.py && git commit -m "Ajoute les listes de films partagées"`

---

### Task 5: Reprise de l'existant dans le journal

**Files:**
- Create: `backend/scripts/backfill_journal.py`
- Test: `tests/test_backfill_journal.py`

**Interfaces:**
- Consumes: `MediaStore`, `AuthStore`, `create_diary_entry`, `list_diary_tmdb_ids`, `_rating_value` (`backend/core/recommendations.py`).
- Produces:
  - `async def plan_backfill(media_store: MediaStore, auth_store: AuthStore) -> list[DiaryEntry]` : pour chaque utilisateur et chaque media « Film » avec `tmdb_id` : source = `user_media_state` ; à défaut de ligne, et seulement pour le propriétaire du catalogue (premier admin, même règle que `get_catalogue_owner_id`), `media.status`/`media.rating`. Vu si statut ∈ {« Terminé », « Terminée », « A revoir »} ou note non vide. Note = `_rating_value(raw)` arrondie au 0,5 le plus proche et bornée à [0,5 ; 5] ; illisible → `None` et `review` complétée par `"Note d'origine : <raw>"` (sur une nouvelle ligne si une critique existe). `watched_on=None`, `source="backfill"`. Ignore tout couple (utilisateur, tmdb_id) ayant déjà une entrée.
  - `async def apply_backfill(media_store, entries) -> int`.
  - CLI `python -m backend.scripts.backfill_journal` : aperçu (compte par utilisateur, 10 premiers titres) ; `--apply` écrit. Même forme que `backend/scripts/migrate_ratings_to_user_state.py`.

- [ ] **Step 1: Write the failing tests** :
  - `test_backfill_reads_user_states_and_owner_fallback` : admin (propriétaire) avec `media.rating="4"` sans ligne d'état ; coloc avec état « A revoir » sur un autre film ; un film sans `tmdb_id` noté → 2 entrées, aucune pour le film sans `tmdb_id`.
  - `test_backfill_converts_and_keeps_unreadable_ratings` : note `"⭐⭐⭐⭐⭐⭐⭐⭐"` → valeur de `_rating_value` arrondie ; note `"top"` → `rating is None`, `review` se termine par `"Note d'origine : top"`.
  - `test_backfill_is_idempotent` : `apply` deux fois → le second plan est vide.
  - `test_backfill_second_admin_gets_no_fallback` : un second admin sans état n'hérite pas de `media.rating`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_backfill_journal.py -q` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** le script.

- [ ] **Step 4: Run** the same command — Expected: 4 passed. Puis l'aperçu sur une **copie** de la vraie base (`Config.DB_PATH` pointé vers la copie) pour vérifier qu'il annonce environ 90 films repris ; ne jamais lancer `--apply` sur la vraie base (l'utilisateur le fera au déploiement).

- [ ] **Step 5: Commit** `git add backend/scripts/backfill_journal.py tests/test_backfill_journal.py && git commit -m "Ajoute la reprise des films vus dans le journal"`

---

### Task 6: Logique d'affichage du journal et des listes

**Files:**
- Create: `proto-ui/src/journal.js`, `proto-ui/src/journal.test.js`
- Modify: `proto-ui/package.json` (ajouter `src/journal.test.js` au script `test`)

**Interfaces:**
- Consumes: `CINEMA_WINDOW_DAYS`, `enRouteBadge` de `library.js`.
- Produces:
  - `groupDiaryByMonth(entries) -> Array<{key: string, label: string, entries}>` : clés `YYYY-MM`, libellé « Novembre 2026 » (mois en français, majuscule initiale), groupes du plus récent au plus ancien ; entrées sans `watched_on` dans un dernier groupe `{key: 'unknown', label: 'Date inconnue'}` ; ordre des entrées conservé.
  - `formatStars(rating) -> string` : 4.5 → `'★★★★½'`, 3 → `'★★★'`, `null` → `''`.
  - `listItemBadge(item, now) -> {label, tone} | null` : `item.library?.ready` → `{label: 'Sur le serveur', tone: 'ready'}` ; `item.library` → `enRouteBadge(item.release_date, item.library, now)` ; sinon sortie future → « Sort le JJ/MM », sortie depuis moins de `CINEMA_WINDOW_DAYS` → « Au cinéma » (mêmes tons que `enRouteBadge`), sinon `null`.
  - `shouldOfferSeerrRequest(addResult) -> boolean` : vrai si `addResult.item.library == null`.
  - `todayIsoDate(now) -> 'YYYY-MM-DD'` en date locale.

- [ ] **Step 1: Write the failing tests** in `journal.test.js` (style de `rentals.test.js`) : un test par fonction et par branche ci-dessus, avec `now = new Date(2026, 10, 26)` : sortie `'2026-12-17'` → « Sort le 17/12 » ; `'2026-10-01'` → « Au cinéma » ; `'2020-01-01'` sans library → `null` ; library `{state: 'downloading', progress_percent: 40}` → « Téléchargement 40 % » ; entrées `[nov, null, oct]` → groupes `['2026-11', '2026-10', 'unknown']`.

- [ ] **Step 2: Run** `cd proto-ui && npm test` — Expected: FAIL (module introuvable).

- [ ] **Step 3: Implement** `journal.js`.

- [ ] **Step 4: Run** `cd proto-ui && npm test` — Expected: tous les tests passent.

- [ ] **Step 5: Commit** `git add proto-ui/src/journal.js proto-ui/src/journal.test.js proto-ui/package.json && git commit -m "Ajoute la logique d'affichage du journal et des listes"`

---

### Task 7: Page Journal, fenêtre « Vu » et bouton dans la bibliothèque

**Files:**
- Modify: `proto-ui/src/api.js`, `proto-ui/src/BackstagePrototype.jsx`, `proto-ui/src/components/FilmDetailView.jsx`
- Create: `proto-ui/src/components/SeenDialog.jsx`, `proto-ui/src/components/JournalView.jsx`

**Interfaces:**
- Consumes: routes de Task 2 ; `groupDiaryByMonth`, `formatStars`, `todayIsoDate` (Task 6) ; `fetchTMDBRating` (relie un film sans `tmdb_id`), `searchTMDB` existants.
- Produces:
  - `api.js` : `fetchJournal()`, `createJournalEntry(payload)`, `updateJournalEntry(id, payload)`, `deleteJournalEntry(id)` (même gestion d'erreur que `updatePersonalMedia`).
  - `SeenDialog({movie: {tmdbId, title, posterUrl}, initial, isDarkMode, onSave(payload), onClose})` : date (défaut `todayIsoDate`, `max` = aujourd'hui, bouton pour vider → date inconnue), note par demi-étoiles (effaçable), critique, case « Vu au cinéma ».
  - `JournalView({isDarkMode, onOpenLibraryFilm(mediaId), showToast})` : recherche TMDB pour ajouter, groupes par mois, modifier / supprimer (confirmation) une entrée.
  - Navigation : `activeView === 'journal'` ; entrée « Journal » dans les onglets d'en-tête (~1440) et la barre mobile (~1539).
  - Fiche film de la bibliothèque : bouton « Vu » qui ouvre `SeenDialog`. Sans `tmdbId`, appeler d'abord `fetchTMDBRating(id)` ; si toujours aucun `tmdb_id`, retomber sur `handleRate` actuel. Après enregistrement, recharger les médias pour afficher l'état « vu ».

- [ ] **Step 1: Implement** api functions, components and wiring.
- [ ] **Step 2: Run** `cd proto-ui && npm test && npm run build` — Expected: tests verts, build sans erreur.
- [ ] **Step 3: Verify in the sandbox** (copie de la base, port 8091, cf. Global Constraints) : ajouter un film hors bibliothèque au journal → visible dans le mois courant, absent de la grille et d'« En route » ; marquer « Vu » un film de la bibliothèque → statut vu ; un second compte ne voit pas le journal ; largeur 375 px : la barre mobile reste lisible (sinon regrouper Journal et Listes sous un onglet « Plus » — choix laissé au builder). Capture d'écran en preuve.
- [ ] **Step 4: Commit** `git add proto-ui/src && git commit -m "Ajoute la page Journal et le bouton Vu"`

---

### Task 8: Page Listes et proposition de demande Seerr

**Files:**
- Modify: `proto-ui/src/api.js`, `proto-ui/src/BackstagePrototype.jsx`
- Create: `proto-ui/src/components/ListsView.jsx`

**Interfaces:**
- Consumes: routes de Task 4 ; `listItemBadge`, `shouldOfferSeerrRequest` (Task 6) ; `SeenDialog`, `createJournalEntry` (Task 7) ; `createSeerrRequest(tmdbId, 'movie', …)` existant (flux `pendingSeerrFilm`, ~253 et ~576).
- Produces:
  - `api.js` : `fetchFilmLists()`, `createFilmList(name)`, `renameFilmList(id, name)`, `deleteFilmList(id)`, `fetchFilmList(id)`, `addFilmListItem(id, tmdbId)`, `removeFilmListItem(id, tmdbId)`.
  - `ListsView({isDarkMode, showToast, onRequestOnServer(film)})` : vue d'ensemble (nom, nombre de films), création, ouverture d'une liste, renommer, supprimer (confirmation « Supprimer la liste « X » pour tous les colocs ? »). Dans une liste : recherche TMDB pour ajouter ; chaque film = affiche, titre, badge `listItemBadge` (couleurs `BADGE_TONE_CLASSES`, ajouter le ton `ready` s'il manque), « ajouté par X » / « ajouté par toi », « ✓ Vu » si `seen_by_me`, boutons « Vu » (ouvre `SeenDialog`) et « Retirer ».
  - Après un ajout avec `added: true` et `shouldOfferSeerrRequest` vrai → fenêtre « Demander aussi sur le serveur ? » (Oui → `onRequestOnServer` réutilise le flux `pendingSeerrFilm` existant ; Non → ferme, le film reste). `added: false` → toast « Déjà dans la liste ».
  - Navigation : `activeView === 'lists'`, entrée « Listes » à côté de « Journal ».

- [ ] **Step 1: Implement** api functions, `ListsView` and wiring.
- [ ] **Step 2: Run** `cd proto-ui && npm test && npm run build` — Expected: verts.
- [ ] **Step 3: Verify in the sandbox** : créer « Films à voir au ciné », ajouter un film à venir → badge « Sort le JJ/MM » et fenêtre Seerr (répondre Non : le film reste, aucune fiche bibliothèque) ; second compte voit la liste ; marquer « Vu » → « ✓ Vu » pour ce compte seulement, le film reste. Capture d'écran.
- [ ] **Step 4: Commit** `git add proto-ui/src && git commit -m "Ajoute la page Listes et la proposition de demande"`

---

### Task 9: Vérification d'ensemble

- [ ] **Step 1: Run** `.venv/Scripts/python.exe -m pytest -q > <workspace>/pytest.txt` et lire la fin — Expected: seuls les 11 échecs préexistants (Global Constraints).
- [ ] **Step 2: Run** `cd proto-ui && npm test && npm run build` — Expected: verts.
- [ ] **Step 3:** Vérifier `git diff --stat main` : aucun fichier dont toutes les lignes changent (fins de ligne).
