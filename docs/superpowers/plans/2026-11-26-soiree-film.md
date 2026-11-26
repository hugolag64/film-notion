# Soirée film Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une soirée film collective jouée dans le salon : on la lance (Coloc ou Ciné ce soir), chacun rejoint et répond depuis son téléphone, Backstage propose 3 films adaptés à tous, le groupe vote à la majorité.

**Architecture:** Une soirée est un état en base (`parties`, membres, propositions, votes) piloté par un service. Le bot « Soirée » poste dans le salon un message dont le `payload` porte l'id de la soirée ; la carte React relit l'état de la soirée toutes les 3 s tant qu'elle est active. Les candidats viennent des séances du Grand Sud (mode Ciné) ou de TMDB + la bibliothèque (mode Coloc), classés par le profil de goûts moyen des partants, puis Gemini en choisit 3.

**Tech Stack:** FastAPI, SQLite (`MediaStore` + store dédié comme `CinemaStore`), httpx/TMDB, passerelle Gemini existante, React (`proto-ui`), `node --test`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-soiree-film-design.md`

## Global Constraints

- Les journaux restent privés : aucune réponse d'API ni message du bot ne dit qui a vu un film ou qui a répondu quoi.
- Pas de veto : score = 👍 − 👎, majorité ; égalité → le film au meilleur rang (rang 1 = premier choix de Gemini).
- Une seule soirée active (`joining` ou `voting`) à la fois ; expiration 3 h après la création.
- Questions : humeur `light` « Léger », `intense` « Intense », `any` « Peu importe » ; durée max `105` « 1 h 45 », `135` « 2 h 15 », `any` « Peu importe » ; en mode Coloc seulement, époque `recent` « Plutôt récent », `classic` « Plutôt classique », `any` « Peu importe ».
- Combinaison : durée = la plus courte demandée ; humeur et époque = réponse majoritaire hors `any` (égalité ou aucune → `any`).
- Films vus par au moins un partant exclus en mode Coloc uniquement.
- Les soirées ne consomment pas le quota individuel de recommandations.
- Tests sans réseau : TMDB, Gemini et le site du ciné sont simulés.
- Fichiers CRLF (à éditer par script Python qui préserve `\r\n`) : `backend/api.py`, `backend/core/store.py`, `backend/config.py`, `main.py`, `proto-ui/src/api.js`. Les fichiers nouveaux sont LF.
- Python : `.venv/Scripts/python.exe -m pytest` (dans un worktree : `../../.venv/Scripts/python.exe`). Seuls les 11 échecs préexistants sont tolérés (`test_auth_api` ×8, `test_auth_store` ×2, `test_catalogue_playback_ui` ×1).
- UI : `npm --prefix proto-ui test` et `npm --prefix proto-ui run build`.

## Review Focus

- Deux partants cliquent « On lance » ou votent en même temps : pas de double jeu de propositions ni de vote compté deux fois (Task 1 : clé primaire des votes ; Task 4 : `launch` refusé si le statut n'est plus `joining`).
- Un membre qui n'est pas partant appelle `vote`/`answer` sur une soirée : refusé (Task 4).
- TMDB ou Gemini en panne au moment du lancement : la soirée propose quand même (classement local) ou se termine proprement en `empty` avec un message du bot (Task 3, Task 4).
- Une soirée oubliée : après 3 h, elle est `expired`, on peut en relancer une (Task 2, Task 4).
- La réponse d'état ne contient aucun nom associé à un film vu ni les réponses individuelles (Task 4 : test dédié).

---

### Task 1: Tables et `PartyStore`

**Files:**
- Create: `backend/core/party_store.py`
- Modify: `backend/core/store.py` (`init_schema` appelle `create_party_tables(conn)`, comme `create_cinema_tables`) — CRLF
- Test: `tests/test_party_store.py`

**Interfaces:**
- Produces:
  - `create_party_tables(conn: sqlite3.Connection) -> None` — tables :
    - `parties(id TEXT PK, mode TEXT, status TEXT, starter_id TEXT, starter_name TEXT, created_at TEXT, launched_at TEXT, closed_at TEXT, winner_tmdb_id INTEGER, message_id INTEGER)` ; `status ∈ {joining, voting, done, empty, expired}`.
    - `party_members(party_id, user_id, display_name, answers TEXT JSON NULL, late INTEGER DEFAULT 0, joined_at TEXT, PK(party_id,user_id))`.
    - `party_proposals(party_id, rank INTEGER, tmdb_id INTEGER NULL, title, poster_url, reason, source TEXT ∈ {server, tmdb, cinema}, site_id INTEGER NULL, showtime TEXT JSON NULL, PK(party_id, rank))`.
    - `party_votes(party_id, user_id, rank INTEGER, value INTEGER ∈ {1,-1}, PK(party_id,user_id,rank))`.
  - `class PartyStore(db_path)` avec méthodes async (enveloppes `asyncio.to_thread` de `_..._sync`, même style que `CinemaStore`) :
    - `create_party(party_id, mode, starter_id, starter_name, created_at) -> None`
    - `get_party(party_id) -> dict | None` (dates en `datetime`)
    - `active_party() -> dict | None` (statut `joining`/`voting`, la plus récente)
    - `set_status(party_id, status, *, at: datetime | None = None, winner_tmdb_id: int | None = None) -> bool` — `UPDATE … WHERE id=? AND status IN (joining, voting)` ; renvoie si une ligne a changé. `voting` remplit `launched_at`, `done/empty/expired` remplissent `closed_at`.
    - `set_message_id(party_id, message_id) -> None`
    - `add_member(party_id, user_id, display_name, joined_at, late: bool) -> None` (idempotent : `INSERT OR IGNORE`)
    - `set_answers(party_id, user_id, answers: dict) -> None`
    - `list_members(party_id) -> list[dict]` (`answers` décodé ou `None`)
    - `replace_proposals(party_id, proposals: list[dict]) -> None` (dicts aux clés des colonnes, `showtime` dict ou `None`)
    - `list_proposals(party_id) -> list[dict]` triés par `rank`
    - `set_vote(party_id, user_id, rank, value) -> None` (`INSERT OR REPLACE`)
    - `list_votes(party_id) -> list[dict]`

- [ ] **Step 1: Write the failing tests** — `tests/test_party_store.py` avec un `MediaStore(tmp_path/"p.db")` + `init_schema()` puis `PartyStore(store.db_path)` :
  - `test_init_schema_creates_party_tables` : les 4 tables existent dans `sqlite_master`.
  - `test_active_party_ignores_finished_ones` : une soirée `done` puis une `joining` → `active_party()["id"]` est la seconde ; après `set_status(.., "expired")` → `None`.
  - `test_set_status_only_moves_active_parties` : `set_status("p","voting")` → `True` ; `set_status("p","done", winner_tmdb_id=7)` → `True`, `winner_tmdb_id == 7`, `closed_at` non nul ; un second `set_status("p","voting")` → `False`.
  - `test_add_member_twice_keeps_one_row` et `test_answers_round_trip` (`{"mood":"light","runtime":"105"}`).
  - `test_vote_replaces_previous_value` : `set_vote(p,"hugo",1,1)` puis `set_vote(p,"hugo",1,-1)` → une seule ligne, `value == -1`.
  - `test_proposals_round_trip_with_showtime` : `showtime={"time":"20:15","version":"VF","booking_url":"https://x"}` relu identique, ordre par `rank`.
- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_party_store.py -q` — Expected: FAIL (`ModuleNotFoundError: backend.core.party_store`).
- [ ] **Step 3: Implement** `backend/core/party_store.py` et l'appel dans `MediaStore.init_schema` (script Python qui préserve CRLF).
- [ ] **Step 4: Run** le même test — Expected: PASS.
- [ ] **Step 5: Commit** `git add backend/core/party_store.py backend/core/store.py tests/test_party_store.py && git commit -m "Ajoute les tables de la soirée film"`

