# Cinéma et agenda — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lire chaque jour la programmation du Ciné Grand Sud, prévenir le salon quand un film des listes arrive ou part, répondre à `@ciné` dans le tchat, et publier un agenda ICS des dates de sortie des films suivis.

**Architecture:** Un analyseur HTML pur (`cinema_site.py`) alimente un petit magasin SQLite dédié (`cinema_store.py`). Une synchronisation quotidienne (`cinema_sync.py`) relie les films à TMDB et poste les rappels calculés par une fonction pure (`cinema_reminders.py`). Le bot (`cinema_bot.py`) répond dans `post_chat_message`. L'ICS (`ics.py`) est servi par `cinema_api.py`. Côté interface : boutons et horaires dans `ChatDock.jsx`, bouton d'agenda dans `ListsView.jsx`.

**Tech Stack:** FastAPI, SQLite (`MediaStore`), `html.parser` de la bibliothèque standard, httpx (`backend/core/http.py`), React (`proto-ui`), `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-26-cinema-et-agenda-design.md`

## Global Constraints

- Uniquement le Multiplexe Ciné Grand Sud ; base `CINEMA_BASE_URL` (défaut `https://cine-reunion.com`), désactivable par `CINEMA_ENABLED`.
- Heures et « aujourd'hui » en `Indian/Reunion` (constante, pas `RECOMMENDATION_TIMEZONE`). Les dates/heures locales sont stockées naïves au format `YYYY-MM-DDTHH:MM`.
- Rappels : fenêtre des **7 prochains jours**, une seule fois par film et par type (`arrivee`, `fin`), marge de fin **2 jours**, premier passage silencieux pour `arrivee` seulement.
- Données périmées : plus de **2 jours** depuis la dernière lecture réussie → « Horaires indisponibles depuis le JJ/MM. »
- Une programmation lue sans aucun film = échec ; les séances en base ne sont remplacées qu'après une lecture réussie.
- Un film du site « pas trouvé » dans TMDB est retenté au plus une fois par **7 jours**.
- ICS : `GET /api/cinema/agenda.ics?token=…` sans session, un `VEVENT` d'une journée par film suivi, films sortis dans les **365 derniers jours** ou à venir, CRLF, repli à 75 octets, `text/calendar; charset=utf-8`.
- Aucune nouvelle dépendance Python.
- Fins de ligne : CRLF pour `backend/api.py`, `backend/core/store.py`, `backend/core/models.py`, `main.py`, `proto-ui/src/api.js`, `proto-ui/src/library.js` (éditer via un script qui conserve CRLF) ; LF pour tout fichier nouveau et pour `ChatDock.jsx`, `ListsView.jsx`, `BackstagePrototype.jsx`, `journal_api.py`, `tmdb.py`, `scheduler.py`, `config.py` (vérifié le 2026-11-26).
- Tests Python : `.venv/Scripts/python.exe -m pytest` ; seuls échecs admis, les 11 préexistants (`test_auth_api` ×8, `test_auth_store` ×2, `test_catalogue_playback_ui` ×1). Interface : `npm --prefix proto-ui test`, `npm --prefix proto-ui run build`.
- Jamais le vrai site dans les tests (pages dans `tests/fixtures/cinema/`), jamais le vrai serveur (8090) ; essais manuels sur copie de base, port 8091.
- Textes visibles en français.

## Review Focus

1. **Titre du site avec suffixe de format** (« Avengers : Doomsday INFINITY VISION ») : le titre affiché et cherché dans TMDB doit être le texte `alt` de l'affiche, sans suffixe. Test dans Task 1.
2. **Film du site sans id TMDB** : il apparaît dans `@ciné films` et ses horaires, mais jamais dans les rappels ni l'ICS. Tests dans Task 4 et Task 6.
3. **Message `@ciné` alors que le bot plante** (base verrouillée, exception) : le message humain est enregistré et renvoyé, l'erreur est journalisée. Test dans Task 6.
4. **Jeton ICS inconnu ou vide** : 404, sans détail. Test dans Task 7.
5. **Séance passée** : jamais affichée dans `ce soir` ni dans les horaires d'un film (comparaison à l'heure de La Réunion, pas UTC). Test dans Task 6.

---

### Task 1: Analyseur des pages du site

**Files:**
- Create: `backend/core/cinema_site.py`
- Test: `tests/test_cinema_site.py` (utilise `tests/fixtures/cinema/*.html`, déjà commités)

**Interfaces:**
- Produces:
  ```python
  GRAND_SUD_PATH = "/programmation/multiplexe-cine-grand-sud-saint-pierre/"
  UPCOMING_PATH = "/films/prochaines-sorties/"
  @dataclass(frozen=True)
  class Showtime: starts_at: datetime; version: str; booking_url: Optional[str]   # starts_at naïf, heure locale
  @dataclass(frozen=True)
  class ProgrammeFilm: site_id: int; title: str; url: str; poster_url: Optional[str]; showtimes: tuple[Showtime, ...]
  @dataclass(frozen=True)
  class FilmDetails: original_title: Optional[str]; directors: tuple[str, ...]; release_national: Optional[date]; release_reunion: Optional[date]
  @dataclass(frozen=True)
  class UpcomingFilm: site_id: int; title: str; url: str; poster_url: Optional[str]
  def parse_french_date(text: str) -> Optional[date]
  def parse_programme(html: str) -> list[ProgrammeFilm]
  def parse_film_page(html: str) -> FilmDetails
  def parse_upcoming(html: str) -> list[UpcomingFilm]
  ```
  `url` et `poster_url` sont les chemins tels qu'écrits sur le site (`/film/camembert/16263/`, `/images/movie/5SQOQ.jpg`).

