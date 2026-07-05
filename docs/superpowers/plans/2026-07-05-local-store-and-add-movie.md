# Local SQLite Store + Manual Add-Movie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Notion with a local SQLite store as Backstage's sole data
backend (importing the 247 existing films), and add a dashboard form to
create new film entries manually.

**Architecture:** A new `MediaStore` (SQLite, stdlib `sqlite3`) replaces
`NotionService` as `EnrichmentProcessor`'s persistence dependency.
`_prepare_updates`/`summarize_changes` switch from Notion's property-JSON
shape to plain Python field values. A one-shot script migrates existing
Notion data into the new store, preserving IDs so `cache.json` stays valid.
The dashboard gains an "Ajouter un film" dialog that writes straight to the
store.

**Tech Stack:** Python 3.13, `sqlite3` (stdlib, no new dependency), NiceGUI
3.6.1, pydantic 2.12.5, pytest.

## Global Constraints

- No new third-party dependency — use stdlib `sqlite3`, not `aiosqlite` or an ORM.
- Full replacement of Notion in the live app — Notion code (`backend/core/notion.py`) is kept only for the one-shot migration script, never imported by `main.py`/`frontend/*` after this plan.
- Migration must preserve original Notion page IDs as the local primary key, so `cache.json` (keyed by `media.id`) is not invalidated.
- `MediaStore` blocking DB calls must run via `asyncio.to_thread` — never block the NiceGUI event loop.
- Dry-run diff output (`summarize_changes`) must keep showing French field labels (e.g. "Réalisateur", not "director") — matches the existing UI copy in the wizard preview.
- Follow existing code style: French docstrings/comments/log messages, `bs-*` CSS classes for new UI elements (see `frontend/pages/dashboard.py`).

---

### Task 1: `MediaStore` — schema, fetch, create, update

**Files:**
- Create: `backend/core/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `backend.core.models.Media` (existing pydantic model, unchanged field names: `id, title, type, status, support, rating, release_date, director, categories, synopsis, tags, review, tmdb_ok, cover_url`).
- Produces: `MediaStore(db_path: str)`, `MediaStore.init_schema() -> None`, `MediaStore.fetch_all() -> List[Media]` (async), `MediaStore.fetch_one(media_id: str) -> Optional[Media]` (async), `MediaStore.create(fields: Dict[str, Any]) -> Media` (async), `MediaStore.update(media_id: str, fields: Dict[str, Any]) -> bool` (async). These four are the only methods later tasks (processor, frontend) call.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_store.py`:

```python
import asyncio
from datetime import date

from backend.core.store import MediaStore


def _store(tmp_path) -> MediaStore:
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    return store


def test_create_generates_id_when_absent(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))
    assert media.title == "Dune"
    assert media.id  # uuid4 généré
    assert media.type is None
    assert media.categories == []
    assert media.tmdb_ok is False


def test_create_preserves_supplied_id(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"id": "notion-page-123", "title": "Arrival"}))
    assert media.id == "notion-page-123"


def test_create_persists_all_fields(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({
        "title": "Dune",
        "type": "Film",
        "status": "À regarder",
        "support": "Cinéma",
        "rating": "8",
        "release_date": date(2021, 10, 22),
        "director": "Denis Villeneuve",
        "categories": ["SF", "Aventure"],
        "synopsis": "Un noble héritier...",
        "tags": ["😌 Détente"],
        "review": "Excellent",
        "tmdb_ok": True,
        "cover_url": "http://example.com/dune.jpg",
    }))

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.title == "Dune"
    assert fetched.type == "Film"
    assert fetched.release_date == date(2021, 10, 22)
    assert fetched.categories == ["SF", "Aventure"]
    assert fetched.tags == ["😌 Détente"]
    assert fetched.tmdb_ok is True
    assert fetched.cover_url == "http://example.com/dune.jpg"


def test_fetch_all_returns_created_medias(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.create({"title": "Dune"}))
    asyncio.run(store.create({"title": "Arrival"}))

    all_medias = asyncio.run(store.fetch_all())
    assert {m.title for m in all_medias} == {"Dune", "Arrival"}


def test_fetch_one_returns_none_when_missing(tmp_path):
    store = _store(tmp_path)
    assert asyncio.run(store.fetch_one("unknown")) is None


def test_update_changes_only_given_fields(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "director": None}))

    ok = asyncio.run(store.update(media.id, {"director": "Denis Villeneuve", "tmdb_ok": True}))
    assert ok is True

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.director == "Denis Villeneuve"
    assert fetched.tmdb_ok is True
    assert fetched.title == "Dune"  # inchangé


def test_update_returns_false_for_unknown_id(tmp_path):
    store = _store(tmp_path)
    ok = asyncio.run(store.update("unknown", {"director": "X"}))
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.store'`

- [ ] **Step 3: Implement `MediaStore`**

Create `backend/core/store.py`:

```python
"""Persistance locale des médias (SQLite), remplace Notion comme source de vérité."""
import asyncio
import json
import sqlite3
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from backend.core.models import Media

_COLUMNS = [
    "id", "title", "type", "status", "support", "rating", "release_date",
    "director", "categories", "synopsis", "tags", "review", "tmdb_ok", "cover_url",
]

_LIST_FIELDS = {"categories", "tags"}


class MediaStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    type TEXT,
                    status TEXT,
                    support TEXT,
                    rating TEXT,
                    release_date TEXT,
                    director TEXT,
                    categories TEXT,
                    synopsis TEXT,
                    tags TEXT,
                    review TEXT,
                    tmdb_ok INTEGER NOT NULL DEFAULT 0,
                    cover_url TEXT
                )
                """
            )

    @staticmethod
    def _row_to_media(row: sqlite3.Row) -> Media:
        data = dict(row)
        for field in _LIST_FIELDS:
            data[field] = json.loads(data[field]) if data[field] else []
        data["tmdb_ok"] = bool(data["tmdb_ok"])
        if data["release_date"]:
            data["release_date"] = date.fromisoformat(data["release_date"])
        return Media(**data)

    @staticmethod
    def _encode(field: str, value: Any) -> Any:
        if field in _LIST_FIELDS:
            return json.dumps(value or [])
        if field == "release_date" and value is not None:
            return value.isoformat() if isinstance(value, date) else value
        if field == "tmdb_ok":
            return int(bool(value))
        return value

    def _fetch_all_sync(self) -> List[Media]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM media").fetchall()
        return [self._row_to_media(row) for row in rows]

    def _fetch_one_sync(self, media_id: str) -> Optional[Media]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM media WHERE id = ?", (media_id,)
            ).fetchone()
        return self._row_to_media(row) if row else None

    def _create_sync(self, fields: Dict[str, Any]) -> Media:
        media_id = fields.get("id") or str(uuid.uuid4())
        values = {col: fields.get(col) for col in _COLUMNS if col != "id"}
        values["id"] = media_id

        with sqlite3.connect(self.db_path) as conn:
            placeholders = ", ".join("?" for _ in _COLUMNS)
            conn.execute(
                f"INSERT INTO media ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [self._encode(col, values[col]) for col in _COLUMNS],
            )
        return self._fetch_one_sync(media_id)

    def _update_sync(self, media_id: str, fields: Dict[str, Any]) -> bool:
        if not fields:
            return self._fetch_one_sync(media_id) is not None
        set_clause = ", ".join(f"{col} = ?" for col in fields)
        values = [self._encode(col, val) for col, val in fields.items()]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE media SET {set_clause} WHERE id = ?", [*values, media_id]
            )
            return cursor.rowcount > 0

    async def fetch_all(self) -> List[Media]:
        return await asyncio.to_thread(self._fetch_all_sync)

    async def fetch_one(self, media_id: str) -> Optional[Media]:
        return await asyncio.to_thread(self._fetch_one_sync, media_id)

    async def create(self, fields: Dict[str, Any]) -> Media:
        return await asyncio.to_thread(self._create_sync, fields)

    async def update(self, media_id: str, fields: Dict[str, Any]) -> bool:
        return await asyncio.to_thread(self._update_sync, media_id, fields)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/core/store.py tests/test_store.py
git commit -m "feat: add local SQLite MediaStore"
```

---

### Task 2: Trim `backend/core/models.py` (drop Notion aliases)

**Files:**
- Modify: `backend/core/models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Media` with the same field names/types as before, no `alias=` metadata, no `populate_by_name` config (no longer needed since nothing constructs `Media` via alias keys).

- [ ] **Step 1: Edit the model**

Replace the full contents of `backend/core/models.py` with:

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class Media(BaseModel):
    id: str  # identifiant local (uuid, ou id Notion importé)
    title: str
    type: Optional[str] = None  # Film, Série, etc.
    status: Optional[str] = None  # Terminé, À voir, etc.
    support: Optional[str] = None  # NAS, Netflix, etc.
    rating: Optional[str] = None

    release_date: Optional[date] = None
    director: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    synopsis: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    review: Optional[str] = None
    tmdb_ok: bool = False

    # URL de l'image de couverture
    cover_url: Optional[str] = None
```

- [ ] **Step 2: Run the full test suite to verify nothing depended on the aliases**

Run: `python -m pytest -v`
Expected: Same failures as before this task only (aliases were unused — `tests/test_diff.py` and `tests/test_mapping.py` already fail/will fail for unrelated reasons fixed in later tasks; no *new* failures should appear in `test_cache.py`, `test_processor_match.py`, `test_processor_pass.py`, `test_store.py`, `test_stats.py`, `test_theme.py`, `test_tmdb_tv.py`, `test_format_utils.py`, `test_history.py`, `test_http_retry.py`)

- [ ] **Step 3: Commit**

```bash
git add backend/core/models.py
git commit -m "refactor: drop unused Notion aliases from Media model"
```

---

### Task 3: `mapping.py` — drop Notion schema, add `FIELD_LABELS`, relocate `Props` into `notion.py`

**Files:**
- Modify: `backend/core/mapping.py`
- Modify: `backend/core/notion.py`
- Modify: `tests/test_mapping.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `FIELD_LABELS: Dict[str, str]` mapping plain `Media` field names to French display labels: `{"status": "Statut", "support": "Support", "director": "Réalisateur", "synopsis": "Synopsis", "release_date": "Date de sortie", "categories": "Catégorie", "tags": "Tags", "tmdb_ok": "TMDB_OK", "cover_url": "Couverture"}`. `Values`, `SERIES_TYPES`, `is_series`, `GENRE_TAG_RULES` unchanged. `Props`, `REQUIRED_PROPERTIES`, `validate_schema` removed from `mapping.py`.

**Important — do this as one atomic task/commit:** `backend/core/notion.py` currently does `from backend.core.mapping import Props, validate_schema`, and `backend/core/processor.py` (not refactored until Task 5) still does `from backend.core.notion import NotionService, Media` — so `notion.py`'s imports must keep working the moment `mapping.py` changes, otherwise `test_processor_match.py`/`test_processor_pass.py` break by transitively importing a broken `notion.py`. `Props` (Notion's own property-name constants) moves to live directly inside `notion.py` instead of being deleted, and `notion.py`'s dead `validate_schema_sync` method (the only user of `validate_schema`) is removed in this same task.

- [ ] **Step 1: Replace `backend/core/mapping.py`**

```python
"""Règles métier partagées (statuts, genres, libellés d'affichage)."""
from typing import Dict


class Values:
    """Valeurs de statut/support appliquées par les règles métier."""
    STATUS_TO_WATCH = "À regarder"
    SUPPORT_CINEMA = "Cinéma"
    SUPPORT_DOWNLOAD = "À télécharger"


# Valeurs de la propriété "type" interprétées comme des séries TV (sinon : film)
SERIES_TYPES = {"Série", "Serie", "Séries", "TV", "Série TV"}


def is_series(media_type) -> bool:
    return bool(media_type) and media_type in SERIES_TYPES


# Règles genre TMDB (fr-FR) -> tag
GENRE_TAG_RULES: Dict[str, str] = {
    "Comédie": "😌 Détente",
    "Animation": "👨‍👩‍👧‍👦 Familial",
    "Familial": "👨‍👩‍👧‍👦 Familial",
    "Horreur": "⚠️ Film dur",
    "Documentaire": "🧠 Complexe",
    "Histoire": "🎬 Classique",
    "Drame": "😢 Triste",
}

# Libellés français affichés dans l'aperçu dry-run (nom de champ Media -> libellé)
FIELD_LABELS: Dict[str, str] = {
    "status": "Statut",
    "support": "Support",
    "director": "Réalisateur",
    "synopsis": "Synopsis",
    "release_date": "Date de sortie",
    "categories": "Catégorie",
    "tags": "Tags",
    "tmdb_ok": "TMDB_OK",
    "cover_url": "Couverture",
}
```