### Task 2: Règles pures de la soirée

**Files:**
- Create: `backend/core/party_logic.py`
- Test: `tests/test_party_logic.py`

**Interfaces:**
- Produces:
  - `PARTY_TTL = timedelta(hours=3)`
  - `QUESTIONS: dict[str, list[dict]]` — `{"coloc": [mood, runtime, era], "cinema": [mood, runtime]}` ; chaque question `{"key": "mood"|"runtime"|"era", "label": str, "options": [{"value": str, "label": str}]}` avec les valeurs et libellés des Global Constraints ; libellés des questions : « Quelle humeur ? », « Combien de temps ? », « Quelle époque ? ».
  - `validate_answers(mode: str, answers: dict) -> dict` — renvoie un dict ne contenant que les clés de `QUESTIONS[mode]`, chacune avec une valeur permise ; lève `ValueError` sinon (clé manquante ou valeur inconnue).
  - `combine_answers(answers: list[dict]) -> dict` — `{"mood": "light"|"intense"|"any", "runtime_max": int | None, "era": "recent"|"classic"|"any"}` selon les règles des Global Constraints.
  - `average_profiles(profiles: list[TasteProfile]) -> TasteProfile` — moyenne clé par clé des quatre dictionnaires d'affinités (clé absente = 0), `confidence` moyenne, `preferred_runtime_minutes=None` ; liste vide → `TasteProfile()`.
  - `tally(proposals: list[dict], votes: list[dict]) -> dict` — `{"scores": {rank: {"up": n, "down": n}}, "winner_rank": int | None}` ; gagnant = score `up-down` max, égalité → plus petit `rank` ; aucune proposition → `None`.
  - `is_expired(party: dict, now: datetime) -> bool` — statut actif et `now - created_at >= PARTY_TTL`.