Structure relevée dans les pages :
- Programmation : un bloc par film `div.movie.movie--preview` ; id et url via le premier `a[href^="/film/"]` (`/film/<slug>/<id>/`) ; titre = `alt` de l'`img` de `div.movie__images` ; par jour, `div.time-select__group` contenant `p.time-select__place` (« mercredi 16 décembre 2026 ») puis des `a.achat-billet[href]` contenant `li.time-select__item[data-time="HH:MM"]` dont les `span` non vides forment la version (`VF`, `VOST`, `VF 3D`). Ignorer tout ce qui est hors de ces blocs (bandeau d'événements, carrousels).
- Page film : des `p.movie__option` contenant `<strong>Libellé: </strong><a>valeur</a>` pour « Sortie à La Réunion », « Sortie nationale », « Titre original », « Réalisateur » (plusieurs noms séparés par des virgules).
- Prochaines sorties : blocs `div.movie.movie--test` ; titre = `alt` de l'`img`, id via `a.movie-beta__link[href]`.

- [ ] **Step 1: Write the failing tests**

```python
FIXTURES = Path(__file__).parent / "fixtures" / "cinema"
def _read(name): return (FIXTURES / name).read_text(encoding="utf-8")

def test_parse_french_date():
    assert parse_french_date("mercredi 18 novembre 2026") == date(2026, 11, 18)
    assert parse_french_date("Mardi 1 décembre 2026") == date(2026, 12, 1)
    assert parse_french_date("1er août 2027") == date(2027, 8, 1)
    assert parse_french_date("bientôt") is None

def test_programme_lists_every_film_block():
    films = parse_programme(_read("programmation-grand-sud.html"))
    assert len(films) == 20
    camembert = next(f for f in films if f.site_id == 16263)
    assert camembert.title == "Camembert"
    assert camembert.url == "/film/camembert/16263/"
    assert camembert.showtimes

def test_programme_title_comes_from_poster_alt_without_format_suffix():
    films = parse_programme(_read("programmation-grand-sud.html"))
    avengers = next(f for f in films if f.site_id == 16259)
    assert avengers.title == "Avengers : Doomsday"

def test_programme_showtimes_have_time_version_and_booking_link():
    films = parse_programme(_read("programmation-grand-sud.html"))
    avengers = next(f for f in films if f.site_id == 16259)
    first = avengers.showtimes[0]
    assert first.starts_at == datetime(2026, 12, 16, 10, 0)
    assert first.version == "VF"
    assert first.booking_url.startswith("https://www.ticketingcine.com/EMS1278/")
    versions = {s.version for f in films for s in f.showtimes}
    assert "VOST" in versions

def test_programme_of_unrelated_html_is_empty():
    assert parse_programme("<html><body><p>Maintenance</p></body></html>") == []

def test_film_page_details():
    details = parse_film_page(_read("film-camembert.html"))
    assert details == FilmDetails(
        original_title="Camembert",
        directors=("Matthieu Rumani", "Nicolas Slomka"),
        release_national=date(2026, 11, 18),
        release_reunion=date(2026, 11, 18),
    )

def test_upcoming_films():
    films = parse_upcoming(_read("prochaines-sorties.html"))
    assert len(films) == 15
    assert UpcomingFilm(16238, "Astérix - Le Royaume de Nubie",
                        "/film/asterix-le-royaume-de-nubie/16238/",
                        "/images/movie/asterix-le-royaume-de-nubie-allocine-313265.jpg") in films
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_site.py -q`
Expected: FAIL (`ModuleNotFoundError: backend.core.cinema_site`)