- [ ] **Step 2: Relocate `Props` into `notion.py` and drop its dead schema validator**

In `backend/core/notion.py`, change the import line:
```python
from backend.core.mapping import Props, validate_schema
```
to nothing (remove it entirely — `Props` now lives locally in this file, `validate_schema` is no longer used anywhere in this file).

Add this class directly after the existing imports (`import logging`, `import httpx`, `from backend.config import Config`, `from backend.core.models import Media`, `from backend.core import http`, `from typing import ...`, `from datetime import datetime`):

```python
class Props:
    """Noms exacts des propriétés Notion (utilisé uniquement par ce module,
    conservé pour le script de migration one-shot)."""
    TITLE = "Nom"
    TYPE = "Type"
    STATUS = "Statut"
    SUPPORT = "Support"
    RATING = "Note /10"
    RELEASE_DATE = "Date de sortie"
    DIRECTOR = "Réalisateur"
    CATEGORY = "Catégorie"
    SYNOPSIS = "Synopsis"
    TAGS = "Tags"
    REVIEW = "Avis"
    TMDB_OK = "TMDB_OK"
```

Then delete the `validate_schema_sync` classmethod (currently near the end of the file, just above `_map_page_to_media`):
```python
    @classmethod
    def validate_schema_sync(cls) -> List[str]:
        """
        Vérifie (en synchrone, au démarrage) que la base Notion expose les
        propriétés attendues. Retourne la liste des problèmes (vide si OK).
        Lève en cas d'échec d'accès à la base.
        """
        url = f"{cls.BASE_URL}/databases/{Config.DATABASE_ID}"
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=cls._headers())
        response.raise_for_status()
        return validate_schema(response.json().get("properties", {}))

```

Everything else in `notion.py` (`_extract_property`, `fetch_all_media`, `fetch_page`, `update_page`, `append_image_block`, `_map_page_to_media`) stays exactly as-is — still needed by the Task 8 migration script.

- [ ] **Step 3: Replace `tests/test_mapping.py`**

```python
from backend.core.mapping import FIELD_LABELS, GENRE_TAG_RULES, is_series


def test_genre_rules_cover_known_genres():
    assert GENRE_TAG_RULES["Comédie"]
    assert GENRE_TAG_RULES["Horreur"]


def test_field_labels_cover_diff_fields():
    for field in ("status", "support", "director", "synopsis", "release_date", "categories", "tags", "tmdb_ok"):
        assert field in FIELD_LABELS


def test_is_series_matches_known_types():
    assert is_series("Série") is True
    assert is_series("Film") is False
    assert is_series(None) is False
```

- [ ] **Step 4: Run tests, and confirm `notion.py` still imports cleanly**

Run: `python -m pytest tests/test_mapping.py -v && python -c "import backend.core.notion"`
Expected: PASS (3 tests), then no output from the import check (exit code 0)

- [ ] **Step 5: Commit**

```bash
git add backend/core/mapping.py backend/core/notion.py tests/test_mapping.py
git commit -m "refactor: drop Notion schema mapping, add plain-field display labels, relocate Props into notion.py"
```

---

### Task 4: `diff.py` — decode plain field values instead of Notion payloads

**Files:**
- Modify: `backend/core/diff.py`
- Modify: `tests/test_diff.py`

**Interfaces:**
- Consumes: `backend.core.mapping.FIELD_LABELS` (Task 3).
- Produces: `summarize_changes(media: Media, updates: Dict[str, Any], poster_url: Optional[str] = None) -> List[Dict[str, str]]` — same signature as before, but `updates` now maps `Media` field name -> plain new value (e.g. `{"director": "Denis Villeneuve", "categories": ["SF", "Aventure"], "tmdb_ok": True}`) instead of Notion property JSON. This is what Task 5 (`processor.py`) will call it with.

- [ ] **Step 1: Replace `backend/core/diff.py`**

```python
"""Traduction d'un dict de mise à jour (valeurs Media simples) en diff lisible (mode dry-run)."""
from typing import Dict, Any, List, Optional

from backend.core.mapping import FIELD_LABELS
from backend.core.models import Media


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def summarize_changes(
    media: Media,
    updates: Dict[str, Any],
    poster_url: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Retourne la liste des changements prévus : [{'field', 'old', 'new'}, ...].
    Inclut la couverture si une affiche va être posée.
    """
    changes: List[Dict[str, str]] = []
    for field, value in updates.items():
        new = _format_value(value)
        old = _format_value(getattr(media, field, None))
        if new and new != old:
            changes.append({"field": FIELD_LABELS.get(field, field), "old": old or "—", "new": new})

    if poster_url and not media.cover_url:
        changes.append({"field": "Couverture", "old": "—", "new": "Affiche TMDB"})

    return changes
```

- [ ] **Step 2: Replace `tests/test_diff.py`**

```python
from backend.core.diff import summarize_changes
from backend.core.models import Media


def test_new_values_are_reported_as_changes():
    media = Media(id="x", title="Dune")  # tout vide
    updates = {
        "director": "Denis Villeneuve",
        "status": "À regarder",
        "categories": ["SF", "Aventure"],
        "tmdb_ok": True,
    }

    changes = summarize_changes(media, updates)
    fields = {c["field"]: c for c in changes}

    assert fields["Réalisateur"]["new"] == "Denis Villeneuve"
    assert fields["Réalisateur"]["old"] == "—"
    assert fields["Catégorie"]["new"] == "SF, Aventure"
    assert fields["TMDB_OK"]["new"] == "Oui"


def test_unchanged_values_are_not_reported():
    media = Media(id="x", title="Dune", director="Denis Villeneuve", cover_url="http://existing")
    updates = {"director": "Denis Villeneuve"}

    changes = summarize_changes(media, updates)
    assert changes == []


def test_poster_change_reported_when_no_existing_cover():
    media = Media(id="x", title="Dune")
    changes = summarize_changes(media, {}, poster_url="http://tmdb/poster.jpg")
    assert changes == [{"field": "Couverture", "old": "—", "new": "Affiche TMDB"}]


def test_poster_change_not_reported_when_cover_already_set():
    media = Media(id="x", title="Dune", cover_url="http://existing")
    changes = summarize_changes(media, {}, poster_url="http://tmdb/poster.jpg")
    assert changes == []
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_diff.py -v`
Expected: PASS (4 tests)

- [ ] **Step 4: Commit**

```bash
git add backend/core/diff.py tests/test_diff.py
git commit -m "refactor: diff plain Media field values instead of Notion payload shape"
```