- [ ] **Step 1: Write the failing tests** — `tests/test_party_logic.py` :
  - `test_validate_answers_rejects_unknown_value` (`{"mood":"sad","runtime":"any"}` → `ValueError`) et `test_validate_answers_cinema_ignores_era` (`era` absent accepté en `cinema`, `era` présent retiré du résultat).
  - `test_combine_takes_shortest_runtime` : runtimes `135`, `105`, `any` → `runtime_max == 105` ; tous `any` → `None`.
  - `test_combine_mood_majority_ignores_any` : `light, light, intense, any` → `light` ; `light, intense` → `any`.
  - `test_average_profiles_fills_missing_keys_with_zero` : `{"Comédie": 1.0}` et `{"Drame": 0.5}` → `{"Comédie": 0.5, "Drame": 0.25}`.
  - `test_tally_majority_wins_without_veto` : rang 1 = 2 👍 + 1 👎, rang 2 = 1 👍 → gagnant 1.
  - `test_tally_tie_goes_to_best_rank` : rangs 2 et 3 à +1, rang 1 à −1 → gagnant 2.
  - `test_is_expired_after_three_hours` : créée à 18:00, `now` 20:59 → `False`, 21:00 → `True` ; statut `done` → `False`.
- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_party_logic.py -q` — Expected: FAIL (module absent).
- [ ] **Step 3: Implement** `backend/core/party_logic.py`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Ajoute les règles de vote et de combinaison de la soirée"`

### Task 3: Candidats et choix des 3 films

**Files:**
- Create: `backend/core/party_candidates.py`
- Modify: `backend/core/gemini_recommendations.py` (méthode `select_group`)
- Test: `tests/test_party_candidates.py`, ajout dans `tests/test_gemini_recommendations.py`