- [ ] **Step 3: Implement `backend/core/cinema_site.py`** with `html.parser.HTMLParser` subclasses (one state machine per page kind). `parse_french_date` accepte un jour de semaine optionnel, « 1er », les mois avec ou sans accents, insensible à la casse. Décoder les entités HTML (`convert_charrefs=True`).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_site.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/core/cinema_site.py tests/test_cinema_site.py
git commit -m "Ajoute la lecture des pages du Ciné Grand Sud"
```

---

### Task 2: Stockage (tables ciné, colonne payload du tchat, date de sortie française)

**Files:**
- Create: `backend/core/cinema_store.py`
- Modify: `backend/core/store.py` (CRLF) : `init_schema` appelle `create_cinema_tables(conn)` ; colonne `payload TEXT` sur `chat_messages` ; colonne `fr_release_date TEXT` sur `tmdb_movie_cache` (migrations `ALTER TABLE` comme les existantes) ; `create_chat_message(..., payload: Optional[dict] = None)` ; `_row_to_chat_message` ajoute `"payload"` (dict ou `None`) ; `_upsert_tmdb_movie_sync` écrit `fr_release_date`.
- Test: `tests/test_cinema_store.py`, et un test ajouté à `tests/test_chat.py`

**Interfaces:**
- Consumes: `Showtime`, `FilmDetails` (Task 1).
- Produces (`cinema_store.py`) :
  ```python
  def create_cinema_tables(conn: sqlite3.Connection) -> None
  class CinemaStore:
      def __init__(self, db_path: str)
      async def upsert_site_film(self, site_id: int, title: str, url: str, poster_url: Optional[str]) -> None   # ne touche pas aux autres colonnes
      async def set_film_details(self, site_id: int, details: FilmDetails, fetched_at: datetime) -> None
      async def set_tmdb_match(self, site_id: int, tmdb_id: Optional[int], attempted_at: datetime) -> None
      async def get_site_films(self) -> dict[int, dict]
          # clés : site_id, title, url, poster_url, original_title, directors (list[str]), release_national,
          # release_reunion (ISO ou None), tmdb_id, match_attempted_at, details_fetched_at
      async def replace_showtimes(self, showtimes: dict[int, list[Showtime]]) -> None   # remplace TOUTES les séances, transaction unique
      async def list_showtimes(self, start: datetime, end: Optional[datetime] = None) -> list[dict]
          # triées par starts_at ; clés : site_id, starts_at (datetime naïf), version, booking_url
      async def sent_reminders(self) -> set[tuple[int, str]]
      async def record_reminder(self, site_id: int, kind: str, sent_at: datetime) -> None   # INSERT OR IGNORE
      async def record_success(self, at: datetime) -> None
      async def record_failure(self, at: datetime, error: str) -> None
      async def get_status(self) -> dict   # {"last_success_at": datetime|None, "last_error": str|None, "last_error_at": datetime|None}
      async def tracked_tmdb_ids(self) -> set[int]   # DISTINCT tmdb_id de film_list_items
      async def calendar_token_for(self, user_id: str) -> Optional[str]
      async def set_calendar_token(self, user_id: str, token: str) -> None   # remplace l'ancien
      async def user_for_calendar_token(self, token: str) -> Optional[str]
  ```
  Tables : `cinema_films` (site_id PK), `cinema_showtimes`, `cinema_reminders` (PK site_id+kind), `cinema_status` (une ligne id=1), `calendar_tokens` (user_id PK, token UNIQUE, created_at). Le jeton est stocké en clair (ruling : il n'ouvre qu'un agenda de dates de sortie des listes communes ; le montrer à nouveau dans l'interface l'exige).

- [ ] **Step 1: Write the failing tests** (`tests/test_cinema_store.py`, base temporaire via `MediaStore(path).init_schema()`)

```python
def test_replace_showtimes_swaps_the_whole_set(cinema): ...
    # après replace({1: [s1, s2]}) puis replace({2: [s3]}), list_showtimes(datetime(2026,1,1)) ne contient que s3
def test_list_showtimes_filters_by_window(cinema): ...
    # start inclus, end exclu, ordre chronologique
def test_upsert_site_film_keeps_details_and_match(cinema): ...
    # set_film_details + set_tmdb_match puis upsert_site_film(nouveau titre) → details et tmdb_id conservés, titre mis à jour
def test_reminders_are_recorded_once(cinema): ...
    # record_reminder deux fois → sent_reminders() == {(1, "arrivee")}
def test_status_tracks_success_and_failure(cinema): ...
def test_tracked_ids_come_from_shared_lists(cinema, media_store): ...
    # deux listes contenant 550 et 551 (550 en double) → {550, 551}
def test_calendar_token_roundtrip_and_regeneration(cinema): ...
    # set "a" pour hugo, user_for("a") == "hugo" ; set "b" → user_for("a") is None, user_for("b") == "hugo"
```
Dans `tests/test_chat.py` :
```python
def test_bot_message_keeps_its_payload(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.create_chat_message("bot:cine", "Ciné", None, "Films", payload={"type": "cine_help", "commands": []}))
    message = asyncio.run(store.list_chat_messages())[0]
    assert message["payload"] == {"type": "cine_help", "commands": []}
    # et un message humain a "payload": None
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_store.py tests/test_chat.py -q`
Expected: FAIL (module absent, `payload` inattendu)

- [ ] **Step 3: Implement** `cinema_store.py` (méthodes synchrones `_..._sync` + enveloppes `asyncio.to_thread`, comme `MediaStore`) et les modifications de `store.py` (script CRLF).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_store.py tests/test_chat.py tests/test_journal_store.py tests/test_store.py -q`
Expected: tout passe

- [ ] **Step 5: Commit**

```bash
git add backend/core/cinema_store.py backend/core/store.py tests/test_cinema_store.py tests/test_chat.py
git commit -m "Ajoute le stockage du cinéma et les messages enrichis du tchat"
```

---

### Task 3: Date de sortie française en salle (TMDB)

**Files:**
- Modify: `backend/core/tmdb.py`, `backend/journal_api.py` (`_movie_from_details`)
- Test: `tests/test_tmdb.py`, `tests/test_journal_api.py`

**Interfaces:**
- Produces: `def french_theatrical_date(details: dict) -> Optional[str]` (fonction de module dans `tmdb.py`) : dans `details["release_dates"]["results"]`, l'entrée `iso_3166_1 == "FR"` ; la plus ancienne date de type 3, sinon de type 2 ; renvoie `YYYY-MM-DD` ou `None`. `_movie_from_details` ajoute la clé `fr_release_date`, donc le cache la stocke.

- [ ] **Step 1: Write the failing tests**