---

### Task 5: `EnrichmentProcessor` — switch from `NotionService` to `MediaStore`

**Files:**
- Modify: `backend/core/processor.py`
- Test: `tests/test_processor_updates.py` (new — covers `_prepare_updates`, which had no dedicated test before)

**Interfaces:**
- Consumes: `MediaStore` (Task 1): `fetch_all()`, `fetch_one(id)`, `update(id, fields)`. `mapping.Values`, `mapping.is_series`, `mapping.GENRE_TAG_RULES` (unchanged). `diff.summarize_changes(media, updates, poster_url=None)` (Task 4, plain-value shape).
- Produces: `EnrichmentProcessor(store: MediaStore)` constructor (was no-arg). All other public method signatures (`process_all`, `run_auto_pass`, `process_one_media`, `search_candidates`, `enrich_media_with_tmdb_id`) unchanged — later tasks (frontend) only need to know the constructor now takes `store`.

- [ ] **Step 1: Write the failing test for `_prepare_updates`**

Create `tests/test_processor_updates.py`:

```python
from datetime import date

from backend.core.processor import EnrichmentProcessor
from backend.core.models import Media


def _bare_processor() -> EnrichmentProcessor:
    return object.__new__(EnrichmentProcessor)


def test_prepare_updates_returns_plain_field_values():
    p = _bare_processor()
    media = Media(id="x", title="Dune", release_date=date(2021, 10, 22))
    tmdb_data = {
        "release_date": "2021-10-22",
        "overview": "Un noble héritier...",
        "genres": [{"name": "Science-Fiction"}, {"name": "Aventure"}],
        "credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]},
    }

    updates, poster_url = p._prepare_updates(media, tmdb_data)

    assert updates["status"] == "À regarder"
    assert updates["support"] == "À télécharger"  # date passée, pas de cinéma
    assert updates["director"] == "Denis Villeneuve"
    assert updates["synopsis"] == "Un noble héritier..."
    assert updates["tmdb_ok"] is True
    assert isinstance(updates["categories"], list)


def test_prepare_updates_does_not_overwrite_existing_fields():
    p = _bare_processor()
    media = Media(id="x", title="Dune", director="Déjà rempli", status="Vu")
    updates, _ = p._prepare_updates(media, None)

    assert "director" not in updates
    assert "status" not in updates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_processor_updates.py -v`
Expected: FAIL — `updates` currently keyed by `Props.STATUS` etc. with Notion payload values, so `updates["status"]` raises `KeyError`.

- [ ] **Step 3: Rewrite `backend/core/processor.py`**

Full replacement:

```python
import asyncio
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Callable

from backend.core.models import Media
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient
from backend.core.cache_service import CacheService
from backend.core.mapping import Values, GENRE_TAG_RULES, is_series
from backend.core import history, omdb
from backend.core.diff import summarize_changes

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 5


class EnrichmentProcessor:
    def __init__(self, store: MediaStore):
        self.store = store
        self.tmdb = TMDBClient()
        self.cache = CacheService()

    async def process_all(self, force: bool = False):
        """Lance le processus d'enrichissement complet (Mode Automatique)."""
        logger.info("Début de l'enrichissement...")
        medias = await self.store.fetch_all()

        updated_count = 0
        skipped_count = 0

        for media in medias:
            result = await self.process_one_media(media, force=force)
            if result['status'] == 'PROCESSED':
                updated_count += 1
            elif result['status'] in ('SKIPPED', 'AMBIGUOUS'):
                skipped_count += 1

        logger.info("Enrichissement terminé. Mis à jour : %s, Ignorés : %s", updated_count, skipped_count)
        return updated_count, skipped_count

    async def run_auto_pass(
        self,
        medias: List[Media],
        force: bool = False,
        progress_cb: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> Dict[str, Any]:
        """
        Traite tous les médias en parallèle (concurrence bornée).
        Les cas non ambigus sont enrichis automatiquement ; les ambigus sont
        collectés pour résolution manuelle ultérieure (interactive, séquentielle).

        `progress_cb(done, total, result)` est appelé après chaque média terminé.
        Retourne {'processed', 'skipped', 'errors', 'ambiguous': [result, ...]}.
        """
        total = len(medias)
        semaphore = asyncio.Semaphore(max(1, concurrency))
        counters = {'processed': 0, 'skipped': 0, 'errors': 0, 'ambiguous': []}
        done = 0

        async def worker(media: Media) -> Dict[str, Any]:
            async with semaphore:
                return media, await self.process_one_media(media, force=force)

        tasks = [asyncio.create_task(worker(m)) for m in medias]
        for coro in asyncio.as_completed(tasks):
            media, result = await coro
            done += 1
            status = result['status']
            if status == 'PROCESSED':
                counters['processed'] += 1
            elif status == 'AMBIGUOUS':
                counters['ambiguous'].append(result)
            elif status == 'ERROR':
                counters['errors'] += 1
            else:
                counters['skipped'] += 1

            if progress_cb:
                progress_cb(done, total, {'media': media, **result})

        return counters

    async def process_one_media(self, media: Media, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        Traite un seul média et retourne son statut :
        - {'status': 'SKIPPED', 'reason': '...'}
        - {'status': 'PROCESSED', 'title': '...', 'tmdb_id': ...}
        - {'status': 'PREVIEW', 'changes': [...], ...}        (dry_run)
        - {'status': 'AMBIGUOUS', 'candidates': [...], 'original_title': '...', 'media_id': '...'}
        - {'status': 'ERROR', 'error': '...'}
        """
        try:
            if not force and self.cache.is_processed(media):
                return {'status': 'SKIPPED', 'reason': 'Déjà traité'}

            missing_info = self._get_missing_fields(media)

            if not missing_info and media.status and media.support and media.director and media.release_date:
                if not dry_run:
                    self.cache.mark_as_processed(media)
                return {'status': 'SKIPPED', 'reason': 'Fiche complète'}

            series = is_series(media.type)
            year = media.release_date.year if media.release_date else None
            tmdb_results = await self.tmdb.search(media.title, is_series=series, year=year)

            best_match = self._find_best_match(media, tmdb_results)

            if best_match:
                tmdb_details = await self.tmdb.get_details(best_match['id'], is_series=series)
                updates, poster_url = self._prepare_updates(media, tmdb_details)

                cover_todo = poster_url if (poster_url and not media.cover_url) else None
                changes = summarize_changes(media, updates, poster_url=cover_todo)

                if dry_run:
                    return {
                        'status': 'PREVIEW',
                        'title': best_match['title'],
                        'tmdb_id': best_match['id'],
                        'media_id': media.id,
                        'changes': changes,
                    }

                if updates or cover_todo:
                    await self._apply_updates(media.id, updates, cover_url=cover_todo)
                    history.record(media.id, media.title, changes, source="auto")
                    await self._mark_processed_after_update(media.id, media)
                    return {'status': 'PROCESSED', 'title': best_match['title'], 'tmdb_id': best_match['id']}

                self.cache.mark_as_processed(media)
                return {'status': 'SKIPPED', 'reason': 'Aucune mise à jour nécessaire'}

            # Aucun match évident -> on enrichit les candidats pour le wizard
            candidates = await self._enrich_candidates(tmdb_results, is_series=series)
            return {
                'status': 'AMBIGUOUS',
                'candidates': candidates,
                'original_title': media.title,
                'media_id': media.id,
                'is_series': series,
            }

        except Exception as e:
            logger.exception("Erreur lors du traitement de %s: %s", media.title, e)
            return {'status': 'ERROR', 'error': str(e)}

    async def search_candidates(self, query: str, is_series_flag: bool = False, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Recherche manuelle libre (utilisée par le wizard quand TMDB ne trouve rien)."""
        results = await self.tmdb.search(query, is_series=is_series_flag, year=year)
        return await self._enrich_candidates(results, is_series=is_series_flag)

    async def _enrich_candidates(self, results: List[Dict[str, Any]], is_series: bool = False) -> List[Dict[str, Any]]:
        """Récupère UNE seule fois les détails de chaque candidat (réal, genres, tags, affiche, IMDb)."""
        for cand in results:
            details = await self.tmdb.get_details(cand['id'], is_series=is_series)
            if details:
                cand['director'] = self.tmdb.get_director(details)
                genres = self.tmdb.get_genres(details)
                cand['genres'] = genres
                cand['suggested_tags'] = self._map_genres_to_tags(genres)
                cand['overview'] = details.get('overview', '')
            cand['poster_url'] = self.tmdb.poster_url_from_path(cand.get('poster_path'), size="w185")

            # Enrichissement OMDb optionnel (note IMDb + classification d'âge)
            year = self._result_year(cand)
            omdb_data = await omdb.fetch(cand.get('title', ''), year=year)
            if omdb_data:
                cand['imdb_rating'] = omdb_data.get('imdb_rating')
                cand['rated'] = omdb_data.get('rated')
        return results

    def _get_missing_fields(self, media: Media) -> List[str]:
        missing = []
        if not media.director:
            missing.append("director")
        if not media.release_date:
            missing.append("release_date")
        if not media.synopsis:
            missing.append("synopsis")
        if not media.categories:
            missing.append("categories")
        return missing

    def _find_best_match(self, media: Media, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Score chaque résultat (titre + année + popularité) et retourne le meilleur
        au-dessus d'un seuil de confiance ; sinon None (ambiguïté).
        """
        if not results:
            return None

        query_norm = media.title.lower().strip()
        query_year = media.release_date.year if media.release_date else None

        best, best_score = None, 0.0
        for res in results:
            score = 0.0
            res_title = (res.get("title") or "").lower().strip()

            # Similarité de titre
            if res_title == query_norm:
                score += 1.0
            elif query_norm in res_title or res_title in query_norm:
                score += 0.6

            # Concordance d'année (forte si on l'a)
            if query_year:
                res_year = self._result_year(res)
                if res_year == query_year:
                    score += 0.5
                elif res_year and abs(res_year - query_year) <= 1:
                    score += 0.2

            # Bonus popularité (départage les homonymes obscurs)
            if res.get("popularity", 0) >= 5:
                score += 0.1

            if score > best_score:
                best, best_score = res, score

        # Seuil : titre exact, ou bonne similarité confortée par l'année
        return best if best_score >= 0.8 else None

    @staticmethod
    def _result_year(res: Dict[str, Any]) -> Optional[int]:
        rd = res.get("release_date") or ""
        try:
            return datetime.strptime(rd, "%Y-%m-%d").year
        except ValueError:
            return None

    async def enrich_media_with_tmdb_id(self, media_id: str, tmdb_id: int):
        """Enrichissement manuel : l'utilisateur a choisi explicitement ce film TMDB."""
        logger.info("Enrichissement manuel de %s avec TMDB ID %s", media_id, tmdb_id)

        # État courant de la fiche (pour ne pas écraser ce qui est déjà rempli)
        media = await self.store.fetch_one(media_id)
        if media is None:
            raise ValueError("Impossible de récupérer la fiche")

        tmdb_details = await self.tmdb.get_details(tmdb_id, is_series=is_series(media.type))
        if not tmdb_details:
            raise ValueError("Impossible de récupérer les détails TMDB")

        updates, poster_url = self._prepare_updates(media, tmdb_details)

        cover_todo = poster_url if not media.cover_url else None
        changes = summarize_changes(media, updates, poster_url=cover_todo)

        await self._apply_updates(media_id, updates, cover_url=cover_todo)

        history.record(media_id, media.title, changes, source="manual")
        await self._mark_processed_after_update(media_id, media)
        return True

    def _map_genres_to_tags(self, genres: List[str]) -> List[str]:
        tags = [GENRE_TAG_RULES[g] for g in genres if g in GENRE_TAG_RULES]
        if "Horreur" in genres and "Thriller" in genres:
            tags.append("⚠️ Film dur")
        return list(set(tags))

    def _prepare_updates(self, media: Media, tmdb_data: Optional[Dict[str, Any]]) -> tuple[Dict[str, Any], Optional[str]]:
        updates: Dict[str, Any] = {}
        poster_url = None
        today = date.today()

        if not media.status:
            updates["status"] = Values.STATUS_TO_WATCH

        # Date (depuis la fiche si présente, sinon TMDB)
        release_date = media.release_date
        if tmdb_data and not release_date:
            release_str = tmdb_data.get("release_date")
            if release_str:
                try:
                    release_date = datetime.strptime(release_str, "%Y-%m-%d").date()
                    updates["release_date"] = release_date
                except ValueError:
                    pass

        # Règle Support
        if not media.support:
            if release_date and release_date > today:
                updates["support"] = Values.SUPPORT_CINEMA
            else:
                updates["support"] = Values.SUPPORT_DOWNLOAD

        if tmdb_data:
            if not media.director:
                director = self.tmdb.get_director(tmdb_data)
                if director:
                    updates["director"] = director

            if not media.synopsis:
                overview = tmdb_data.get("overview")
                if overview:
                    updates["synopsis"] = overview[:2000]

            genres = self.tmdb.get_genres(tmdb_data)
            if not media.categories and genres:
                updates["categories"] = genres

            if not media.tags and genres:
                suggested_tags = self._map_genres_to_tags(genres)
                if suggested_tags:
                    updates["tags"] = suggested_tags

            updates["tmdb_ok"] = True
            poster_url = self.tmdb.get_poster_url(tmdb_data)

        return updates, poster_url

    async def _apply_updates(self, media_id: str, fields: Dict[str, Any], cover_url: Optional[str] = None):
        if cover_url:
            fields = {**fields, "cover_url": cover_url}
        success = await self.store.update(media_id, fields)
        if success:
            logger.info("Fiche locale mise à jour pour %s", media_id)
        else:
            logger.warning("Échec de mise à jour locale pour %s", media_id)

    async def _mark_processed_after_update(self, page_id: str, fallback: Media):
        """Recharge la fiche après écriture pour cacher l'empreinte de l'état réel."""
        fresh = await self.store.fetch_one(page_id)
        self.cache.mark_as_processed(fresh or fallback)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_processor_updates.py tests/test_processor_match.py tests/test_processor_pass.py -v`