**Interfaces:**
- Consumes: `combine_answers` (Task 2), `TasteProfile`, `score_recommendation_candidate`, `GENRE_IDS`, `TMDB_GENRE_NAMES` (`backend/core/recommendations.py`), `CinemaStore.get_site_films()` / `list_showtimes(start, end)`, `MediaStore.fetch_all()`, `TMDBClient.discover_movies(...)` / `get_movie_details(tmdb_id)`.
- Produces:
  - `GeminiRecommendationGateway.select_group(profile: dict, combined: dict, candidates: list[dict]) -> GeminiGroupPick | None` ; `class GeminiGroupPick(BaseModel): picks: list[dict]  # [{"tmdb_id": int, "reason": str}]`, `usage: dict`. Instruction : « Choisis exactement 3 films différents parmi candidates pour un groupe d'amis. Pour chacun, une raison courte qui parle du groupe, jamais d'une personne. » Ids validés avec `_validate_id` ; doublons retirés ; `None` si désactivée.
  - `TOP_N = 15`
  - `async def cinema_candidates(cinema: CinemaStore, tmdb, profile: TasteProfile, combined: dict, now: datetime) -> list[dict]` — films avec au moins une séance entre `now` et minuit (heure de La Réunion, `now` déjà local), dans l'ordre du score. Pour chaque film avec `tmdb_id`, `tmdb.get_movie_details` donne `runtime` et `genres` ; film écarté si `runtime` connu > `runtime_max`. Film sans `tmdb_id` ou détails en erreur : gardé, score 0. Chaque dict : `{"tmdb_id", "title", "poster_url", "source": "cinema", "site_id", "showtime": {"time","version","booking_url"} (prochaine séance), "genre_ids", "overview", "score"}`.
  - `async def coloc_candidates(store: MediaStore, tmdb, profile: TasteProfile, combined: dict, seen_tmdb_ids: set[int], now: datetime) -> list[dict]` — TMDB `discover_movies(page=1, min_vote_count=50, with_genres=<genres de MOOD_GENRES[mood] si mood != any>, runtime_max=…, release_date_gte/lte selon l'époque (récent = `now.year-6`-01-01, classique ≤ 2005-12-31), release_date_lte=today)` + films de la bibliothèque (`type == "Film"`, `tmdb_id` non nul, genres depuis `categories` via `GENRE_IDS`). Union par `tmdb_id` (la version bibliothèque gagne, `source="server"`, sinon `"tmdb"`), exclusion de `seen_tmdb_ids`, score `score_recommendation_candidate(c, profile, {"mood": mood}, None, now).score`, tri décroissant. Erreur TMDB (`ValueError`, `httpx.HTTPError`) → seulement la bibliothèque.
  - `def pick_three(candidates: list[dict], pick: GeminiGroupPick | None) -> list[dict]` — parmi les `TOP_N` premiers : si `pick` a 3 ids valides, ces 3 dans l'ordre de Gemini avec `reason` ; sinon les 3 premiers avec `reason=""`. En Coloc, si aucun des 3 n'est `server` mais qu'un `server` est dans le top 15, il remplace le 3ᵉ. Ajoute `rank` 1..3. Moins de 3 candidats → tous.

- [ ] **Step 1: Write the failing tests** — `tests/test_party_candidates.py` avec un `FakeTMDB` (méthodes async `discover_movies(**kw)` qui enregistre `kw` et renvoie une liste fixe, `get_movie_details(id)` qui renvoie `{"runtime": …, "genres": [{"id":35}]}` ou lève `httpx.HTTPError`) et des séances insérées via `CinemaStore.upsert_site_film`/`replace_showtimes` :
  - `test_cinema_keeps_only_tonight_after_now` : séances 14:00 et 20:15 aujourd'hui, 18:00 demain, `now` = 17:00 → un candidat avec `showtime.time == "20:15"`.
  - `test_cinema_drops_film_longer_than_runtime_max` : runtime 150, `runtime_max` 135 → écarté ; runtime inconnu (détails en erreur) → gardé.
  - `test_coloc_excludes_seen_and_marks_server_films` : un film de la bibliothèque `tmdb_id=1` → `source=="server"` ; `seen_tmdb_ids={2}` → 2 absent.
  - `test_coloc_passes_mood_and_era_to_discover` : `mood=light`, `era=classic` → `with_genres` contient 35, `release_date_lte == "2005-12-31"`.
  - `test_coloc_survives_tmdb_failure` : `discover_movies` lève `httpx.ConnectError` → seuls les films de la bibliothèque.
  - `test_pick_three_follows_gemini_order` et `test_pick_three_without_gemini_takes_top_three` ; `test_pick_three_keeps_one_server_film` (top 3 tous `tmdb`, un `server` 5ᵉ → il devient rang 3).
  - Dans `tests/test_gemini_recommendations.py` : `test_select_group_returns_three_distinct_valid_ids` avec le faux client existant du fichier (réponse JSON contenant un id inconnu et un doublon → filtrés) et `test_select_group_disabled_returns_none`.
- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_party_candidates.py tests/test_gemini_recommendations.py -q` — Expected: FAIL (module absent / attribut `select_group` absent).
- [ ] **Step 3: Implement** `select_group` puis `backend/core/party_candidates.py`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Choisit les films proposés à la soirée"`