```python
def test_french_theatrical_date_prefers_type_3():
    details = {"release_dates": {"results": [
        {"iso_3166_1": "US", "release_dates": [{"type": 3, "release_date": "2026-12-10T00:00:00.000Z"}]},
        {"iso_3166_1": "FR", "release_dates": [
            {"type": 2, "release_date": "2026-12-01T00:00:00.000Z"},
            {"type": 3, "release_date": "2026-12-16T00:00:00.000Z"},
            {"type": 4, "release_date": "2027-03-01T00:00:00.000Z"}]}]}}
    assert french_theatrical_date(details) == "2026-12-16"

def test_french_theatrical_date_falls_back_to_limited_then_none():
    limited = {"release_dates": {"results": [{"iso_3166_1": "FR", "release_dates": [{"type": 2, "release_date": "2026-12-01T00:00:00.000Z"}]}]}}
    assert french_theatrical_date(limited) == "2026-12-01"
    streaming = {"release_dates": {"results": [{"iso_3166_1": "FR", "release_dates": [{"type": 4, "release_date": "2026-12-01T00:00:00.000Z"}]}]}}
    assert french_theatrical_date(streaming) is None
    assert french_theatrical_date({}) is None
```
Dans `tests/test_journal_api.py`, étendre `FakeTMDB.get_movie_details` avec un `release_dates` FR type 3 `2024-02-28` et ajouter :
```python
def test_cached_movie_keeps_french_release_date(client):
    client.post("/api/journal", json={"tmdb_id": 550})
    assert asyncio.run(_store().get_tmdb_movies([550]))[550]["fr_release_date"] == "2024-02-28"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_tmdb.py tests/test_journal_api.py -q`
Expected: FAIL (`ImportError: french_theatrical_date`, puis `KeyError`/`None`)

- [ ] **Step 3: Implement** la fonction et la clé dans `_movie_from_details`.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_tmdb.py tests/test_journal_api.py tests/test_film_lists_api.py -q`
Expected: tout passe

- [ ] **Step 5: Commit**

```bash
git add backend/core/tmdb.py backend/journal_api.py tests/test_tmdb.py tests/test_journal_api.py
git commit -m "Garde la date de sortie française en salle des films"
```

---

### Task 4: Calcul des rappels

**Files:**
- Create: `backend/core/cinema_reminders.py`
- Test: `tests/test_cinema_reminders.py`

**Interfaces:**
- Produces:
  ```python
  REMINDER_WINDOW_DAYS = 7
  END_MARGIN_DAYS = 2
  @dataclass(frozen=True)
  class Reminder: site_id: int; kind: str; first: datetime; last: datetime; post: bool
  def compute_reminders(showtimes: dict[int, list[datetime]], tracked_site_ids: set[int],
                        sent: set[tuple[int, str]], now: datetime, first_run: bool) -> list[Reminder]
  ```
  Règles (fenêtre = `[now, now + 7 jours)`, seules les séances dans la fenêtre comptent ; `window_last_day` = dernier jour ayant une séance, tous films confondus) :
  - `arrivee` : film suivi, au moins une séance dans la fenêtre, `(id, "arrivee")` absent de `sent`. `post=False` si `first_run`.
  - `fin` : film suivi, séances dans la fenêtre, `(id, "fin")` absent, pas d'`arrivee` pour ce film dans le même appel, jamais quand `first_run`, et `window_last_day - jour de sa dernière séance >= 2 jours`.
  - `first`/`last` : première et dernière séance du film dans la fenêtre. Ordre de sortie : par `site_id`, `arrivee` avant `fin`.

- [ ] **Step 1: Write the failing tests** (`now = datetime(2026, 11, 26, 9, 0)`)

```python
def test_tracked_film_arrives_once(): ...          # sent vide → [Reminder(1, "arrivee", ..., post=True)] ; sent={(1,"arrivee")} → []
def test_untracked_film_never_reminds(): ...       # tracked_site_ids=set() → []
def test_first_run_records_arrival_silently_and_skips_end(): ...
    # film 1 suivi, dernière séance le 27, autre film jusqu'au 1/12 → [Reminder(1,"arrivee",...,post=False)], pas de "fin"
def test_end_when_programme_runs_two_days_past_last_showing(): ...
    # film 1 : 26 et 27 ; film 2 : jusqu'au 29 → fin pour 1 (29-27 = 2) ; avec film 2 jusqu'au 28 → rien
def test_far_preview_is_ignored(): ...
    # film 1 n'a qu'une séance le 16/12 (hors fenêtre) → [] ; et cette séance n'allonge pas window_last_day pour les autres films
def test_no_end_in_the_same_run_as_arrival(): ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_reminders.py -q`
Expected: FAIL (module absent)

- [ ] **Step 3: Implement `compute_reminders`** (fonction pure, sans E/S).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_reminders.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/core/cinema_reminders.py tests/test_cinema_reminders.py
git commit -m "Ajoute le calcul des rappels d'arrivée et de dernières séances"
```

---

### Task 5: Synchronisation quotidienne

**Files:**
- Create: `backend/core/cinema_sync.py`
- Modify: `backend/config.py` (`CINEMA_ENABLED` défaut `true`, `CINEMA_BASE_URL` défaut `https://cine-reunion.com`, `CINEMA_REFRESH_HOURS` défaut `24`), `backend/core/scheduler.py` (`start_cinema_sync()` + `_cinema_loop()` : une passe au démarrage puis toutes les `CINEMA_REFRESH_HOURS` heures, exceptions journalisées), `main.py` (CRLF : `app.on_startup(scheduler.start_cinema_sync)`)
- Test: `tests/test_cinema_sync.py`