Expected: PASS (all tests — `test_processor_match.py`/`test_processor_pass.py` use `object.__new__(EnrichmentProcessor)`, unaffected by the constructor change)

- [ ] **Step 5: Commit**

```bash
git add backend/core/processor.py tests/test_processor_updates.py
git commit -m "refactor: EnrichmentProcessor uses MediaStore instead of NotionService"
```

---

### Task 6: `scheduler.py` — use `store` instead of `processor.notion`

**Files:**
- Modify: `backend/core/scheduler.py`

**Interfaces:**
- Consumes: `EnrichmentProcessor(store: MediaStore)` (Task 5), `Config.DB_PATH` (Task 7).
- Produces: `start()` unchanged signature (called from `main.py`).

- [ ] **Step 1: Edit `backend/core/scheduler.py`**

Replace:
```python
async def _run_once():
    processor = EnrichmentProcessor()
    medias = await processor.notion.fetch_all_media()
```
with:
```python
async def _run_once():
    processor = EnrichmentProcessor(MediaStore(Config.DB_PATH))
    medias = await processor.store.fetch_all()
```

And add the import at the top:
```python
from backend.core.store import MediaStore
```

Full resulting file:

```python
"""Synchronisation incrémentale automatique (optionnelle).

Active si SYNC_INTERVAL_MIN > 0. Toutes les N minutes, enrichit automatiquement
les fiches incomplètes (les cas ambigus sont ignorés — ils restent pour le wizard).
"""
import asyncio
import logging

from backend.config import Config
from backend.core.processor import EnrichmentProcessor
from backend.core.store import MediaStore

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _run_once():
    processor = EnrichmentProcessor(MediaStore(Config.DB_PATH))
    medias = await processor.store.fetch_all()
    todo = [
        m for m in medias
        if not (m.director and m.release_date and m.support) or not m.tmdb_ok
    ]
    if not todo:
        logger.info("[sync] Rien à enrichir.")
        return
    counters = await processor.run_auto_pass(todo)
    logger.info(
        "[sync] Auto: %s enrichis, %s ambigus laissés, %s ignorés, %s erreurs",
        counters['processed'], len(counters['ambiguous']), counters['skipped'], counters['errors'],
    )


async def _loop():
    interval = Config.SYNC_INTERVAL_MIN * 60
    logger.info("Sync auto activée (toutes les %s min).", Config.SYNC_INTERVAL_MIN)
    while True:
        await asyncio.sleep(interval)
        try:
            await _run_once()
        except Exception as e:
            logger.exception("[sync] Erreur durant la synchronisation: %s", e)


def start():
    """Démarre la boucle de sync si configurée. À appeler dans la boucle asyncio de l'app."""
    global _task
    if Config.SYNC_INTERVAL_MIN <= 0:
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
```

- [ ] **Step 2: Sanity-check the module imports cleanly**

