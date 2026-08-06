# TMDB Batch Relink Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relier de manière sûre les médias locaux sans identifiant TMDB et produire un CSV pour les fiches restantes.

**Architecture:** Un module pur choisit uniquement une correspondance dont le titre normalisé est exact et dont l'année, si disponible, est compatible. Le script CLI utilise ce module, cherche les films et séries sur les endpoints adaptés, écrit seulement avec `--apply` et exporte les échecs ou ambiguïtés dans un CSV. L'API de réassociation réutilise la mise à jour type-aware afin que les séries utilisent leurs détails TV.

**Tech Stack:** Python 3, asyncio, SQLite via `MediaStore`, TMDB via `TMDBClient`, pytest.

## Global Constraints

- Ne jamais modifier un média ayant déjà `tmdb_id`.
- La simulation est le comportement par défaut ; seule l'option explicite `--apply` écrit dans SQLite.
- Une correspondance ambiguë ou absente est exportée dans `tmdb-a-verifier.csv` et non appliquée.

---

### Task 1: Sélection sûre et préparation des champs TMDB

**Files:**
- Create: `backend/core/tmdb_relink.py`
- Test: `tests/test_tmdb_relink.py`

**Interfaces:**
- Produces: `select_confident_match(media, candidates) -> dict | None`.
- Produces: `build_relink_updates(media, details, tmdb, tmdb_id) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
def test_exact_title_and_matching_year_is_selected():
    assert select_confident_match(media, candidates)["id"] == 2

def test_homonymous_title_without_a_year_is_left_for_manual_review():
    assert select_confident_match(media, candidates) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmdb_relink.py -v`
Expected: FAIL because `backend.core.tmdb_relink` does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
def select_confident_match(media, candidates):
    # titre normalisé exact ; année locale obligatoire si deux homonymes existent
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tmdb_relink.py -v`
Expected: PASS.
### Task 2: Script de réassociation de masse et correction de l'API

**Files:**
- Create: `backend/scripts/relink_tmdb.py`
- Modify: `backend/api.py`
- Modify: `tests/test_tmdb_relink.py`

**Interfaces:**
- Consumes: `select_confident_match` and `build_relink_updates`.
- Produces: `async def relink_missing_tmdb_ids(apply: bool, report_path: Path) -> dict`.

- [ ] **Step 1: Write failing tests**

```python
def test_batch_relink_writes_only_confident_match_and_reports_other(tmp_path):
    summary = asyncio.run(relink_missing_tmdb_ids(store, fake_tmdb, apply=True, report_path=report))
    assert summary == {"linked": 1, "to_review": 1, "already_linked": 1}
    assert report.read_text(encoding="utf-8").count("ambiguous") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmdb_relink.py -v`
Expected: FAIL because the batch entry point does not exist.

- [ ] **Step 3: Implement the CLI and API reuse**

```python
parser.add_argument("--apply", action="store_true")
parser.add_argument("--report", default="tmdb-a-verifier.csv")
```

The script selects `TMDBClient.search(..., is_series=is_series(media.type), year=...)`, persists only under `--apply`, and writes rows containing local title/type/year/reason and candidate ID/title/year. The API retrieves details through `get_details(..., is_series=...)`.

- [ ] **Step 4: Run targeted and full verification**

Run: `pytest tests/test_tmdb_relink.py tests/test_api.py tests/test_series.py -v; pytest -q`
Expected: PASS.