**Interfaces:**
- Consumes: Tasks 1–4 ; `MediaStore.create_chat_message(..., payload=)`, `MediaStore.get_tmdb_movies`, `MediaStore.upsert_tmdb_movie`, `TMDBClient.search_movie`, `get_movie_details`, `get_director`, `journal_api._movie_from_details`, `french_theatrical_date`.
- Produces:
  ```python
  REUNION = ZoneInfo("Indian/Reunion")
  BOT_ID = "bot:cine"; BOT_NAME = "Ciné"
  def reunion_now() -> datetime            # naïf, heure de La Réunion
  def day_label(value: date) -> str        # "mercredi 2/12"
  def films_payload(films: list[dict]) -> dict   # {"type": "cine_films", "films": [{"site_id", "title", "tracked"}]}
  Fetcher = Callable[[str], Awaitable[str]]
  async def fetch_site_page(path: str) -> str        # http.get_client(), base Config.CINEMA_BASE_URL, User-Agent "Backstage", lève sur statut ≠ 200
  async def match_tmdb(tmdb, title: str, details: FilmDetails) -> Optional[int]
  async def refresh_cinema(store: MediaStore, cinema: CinemaStore, tmdb, fetch: Fetcher, now: datetime) -> dict
      # renvoie {"ok": bool, "films": int, "posted": int}
  async def refresh_tracked_release_dates(store: MediaStore, cinema: CinemaStore, tmdb, today: date, limit: int = 40) -> int
  ```
  `refresh_cinema`, dans l'ordre :
  1. `first_run = (await cinema.get_status())["last_success_at"] is None`.
  2. Lire `GRAND_SUD_PATH` ; exception ou 0 film → `record_failure(now, message)`, renvoyer `{"ok": False, ...}` sans rien modifier d'autre.
  3. Lire `UPCOMING_PATH` ; un échec ici est journalisé et ignoré.
  4. `upsert_site_film` pour chaque film (programmation + prochaines sorties).
  5. Pour chaque film sans `details_fetched_at`, ou dont `release_reunion` manque et `details_fetched_at` a plus de 1 jour : lire sa page, `set_film_details`. Échec d'une page : journalisé, on continue.
  6. Pour chaque film sans `tmdb_id` dont `match_attempted_at` est vide ou a plus de 7 jours : `set_tmdb_match(site_id, await match_tmdb(...), now)`.
  7. `replace_showtimes` avec la programmation.
  8. `compute_reminders` sur les séances de la programmation, `tracked_site_ids` = films dont le `tmdb_id` est dans `tracked_tmdb_ids()`. Pour chaque rappel : si `post`, poster via `store.create_chat_message(BOT_ID, BOT_NAME, None, texte, payload=films_payload([...]))` ; dans tous les cas `record_reminder`.
  9. `record_success(now)`.

  Textes exacts :
  - arrivée : `f"🎬 {title} arrive au Grand Sud : première séance {day_label(first.date())} à {first:%H:%M}."`
  - fin : `f"⏳ Dernières séances de {title} au Grand Sud : jusqu'à {day_label(last.date())}."`

  `match_tmdb` : chercher `details.original_title or title` avec `year=release_national.year` (sans année si inconnue, puis sans année si rien) ; parmi les 5 premiers résultats dont l'année est à ±1, prendre le premier dont le réalisateur TMDB (`get_director(await get_movie_details(id))`) correspond à l'un des `directors` (comparaison sans accents ni casse) ; à défaut, le premier résultat dont l'année est à ±1 ; sinon `None`.

  `refresh_tracked_release_dates` : pour les films suivis du cache dont (`fr_release_date` vide et `fetched_at` > 1 jour) ou (`fetched_at` > 7 jours et `fr_release_date` ≥ aujourd'hui − 30 jours), au plus `limit`, relire `get_movie_details` et `upsert_tmdb_movie(_movie_from_details(...))`. Appelée par la boucle après `refresh_cinema`, même si celle-ci a échoué.

- [ ] **Step 1: Write the failing tests** (fetcher factice qui sert les fixtures par chemin, avec `/film/camembert/16263/` → `film-camembert.html` et toute autre page film → `film-camembert.html` ; `FakeTMDB` avec `search_movie` / `get_movie_details` / `get_director` contrôlables ; `now = datetime(2026, 11, 26, 9, 0)`)

```python
def test_refresh_stores_films_and_showtimes(...):
    result = asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, now))
    assert result["ok"] is True and result["films"] >= 20
    assert asyncio.run(cinema.list_showtimes(now))            # séances enregistrées
    assert asyncio.run(cinema.get_status())["last_success_at"] == now

def test_first_run_posts_nothing_then_new_tracked_film_is_announced(...):
    # 1er passage : aucun message bot ; ajouter tmdb 777 (lié à Camembert) dans une liste
    # avant le 1er passage → il est enregistré "arrivee" sans message.
    # Puis un film suivi qui n'était pas programmé apparaît au 2e passage → un message
    # "🎬 Camembert arrive au Grand Sud : première séance ... à ..." avec payload type "cine_films".

def test_failed_programme_keeps_previous_showtimes(...):
    # 2e passage avec fetcher qui lève, puis avec "<html></html>" : séances inchangées,
    # last_error renseigné, last_success_at inchangé

def test_unmatched_film_is_retried_after_a_week(...):
    # search_movie renvoie [] → tmdb_id None ; nouveau passage à now+1 jour : pas de nouvel appel ; à now+8 jours : nouvel appel

def test_match_prefers_matching_director():
    # deux résultats de la bonne année ; seul le 2e a "Nicolas Slomka" → id du 2e

def test_tracked_release_dates_are_refreshed(...):
    # film suivi en cache sans fr_release_date, fetched_at il y a 2 jours → relu, fr_release_date renseignée
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_sync.py -q`
Expected: FAIL (module absent)

- [ ] **Step 3: Implement** `cinema_sync.py`, la config, la boucle du planificateur et l'appel dans `main.py` (la boucle ne fait rien si `CINEMA_ENABLED` est faux ; `TMDBClient()` qui lève `ValueError` → journaliser et sauter l'association TMDB).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_sync.py tests/test_config.py -q`
Expected: tout passe

- [ ] **Step 5: Commit**

```bash
git add backend/core/cinema_sync.py backend/config.py backend/core/scheduler.py main.py tests/test_cinema_sync.py
git commit -m "Ajoute la synchronisation quotidienne du Ciné Grand Sud"
```

---

### Task 6: Bot `@ciné` et horaires d'un film

**Files:**
- Create: `backend/core/cinema_bot.py`, `backend/cinema_api.py`
- Modify: `backend/api.py` (CRLF : `post_chat_message` appelle le bot après avoir enregistré le message humain ; toute exception du bot est journalisée et avalée), `main.py` (CRLF : inclure `cinema_router`)
- Test: `tests/test_cinema_bot.py`

**Interfaces:**
- Consumes: `CinemaStore`, `reunion_now`, `day_label`, `films_payload`, `BOT_ID`, `BOT_NAME` (Task 5).
- Produces:
  ```python
  # cinema_bot.py
  STALE_AFTER = timedelta(days=2)
  COMMANDS = [
      ("@ciné films", "Les films à l'affiche : clique sur un titre pour voir ses horaires."),
      ("@ciné ce soir", "Les séances d'aujourd'hui qui n'ont pas encore commencé."),
      ("@ciné demain", "Les séances de demain."),
      ("@ciné aide", "Cette liste de commandes."),
  ]
  def parse_command(body: str) -> Optional[str]   # None si le message ne commence pas par @ciné/@cine ; sinon "films" | "ce soir" | "demain" | "aide"
  async def build_reply(command: str, cinema: CinemaStore, now: datetime) -> tuple[str, Optional[dict]]
  async def handle_chat_message(body: str, store: MediaStore, now: Optional[datetime] = None) -> Optional[dict]   # message bot créé ou None
  async def film_showtimes(cinema: CinemaStore, site_id: int, now: datetime) -> Optional[dict]
  # cinema_api.py
  cinema_router = APIRouter(prefix="/api/cinema", tags=["cinema"], dependencies=[Depends(get_current_user)])
  GET /api/cinema/films/{site_id}/showtimes -> film_showtimes(...) ou 404 « Film inconnu »
  ```
  `parse_command` : insensible à la casse et aux espaces ; `@ciné` seul ou argument inconnu → `"aide"` ; `soir` et `ce soir` → `"ce soir"`.
  `build_reply` :
  - données périmées (`last_success_at` absent → `"Horaires pas encore disponibles."` ; plus de 2 jours → `f"Horaires indisponibles depuis le {d:%d/%m}."`), payload `None` — sauf pour `aide`, qui répond toujours.
  - `films` : films ayant une séance ≥ `now`, par ordre alphabétique ; corps `"À l'affiche au Grand Sud :"`, payload `films_payload` avec `tracked` vrai si le `tmdb_id` est dans les listes ; aucun → `"Aucune séance à venir au Grand Sud."`.
  - `ce soir` : séances d'aujourd'hui ≥ `now` ; `demain` : séances du lendemain. Corps : en-tête (`"Ce soir au Grand Sud :"` / `f"Demain ({day_label}) au Grand Sud :"`) puis une ligne par film `f"• {title} : 17:20 VF, 20:00 VOST"` ; payload `films_payload` des mêmes films. Aucun → `"Plus de séance ce soir au Grand Sud."` / `"Aucune séance demain au Grand Sud."`.
  - `aide` : corps `"Commandes du bot Ciné :"`, payload `{"type": "cine_help", "commands": [{"command", "description"} ...]}`.
  `film_showtimes` → `{"site_id", "title", "stale": bool, "days": [{"date": "2026-12-16", "label": "mercredi 16/12", "showtimes": [{"time": "20:00", "version": "VF 3D", "booking_url": ...}]}]}` (séances ≥ `now` seulement) ; `None` si film inconnu.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("body,expected", [
    ("@ciné films", "films"), ("@CINE  films ", "films"), ("@ciné ce soir", "ce soir"), ("@cine soir", "ce soir"),
    ("@ciné demain", "demain"), ("@ciné", "aide"), ("@ciné n'importe quoi", "aide"),
    ("salut @ciné films", None), ("@cinéma", None), ("bonjour", None),
])
def test_parse_command(body, expected): ...

def test_films_reply_lists_upcoming_films_with_tracked_flag(...): ...
def test_tonight_skips_showtimes_already_started(...):
    # now 18:00 heure Réunion ; séances 17:20 et 20:00 → seule 20:00 dans le corps
def test_stale_data_is_announced_instead_of_showtimes(...):
    # last_success_at = now - 3 jours → "Horaires indisponibles depuis le 23/11."
def test_help_answers_even_when_stale(...): ...
def test_film_without_tmdb_match_still_listed(...): ...
def test_posting_a_command_adds_a_bot_reply(client):
    # POST /api/chat/messages {"body": "@ciné aide"} → 2 messages listés, le 2e d'auteur "bot:cine" avec payload cine_help
def test_bot_failure_does_not_lose_the_message(client, monkeypatch):
    # build_reply lève → POST renvoie 200 avec le message humain, 1 seul message listé
def test_film_showtimes_route(client):
    # séances passée/à venir → seule la future ; film inconnu → 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_bot.py -q`