Run: `python -c "import backend.core.scheduler"`
Expected: no output, exit code 0 (this task has no dedicated automated test — `scheduler.start()` spawns a real background asyncio loop tied to `SYNC_INTERVAL_MIN`, not something worth mocking here; the import check catches syntax/reference errors, and Task 11's manual smoke test exercises the full startup path)

- [ ] **Step 3: Commit**

```bash
git add backend/core/scheduler.py
git commit -m "refactor: scheduler reads from MediaStore instead of NotionService"
```

---

### Task 7: `Config`/`main.py` — drop Notion requirement, add `DB_PATH`, init schema at startup

**Files:**
- Modify: `backend/config.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: `MediaStore.init_schema()` (Task 1).
- Produces: `Config.DB_PATH: str` (new). `Config.check()` removed (nothing left to require).

- [ ] **Step 1: Edit `backend/config.py`**

Replace the full file with:

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Conservés pour le script de migration one-shot (scripts/migrate_from_notion.py)
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    DATABASE_ID = os.getenv("DATABASE_ID")

    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    DB_PATH = os.getenv("DB_PATH", "backstage.db")

    # Optionnels (fonctionnalités avancées, dégradation propre si absents)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OMDB_API_KEY = os.getenv("OMDB_API_KEY")
    # Intervalle de sync auto en minutes (0 = désactivé)
    SYNC_INTERVAL_MIN = int(os.getenv("SYNC_INTERVAL_MIN", "0") or "0")

    @classmethod
    def ai_enabled(cls) -> bool:
        return bool(cls.ANTHROPIC_API_KEY)

    @classmethod
    def omdb_enabled(cls) -> bool:
        return bool(cls.OMDB_API_KEY)
```

- [ ] **Step 2: Edit `main.py`**

Replace the full file with:

```python
import os
import logging

from nicegui import ui, app

from backend.config import Config
from backend.core import http, scheduler
from backend.core.store import MediaStore
import frontend.ui  # noqa: F401  (enregistre la page via @ui.page)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Crée la base locale si elle n'existe pas encore
MediaStore(Config.DB_PATH).init_schema()

# Synchronisation auto périodique (si SYNC_INTERVAL_MIN > 0)
app.on_startup(scheduler.start)

# Ferme proprement le client HTTP partagé à l'arrêt
app.on_shutdown(http.aclose)

# reload=True uniquement en dev (BACKSTAGE_DEV=1)
RELOAD = os.getenv("BACKSTAGE_DEV", "0") == "1"

ui.run(title="Backstage - Vidéothèque", port=8080, reload=RELOAD)
```

- [ ] **Step 3: Sanity-check imports**

Run: `python -c "from backend.config import Config; print(Config.DB_PATH)"`
Expected: `backstage.db`

- [ ] **Step 4: Commit**

```bash
git add backend/config.py main.py
git commit -m "refactor: drop Notion startup requirement, init local DB schema at startup"
```

---

### Task 8: Migration script

**Files:**
- Create: `scripts/migrate_from_notion.py`

**Interfaces:**
- Consumes: `NotionService.fetch_all_media()` (existing, unchanged), `MediaStore.init_schema()` / `MediaStore.create()` (Task 1), `Config.NOTION_TOKEN` / `Config.DATABASE_ID` / `Config.DB_PATH` (Task 7).
- Produces: a runnable script, no importable interface consumed elsewhere.

- [ ] **Step 1: Write the script**

```python
"""
Migration one-shot : importe tous les films de la base Notion existante dans
la base locale SQLite, en conservant les IDs Notion d'origine (pour que
cache.json, indexé par id, reste valide après la bascule).

Usage : python scripts/migrate_from_notion.py
Nécessite NOTION_TOKEN et DATABASE_ID dans l'environnement (.env).
"""
import asyncio
import logging

from backend.config import Config
from backend.core.notion import NotionService
from backend.core.store import MediaStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    if not Config.NOTION_TOKEN or not Config.DATABASE_ID:
        raise SystemExit("NOTION_TOKEN et DATABASE_ID doivent être définis pour la migration.")

    store = MediaStore(Config.DB_PATH)
    store.init_schema()

    medias = await NotionService.fetch_all_media()
    logger.info("Récupéré %s films depuis Notion, import en cours...", len(medias))

    for media in medias:
        await store.create(media.model_dump())

    logger.info("Migration terminée : %s films importés dans %s.", len(medias), Config.DB_PATH)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify it runs against the real Notion database**

Run: `python scripts/migrate_from_notion.py`
Expected: log line `Migration terminée : 247 films importés dans backstage.db.` (or the current live count), and a new `backstage.db` file created in the project root.

Then spot-check:
```bash
python -c "
import asyncio
from backend.core.store import MediaStore
store = MediaStore('backstage.db')
medias = asyncio.run(store.fetch_all())
print(len(medias), medias[0].title, medias[0].id)
"
```
Expected: prints the total count and a sample title with its (Notion-derived) id.

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_from_notion.py
git commit -m "feat: add one-shot Notion-to-local-DB migration script"
```

(Do not commit `backstage.db` itself — check it's covered by `.gitignore`; if not, add `backstage.db` to `.gitignore` in this same commit.)

---

### Task 9: Frontend wiring — `AppContext`, `ui.py` use `MediaStore`

**Files:**
- Modify: `frontend/context.py`
- Modify: `frontend/ui.py`

**Interfaces:**
- Consumes: `MediaStore` (Task 1), `EnrichmentProcessor(store: MediaStore)` (Task 5), `Config.DB_PATH` (Task 7).
- Produces: `AppContext.store: MediaStore` — consumed by Task 10 (dashboard add-movie dialog).

- [ ] **Step 1: Edit `frontend/context.py`**

```python
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

from backend.core.processor import EnrichmentProcessor
from backend.core.store import MediaStore


@dataclass
class AppState:
    all_medias: List[Any] = field(default_factory=list)
    medias: List[Any] = field(default_factory=list)
    force: bool = False
    running: bool = False
    last_synced: Optional[str] = None


@dataclass
class AppContext:
    processor: EnrichmentProcessor
    store: MediaStore
    state: AppState
    reload: Callable[[], Awaitable[None]]
    rerender: Callable[[], None]
    navigate: Callable[[str], None]
```

- [ ] **Step 2: Edit `frontend/ui.py`**

Change the imports (remove `NotionService`, add `MediaStore`):
```python
from backend.config import Config
from backend.core.store import MediaStore
from backend.core.processor import EnrichmentProcessor
```

In `main_page`, replace:
```python
    processor = EnrichmentProcessor()
    state = AppState()
```
with:
```python
    store = MediaStore(Config.DB_PATH)
    processor = EnrichmentProcessor(store)
    state = AppState()
```

Replace the `reload()` body's Notion call:
```python
        try:
            state.all_medias = await NotionService.fetch_all_media()
        except Exception as e:
```
with:
```python
        try:
            state.all_medias = await store.fetch_all()
        except Exception as e:
```

And update the `AppContext(...)` construction:
```python
    ctx = AppContext(processor=processor, store=store, state=state, reload=reload, rerender=rerender, navigate=navigate)
```

- [ ] **Step 3: Sanity-check imports**

Run: `python -c "import frontend.ui"`
Expected: no output, exit code 0

- [ ] **Step 4: Commit**

```bash
git add frontend/context.py frontend/ui.py
git commit -m "refactor: wire MediaStore through AppContext instead of NotionService"
```

---

### Task 10: Dashboard "Ajouter un film" dialog

**Files:**
- Modify: `frontend/pages/dashboard.py`

**Interfaces:**
- Consumes: `AppContext.store.create(fields: Dict[str, Any]) -> Media` (Task 1/9), `AppContext.reload()` (existing), `frontend.components.media_poster` (existing), `backend.core.mapping.is_series`/`SERIES_TYPES` is not needed here — the type select offers exactly `"Film"` / `"Série"`.
- Produces: nothing new consumed elsewhere — this is a leaf UI addition.

- [ ] **Step 1: Add the dialog + button to `frontend/pages/dashboard.py`**

Add this import at the top (alongside the existing ones):
```python
from datetime import date as date_cls
```

Add the new button next to the existing two, changing:
```python
        with ui.row().classes("gap-2"):
            ui.button("Lancer l'enrichissement", on_click=lambda: _start_wizard(ctx)) \
                .classes("bs-accent-btn px-4 py-2")
            ui.button("Prévisualiser (dry-run)", on_click=lambda: _run_preview(ctx)) \
                .classes("bs-outline-btn px-4 py-2")
```
to:
```python
        with ui.row().classes("gap-2"):
            ui.button("Lancer l'enrichissement", on_click=lambda: _start_wizard(ctx)) \
                .classes("bs-accent-btn px-4 py-2")
            ui.button("Prévisualiser (dry-run)", on_click=lambda: _run_preview(ctx)) \
                .classes("bs-outline-btn px-4 py-2")
            ui.button("Ajouter un film", on_click=lambda: _open_add_dialog(ctx)) \
                .classes("bs-outline-btn px-4 py-2")
```

Also add the button to the empty-state branch (so it's reachable even with zero films to process), changing:
```python
    if not medias:
        with ui.column().classes("w-full items-center justify-center py-16 opacity-70"):
            ui.icon("check_circle", size="5rem").style("color:var(--accent-gold)")
            ui.label("Tout est à jour !").classes("bs-title text-xl mt-4")
        _force_switch(ctx)
        return
```
to:
```python
    if not medias:
        with ui.column().classes("w-full items-center justify-center py-16 opacity-70"):
            ui.icon("check_circle", size="5rem").style("color:var(--accent-gold)")
            ui.label("Tout est à jour !").classes("bs-title text-xl mt-4")
        _force_switch(ctx)
        ui.button("Ajouter un film", on_click=lambda: _open_add_dialog(ctx)) \
            .classes("bs-outline-btn px-4 py-2 mt-2")
        return
```

Add these new functions at the end of the file:

```python
def _open_add_dialog(ctx: AppContext) -> None:
    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("bs-card w-full max-w-2xl p-6"):
        ui.label("Ajouter un film").classes("bs-title text-lg mb-2")

        title_input = ui.input("Titre *").classes("w-full")
        type_select = ui.select(["Film", "Série"], value="Film", label="Type").classes("w-full")
        status_input = ui.input("Statut").classes("w-full")
        support_input = ui.input("Support").classes("w-full")
        rating_input = ui.input("Note /10").classes("w-full")
        release_date_input = ui.input("Date de sortie (AAAA-MM-JJ)").classes("w-full")
        director_input = ui.input("Réalisateur").classes("w-full")
        categories_input = ui.input("Catégories (séparées par des virgules)").classes("w-full")
        tags_input = ui.input("Tags (séparés par des virgules)").classes("w-full")
        synopsis_input = ui.textarea("Synopsis").classes("w-full")
        review_input = ui.textarea("Avis").classes("w-full")
        cover_url_input = ui.input("URL de l'affiche").classes("w-full")

        preview_box = ui.column().classes("w-full items-center mt-2")

        def _update_preview() -> None:
            preview_box.clear()
            with preview_box:
                media_poster(cover_url_input.value or None, height="160px")

        cover_url_input.on("blur", lambda: _update_preview())
        _update_preview()

        error_label = ui.label("").classes("text-xs mt-1").style("color:#c0392b")

        async def _submit() -> None:
            title = title_input.value.strip()
            if not title:
                error_label.set_text("Le titre est obligatoire.")
                return

            release_date_value = None
            raw_date = (release_date_input.value or "").strip()
            if raw_date:
                try:
                    release_date_value = date_cls.fromisoformat(raw_date)
                except ValueError:
                    error_label.set_text("Date invalide (attendu AAAA-MM-JJ).")
                    return

            fields = {
                "title": title,
                "type": type_select.value,
                "status": (status_input.value or "").strip() or None,
                "support": (support_input.value or "").strip() or None,
                "rating": (rating_input.value or "").strip() or None,
                "release_date": release_date_value,
                "director": (director_input.value or "").strip() or None,
                "categories": [c.strip() for c in (categories_input.value or "").split(",") if c.strip()],
                "synopsis": (synopsis_input.value or "").strip() or None,
                "tags": [t.strip() for t in (tags_input.value or "").split(",") if t.strip()],
                "review": (review_input.value or "").strip() or None,
                "cover_url": (cover_url_input.value or "").strip() or None,
            }

            await ctx.store.create(fields)
            ui.notify(f"« {title} » ajouté.", type="positive")
            dialog.close()
            await ctx.reload()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Annuler", on_click=dialog.close).classes("bs-outline-btn")
            ui.button("Ajouter", on_click=_submit).classes("bs-accent-btn")

    dialog.open()
```

- [ ] **Step 2: Sanity-check imports**

Run: `python -c "import frontend.pages.dashboard"`
Expected: no output, exit code 0

- [ ] **Step 3: Manual smoke test**

Run the app: `python main.py`
Then in the browser at `http://localhost:8080`:
1. Click "Ajouter un film".
2. Leave the title blank and click "Ajouter" — expect the inline error "Le titre est obligatoire." and the dialog stays open.
3. Fill in title "Test Film", type "Film", release date "2024-01-01", leave the rest blank, click "Ajouter" — expect a green "« Test Film » ajouté." notification, the dialog closes, and "Test Film" appears in the "à traiter" list (since most fields are empty).
4. Paste a poster image URL into "URL de l'affiche" and tab away — expect the preview image to update above the buttons.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/dashboard.py
git commit -m "feat: add manual 'add movie' dialog to the dashboard"
```

---

### Task 11: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests PASS (existing suites `test_cache.py`, `test_format_utils.py`, `test_history.py`, `test_http_retry.py`, `test_stats.py`, `test_theme.py`, `test_tmdb_tv.py` untouched and green; `test_store.py`, `test_processor_updates.py`, updated `test_mapping.py`/`test_diff.py`, `test_processor_match.py`, `test_processor_pass.py` all green)

- [ ] **Step 2: Confirm no remaining runtime reference to `NotionService` outside the migration script**

Run: `grep -rn "NotionService" --include="*.py" . | grep -v "backend[\\/]core[\\/]notion.py" | grep -v "scripts[\\/]migrate_from_notion.py"`
Expected: no output (the only remaining matches are `backend/core/notion.py`'s own class definition and `scripts/migrate_from_notion.py`'s usage — both excluded by the two `grep -v` filters; `frontend/ui.py`, `backend/core/processor.py`, `backend/core/scheduler.py`, and `main.py` no longer mention it after Tasks 5, 6, 7, 9)

- [ ] **Step 3: Manual smoke test of the full enrichment flow against the migrated local DB**

Run: `python main.py`, open `http://localhost:8080`, and click "Lancer l'enrichissement" on the pre-existing migrated dataset — confirm it runs to completion without the `RuntimeError` from before (already fixed separately) and without any Notion-related errors in the console, and that a manually-added film cycles correctly through the wizard.

This step has no further commit — it's the final verification gate for the whole plan.