### Task 4: Service de soirée, bot et routes

**Files:**
- Create: `backend/core/party_service.py`, `backend/party_api.py`
- Modify: `backend/api.py` (`post_chat_message` appelle aussi `party_service.handle_chat_message`, dans son propre try/except qui logue) — CRLF ; `main.py` (inclut `party_router`) — CRLF
- Test: `tests/test_party_service.py`, `tests/test_party_api.py`

**Interfaces:**
- Consumes: Tasks 1–3, `MediaStore.create_chat_message(author_id, name, avatar, body, payload=…)`, `reunion_now()`, `build_taste_profile` (comme `_recommendation_profile` dans `backend/api.py`), `MediaStore.list_user_media_states`, `list_diary_tmdb_ids`, le calcul « vu » de `_recommendation_pool` (statut Terminé/Terminée ou note).
- Produces:
  - `BOT_ID = "bot:soiree"`, `BOT_NAME = "Soirée"`.
  - `class PartyError(Exception)` avec `status: int` (409 conflit d'état, 403 pas partant / pas le lanceur, 404 inconnue, 422 réponses invalides).
  - `def default_gateway() -> GeminiRecommendationGateway` — `GeminiRecommendationGateway(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)` (pas d'import de `backend.api`, pour éviter un import circulaire).
  - `class PartyService(store: MediaStore, *, tmdb_factory=TMDBClient, gateway_factory=default_gateway, clock=reunion_now)` :
    - `async start(user: dict, mode: str) -> dict` — refuse (409, « Une soirée est déjà en cours. ») si `active_party()` non expirée (une soirée expirée trouvée est passée `expired`) ; crée la soirée, ajoute le lanceur comme membre, poste le message du bot `"🍿 {nom} lance une soirée {Coloc|ciné} ! Qui est partant ?"` avec `payload={"type": "party", "party_id": id}`, enregistre `message_id`, renvoie `state(...)`.
    - `async join(party_id, user) -> dict` — `late = status == "voting"`.
    - `async answer(party_id, user, answers) -> dict` — membre requis, statut `joining`, `validate_answers`.
    - `async launch(party_id, user) -> dict` — lanceur seulement ; passe d'abord `joining → voting` via `set_status` (si `False` → 409) ; calcule profils (membres ayant répondu, sinon tous), `combine_answers`, candidats (Ciné : `cinema_candidates` ; Coloc : `coloc_candidates` avec l'union des films vus des membres), `select_group` dans `asyncio.to_thread` (exception → `None`), `pick_three`. Aucun candidat → statut `empty` et bot : Ciné « Plus de séance ce soir au Grand Sud qui vous convienne. », Coloc « Pas de film trouvé pour ce soir. ».
    - `async vote(party_id, user, rank, value) -> dict` — membre requis, statut `voting`, `value ∈ {1,-1}`, `rank` existant ; si chaque membre a voté sur chaque proposition → `close`.
    - `async close(party_id, user | None) -> dict` — lanceur seulement quand `user` est donné ; `tally` ; statut `done` + `winner_tmdb_id` ; bot : `"🏆 Ce soir : {titre}"` (+ `" à {heure}"` en Ciné).
    - `async state(party_id, viewer_id) -> dict` — passe la soirée en `expired` si `is_expired` ; renvoie `{"id","mode","status","starter":{"id","name"},"questions": QUESTIONS[mode], "members":[{"name","answered": bool,"late": bool}], "me": {"member": bool, "answered": bool, "votes": {rank: value}}, "proposals":[{rank,tmdb_id,title,poster_url,reason,source,showtime}], "scores": {rank: {"up","down"}}, "winner_rank", "expires_at"}`. Pas d'`answers` individuelles, pas d'ids d'utilisateurs autres que le lanceur.
    - `async handle_chat_message(body, user) -> dict | None` — `@soirée` / `@soiree` (accents et casse ignorés) : `coloc` ou `ciné|cine` → `start` ; autre / vide → message d'aide du bot `"Lance une soirée :"` avec `payload={"type": "cine_help", "commands": [{"command": "@soirée coloc", "description": "Un film à la coloc, sur le serveur ou à demander."}, {"command": "@soirée ciné", "description": "Une séance ce soir au Grand Sud."}]}` (réutilise l'affichage d'aide existant). `PartyError` sur `start` → message du bot avec le texte de l'erreur.
  - Routes `backend/party_api.py`, `party_router = APIRouter(prefix="/api/parties", dependencies=[Depends(get_current_user)])` ; chaque route traduit `PartyError` en `HTTPException(status, detail)` :
    - `POST /api/parties` `{mode: "coloc"|"cinema"}` · `GET /api/parties/{id}` · `POST /{id}/join` · `POST /{id}/answers` `{answers: {...}}` · `POST /{id}/launch` · `POST /{id}/votes` `{rank: int, value: 1|-1}` · `POST /{id}/close`.

- [ ] **Step 1: Write the failing tests** — `tests/test_party_service.py` (store `tmp_path`, `FakeTMDB` de Task 3, faux gateway activé ou désactivé, `clock` fixe) :
  - `test_start_posts_bot_card_and_joins_starter` : message `author.id == "bot:soiree"`, `payload == {"type":"party","party_id": id}`, `members == [{"name":"Hugo","answered":False,"late":False}]`.
  - `test_second_party_refused_while_one_is_active` (409) et `test_expired_party_does_not_block_a_new_one` (clock + 3 h).
  - `test_only_starter_can_launch_and_close` (403).
  - `test_launch_twice_is_refused` (409 au second).
  - `test_non_member_cannot_vote_or_answer` (403).
  - `test_late_member_can_vote_and_is_flagged_late`.
  - `test_all_votes_close_the_party_with_majority_winner` : 3 membres, rang 2 majoritaire → `status=="done"`, `winner_rank==2`, dernier message du bot commence par « 🏆 Ce soir : ».
  - `test_coloc_excludes_films_seen_by_any_member` : film 5 dans le journal de Léa → absent des propositions.
  - `test_cinema_without_showtime_ends_empty_with_bot_message`.
  - `test_gemini_failure_falls_back_to_local_ranking` (gateway qui lève → 3 propositions, `reason == ""`).
  - `test_state_never_exposes_answers_or_member_ids` : `json.dumps(state)` ne contient ni `"light"` (réponse donnée) ni l'id d'un membre non lanceur.
  - `test_chat_command_starts_coloc_party_and_help_without_argument`.
  - `tests/test_party_api.py` : `test_routes_map_party_errors_to_http_status` (409 au second `POST /api/parties`, 404 sur id inconnu) en appelant les fonctions de route comme `tests/test_chat.py`.
- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_party_service.py tests/test_party_api.py -q` — Expected: FAIL (module absent).
- [ ] **Step 3: Implement** `party_service.py`, `party_api.py`, le branchement dans `post_chat_message` et `main.py`.
- [ ] **Step 4: Run** ces tests puis toute la suite — Expected: PASS, seuls les 11 échecs connus.
- [ ] **Step 5: Commit** `git commit -m "Ajoute le service et les routes de la soirée film"`

### Task 5: Carte de soirée dans le salon

**Files:**
- Create: `proto-ui/src/party.js`, `proto-ui/src/party.test.js`, `proto-ui/src/components/PartyCard.jsx`
- Modify: `proto-ui/src/api.js` (CRLF), `proto-ui/src/components/ChatDock.jsx`, `proto-ui/src/BackstagePrototype.jsx`, `proto-ui/src/cinema.js` (`isBotMessage` reconnaît aussi `bot:soiree`), `proto-ui/package.json` (ajoute `src/party.test.js` au script `test`)

**Interfaces:**
- Consumes: routes de Task 4 ; `openTMDBPreview({tmdb_id, title})` de `BackstagePrototype.jsx` (sa fiche porte déjà « Demander au serveur » via Seerr, avec confirmation).
- Produces:
  - `party.js` (pur) : `PARTY_BOT_ID = 'bot:soiree'` ; `partyIdOf(payload) -> string | null` (`payload.type === 'party'`) ; `isPartyActive(state) -> boolean` (`joining`/`voting`) ; `partyStep(state) -> 'join'|'answer'|'wait'|'vote'|'result'|'over'` (`over` pour `empty`/`expired`) ; `voteSummary(scores, rank) -> string` (`"👍 2 · 👎 1"`) ; `isPartyCommand(text) -> boolean` (`@soirée`, accents/casse ignorés).
  - `api.js` : `startParty(mode)`, `fetchParty(id)`, `joinParty(id)`, `answerParty(id, answers)`, `launchParty(id)`, `voteParty(id, rank, value)`, `closeParty(id)` — même style que `fetchFilmShowtimes` (`errorDetail` en cas d'échec).
  - `PartyCard({ partyId, isDarkMode, onOpenFilm })` : relit `fetchParty` au montage puis toutes les 3 s tant que `isPartyActive` ; affiche selon `partyStep` :
    - `join` : bouton « Je suis partant » ; liste des partants (✓ si répondu).
    - `answer` : les questions de `state.questions` en boutons (une valeur par question), bouton « Valider ».
    - `wait` : « En attente du lancement » ; pour le lanceur, bouton « On lance ».
    - `vote` : les 3 propositions (affiche cliquable → `onOpenFilm` si `tmdb_id`, titre, raison, badge « Sur le serveur » / « À demander » / séance `20:15 · VF`), boutons 👍/👎 (état actif = mon vote), `voteSummary` ; pour le lanceur, « Clore le vote ».
    - `result` : 🏆 titre ; Ciné : lien « Réserver la séance » (`booking_url`, `target="_blank" rel="noopener noreferrer"`, seulement si `https?://`) ; sinon bouton « Voir la fiche » (`onOpenFilm`) — la fiche porte « Demander au serveur » pour un film absent.
    - `over` : « Soirée expirée » ou « Pas de proposition ce soir ».
    - Erreur d'action → message rouge sous la carte, l'état est relu.
  - `ChatDock({ isDarkMode, onOpenFilm })` : un message dont `partyIdOf(payload)` est non nul rend `<PartyCard>` sous la bulle ; bouton 🍿 à côté du 🎬 qui ouvre un petit choix « Coloc » / « Ciné ce soir » → `startParty(mode)` puis `refresh()` ; après l'envoi d'un message `isPartyCommand` → `refresh()` immédiat.
  - `BackstagePrototype.jsx` : `<ChatDock isDarkMode={isDarkMode} onOpenFilm={openTMDBPreview} />`.

- [ ] **Step 1: Write the failing tests** — `proto-ui/src/party.test.js` (`node:test`, comme `cinema.test.js`) :
  - `partyIdOf` : `{type:'party', party_id:'p1'}` → `'p1'` ; `{type:'cine_films'}` → `null` ; `null` → `null`.
  - `partyStep` : non membre en `joining` → `join` ; membre sans réponse → `answer` ; membre répondu en `joining` → `wait` ; `voting` non membre → `join` ; `voting` membre → `vote` ; `done` → `result` ; `expired` → `over`.
  - `voteSummary({1:{up:2,down:1}}, 1)` → `'👍 2 · 👎 1'` ; rang absent → `'👍 0 · 👎 0'`.
  - `isPartyCommand('@Soiree coloc')` → `true` ; `'@ciné films'` → `false`.
- [ ] **Step 2: Run** `npm --prefix proto-ui test` — Expected: FAIL (module `party.js` absent).
- [ ] **Step 3: Implement** `party.js`, les fonctions `api.js` (script Python CRLF), `PartyCard.jsx`, les changements de `ChatDock.jsx`, `cinema.js`, `BackstagePrototype.jsx`, `package.json`.
- [ ] **Step 4: Run** `npm --prefix proto-ui test` puis `npm --prefix proto-ui run build` — Expected: tests PASS, build OK.
- [ ] **Step 5: Vérifier dans le sandbox** (copie de base, port 8091, intégrations sur 127.0.0.1:9, jamais le serveur 8090) avec deux comptes : lancer une soirée Coloc par 🍿, rejoindre depuis le second compte, répondre, lancer, voter des deux côtés → la carte affiche 🏆 chez les deux ; cliquer une affiche ouvre la fiche. TMDB étant coupé dans le sandbox, les propositions viennent de la bibliothèque.
- [ ] **Step 6: Commit** `git commit -m "Ajoute la carte de soirée film dans le salon"`