Expected: FAIL (module absent)

- [ ] **Step 3: Implement** `cinema_bot.py`, la route, le branchement dans `post_chat_message` (la réponse HTTP reste le message humain, forme inchangée) et l'inclusion du routeur.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cinema_bot.py tests/test_chat.py -q`
Expected: tout passe

- [ ] **Step 5: Commit**

```bash
git add backend/core/cinema_bot.py backend/cinema_api.py backend/api.py main.py tests/test_cinema_bot.py
git commit -m "Ajoute le bot @ciné dans le salon"
```

---

### Task 7: Agenda ICS

**Files:**
- Create: `backend/core/ics.py`
- Modify: `backend/cinema_api.py` (routes agenda + `calendar_feed_router` public), `main.py` (CRLF : inclure `calendar_feed_router`)
- Test: `tests/test_ics.py`, `tests/test_cinema_calendar.py`

**Interfaces:**
- Consumes: `CinemaStore` (jetons, films du site, `tracked_tmdb_ids`), `MediaStore.get_tmdb_movies` (`title`, `fr_release_date`), `Config.BACKSTAGE_PUBLIC_URL`.
- Produces:
  ```python
  # ics.py
  @dataclass(frozen=True)
  class CalendarEvent: uid: str; day: date; summary: str; description: str
  def build_calendar(events: list[CalendarEvent], now: datetime) -> str
  # cinema_api.py
  async def calendar_events(store: MediaStore, cinema: CinemaStore, today: date) -> list[CalendarEvent]
  GET  /api/cinema/calendar             -> {"url": ...}   (crée le jeton s'il n'existe pas ; secrets.token_urlsafe(32))
  POST /api/cinema/calendar/regenerate  -> {"url": ...}
  calendar_feed_router = APIRouter(prefix="/api/cinema", tags=["cinema"])   # sans dépendance d'auth
  GET  /api/cinema/agenda.ics?token=... -> text/calendar ; jeton absent/inconnu → 404
  ```
  URL : `f"{Config.BACKSTAGE_PUBLIC_URL.rstrip('/')}/api/cinema/agenda.ics?token={token}"`.
  `calendar_events` : pour chaque `tmdb_id` suivi ; date = `release_reunion` d'un film du site lié à ce `tmdb_id` s'il en a une (description `"Au Grand Sud"`), sinon `fr_release_date` du cache (description `"Date France, à confirmer pour La Réunion"`) ; sans date → pas d'événement ; date < `today - 365 jours` → pas d'événement. `uid = f"backstage-cinema-{tmdb_id}@backstage"`, `summary = f"🎬 {title} — sortie au cinéma"`. Tri par date.
  `build_calendar` : `BEGIN:VCALENDAR`, `VERSION:2.0`, `PRODID:-//Backstage//Cinema//FR`, `CALSCALE:GREGORIAN`, `X-WR-CALNAME:Backstage — Sorties ciné` ; par événement `UID`, `DTSTAMP` (UTC `YYYYMMDDTHHMMSSZ`), `DTSTART;VALUE=DATE`, `DTEND;VALUE=DATE` (lendemain), `SUMMARY`, `DESCRIPTION`, `TRANSP:TRANSPARENT`. Échapper `\`, `;`, `,`, retours à la ligne ; replier à 75 octets UTF-8 sans couper un caractère (continuation = CRLF + espace) ; toutes les lignes en CRLF, y compris la dernière.

- [ ] **Step 1: Write the failing tests**

```python
def test_calendar_is_crlf_folded_and_escaped():
    text = build_calendar([CalendarEvent("u1@b", date(2026, 12, 16), "🎬 Dune; partie 3, " + "é" * 60, "Au Grand Sud")], datetime(2026, 11, 26, tzinfo=timezone.utc))
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "DTSTART;VALUE=DATE:20261216" in text and "DTEND;VALUE=DATE:20261217" in text
    assert "Dune\\; partie 3\\," in text.replace("\r\n ", "")

def test_feed_uses_reunion_date_then_french_date(client): ...
    # 550 dans une liste avec fr_release_date 2026-12-20 ; film du site lié à 550 avec release_reunion 2026-12-16
    # → un VEVENT au 20261216 "Au Grand Sud" ; sans film du site → 20261220 "Date France, à confirmer pour La Réunion"
def test_feed_skips_films_without_date_or_older_than_a_year(client): ...
def test_calendar_url_is_stable_until_regenerated(client): ...
    # GET deux fois → même url ; POST regenerate → nouvelle url ; l'ancienne → 404
def test_feed_rejects_unknown_or_missing_token(client):
    # sans session : ?token=nimporte → 404 ; sans paramètre token → 404 (déclarer token: str = "" pour éviter le 422 de FastAPI)
def test_feed_works_without_session(client): ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ics.py tests/test_cinema_calendar.py -q`
Expected: FAIL (modules/routes absents)

- [ ] **Step 3: Implement** `ics.py`, `calendar_events`, les trois routes et l'inclusion du routeur public.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ics.py tests/test_cinema_calendar.py -q`
Expected: tout passe

- [ ] **Step 5: Commit**

```bash
git add backend/core/ics.py backend/cinema_api.py main.py tests/test_ics.py tests/test_cinema_calendar.py
git commit -m "Ajoute l'agenda ICS des sorties ciné"
```

---

### Task 8: Interface (tchat et page Listes)

**Files:**
- Create: `proto-ui/src/cinema.js`, `proto-ui/src/cinema.test.js`
- Modify: `proto-ui/package.json` (ajouter `src/cinema.test.js` au script `test`), `proto-ui/src/api.js` (CRLF : `fetchFilmShowtimes(siteId)`, `fetchCalendarUrl()`, `regenerateCalendarUrl()`), `proto-ui/src/components/ChatDock.jsx`, `proto-ui/src/components/ListsView.jsx`

**Interfaces:**
- Consumes: routes des Tasks 6 et 7 ; `message.payload` (Task 2).
- Produces (`cinema.js`, pur) :
  ```js
  export const CINE_COMMANDS   // [{command:'@ciné films', description:'…'}, …] — mêmes 4 entrées et textes que COMMANDS (Task 6)
  export function isBotMessage(message)          // message.author.id === 'bot:cine'
  export function filmButtons(payload)           // payload?.type === 'cine_films' ? payload.films : []
  export function helpCommands(payload)          // payload?.type === 'cine_help' ? payload.commands : []
  export function showtimeLine(showtime)         // "20:00 · VF 3D"
  ```
  Comportement :
  - Message du bot : avatar 🎬, nom « Ciné ». Sous le texte, un bouton par film de `filmButtons` (★ devant si `tracked`). Un clic charge `fetchFilmShowtimes` et affiche, sous ce message et pour cet utilisateur seulement, les jours (`label`) avec leurs séances (`showtimeLine`, lien 🎟 vers `booking_url` en `target="_blank" rel="noopener noreferrer"`) ; re-clic → replie ; `stale` → « Horaires indisponibles » ; erreur → « Horaires indisponibles pour le moment ». Pour `cine_help`, chaque commande est un bouton qui la met dans la zone de saisie.
  - Bouton 🎬 à côté du bouton emoji : ouvre un petit panneau listant `CINE_COMMANDS` (commande + description) ; un clic met la commande dans la zone de saisie, ferme le panneau et donne le focus.
  - Après l'envoi d'un message commençant par `@ciné`/`@cine`, relancer immédiatement la récupération des nouveaux messages (la réponse du bot arrive sans attendre l'intervalle).
  - `ListsView.jsx` : bouton « Ajouter à mon agenda » en tête de page ; il ouvre un encart avec l'adresse (champ en lecture seule), « Copier » (`navigator.clipboard.writeText`, repli : sélectionner le texte), « Régénérer » (confirmation « L'ancienne adresse cessera de fonctionner. ») et une phrase : « Abonne-toi à cette adresse dans Google Agenda ou le calendrier de ton téléphone : les dates de sortie des films de vos listes y apparaissent. »

- [ ] **Step 1: Write the failing tests** (`proto-ui/src/cinema.test.js`, style des tests existants avec `node:test` et `assert`)

```js
test('reconnaît les messages du bot', () => { assert.equal(isBotMessage({author:{id:'bot:cine'}}), true); assert.equal(isBotMessage({author:{id:'hugo'}}), false); });
test('extrait les boutons de films', () => { assert.deepEqual(filmButtons({type:'cine_films', films:[{site_id:1,title:'Dune',tracked:true}]}), [{site_id:1,title:'Dune',tracked:true}]); assert.deepEqual(filmButtons(null), []); assert.deepEqual(filmButtons({type:'cine_help'}), []); });
test("extrait les commandes d'aide", () => { assert.equal(helpCommands({type:'cine_help', commands:[{command:'@ciné films'}]}).length, 1); assert.deepEqual(helpCommands(undefined), []); });
test('formate une séance', () => { assert.equal(showtimeLine({time:'20:00', version:'VF 3D'}), '20:00 · VF 3D'); });
test("l'aide liste les quatre commandes", () => { assert.deepEqual(CINE_COMMANDS.map(c => c.command), ['@ciné films','@ciné ce soir','@ciné demain','@ciné aide']); });
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm --prefix proto-ui test`
Expected: FAIL (module `cinema.js` absent)

- [ ] **Step 3: Implement** `cinema.js`, les fonctions d'API, `ChatDock.jsx` et `ListsView.jsx` dans le style visuel existant (classes Tailwind du tchat, mode sombre via `isDarkMode`).

- [ ] **Step 4: Run tests and build**

Run: `npm --prefix proto-ui test` puis `npm --prefix proto-ui run build`
Expected: tous les tests passent ; build sans erreur

- [ ] **Step 5: Commit**

```bash
git add proto-ui/src/cinema.js proto-ui/src/cinema.test.js proto-ui/package.json proto-ui/src/api.js proto-ui/src/components/ChatDock.jsx proto-ui/src/components/ListsView.jsx
git commit -m "Ajoute les boutons du bot ciné et l'abonnement à l'agenda"
```

---

### Task 9: Vérification de bout en bout dans le bac à sable

**Files:** aucun fichier du dépôt (scripts dans le scratchpad).

- [ ] **Step 1: Suite complète**

Run: `.venv/Scripts/python.exe -m pytest -q` puis `npm --prefix proto-ui test`
Expected: seuls les 11 échecs préexistants ; interface verte.

- [ ] **Step 2: Bac à sable** — copie de la base, port 8091, intégrations sur `127.0.0.1:9`, et un petit serveur statique local (scratchpad) qui sert les fixtures aux chemins du site (`/programmation/multiplexe-cine-grand-sud-saint-pierre/`, `/films/prochaines-sorties/`, `/film/<slug>/<id>/`) ; `CINEMA_BASE_URL` pointé dessus. Ne jamais lancer `preview_start` par nom ; ouvrir par URL `http://localhost:8091`.

- [ ] **Step 3: Parcours manuel** — dans le salon : `@ciné aide`, `@ciné films` (boutons, clic → horaires sous le message, liens 🎟), `@ciné demain`, bouton 🎬 → commande dans la zone de saisie ; page Listes : « Ajouter à mon agenda », copier l'adresse, ouvrir l'ICS dans un nouvel onglet sans session → fichier valide. Capture d'écran du tchat avec horaires dépliés.
Expected: tout fonctionne ; aucune erreur dans la console ni dans les journaux du serveur.
