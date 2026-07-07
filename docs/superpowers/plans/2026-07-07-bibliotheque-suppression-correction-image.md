# Bibliothèque : fix tri, suppression de film, correction d'image via TMDB — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the library sort/search/page reset bug, and add delete-movie and correct-image-via-TMDB features to the movie detail dialog.

**Architecture:** Persist library UI state in `AppState.ui_state` (survives page reloads); add `MediaStore.delete()` and a `force` flag on `EnrichmentProcessor.enrich_media_with_tmdb_id`/`_prepare_updates` (reusing existing TMDB search/apply plumbing instead of duplicating it); wire two new buttons + dialogs into the existing `open_media_detail_dialog`.

**Tech Stack:** Python, NiceGUI, SQLite (sqlite3), pytest, Pydantic (`Media` model).

**Spec:** `docs/superpowers/specs/2026-07-07-bibliotheque-suppression-correction-image-design.md`

## Global Constraints

- Follow existing code style: no comments unless explaining non-obvious "why"; French UI strings/labels (match existing `"Fermer"`, `"Enregistrer"`, etc.).
- Reuse existing theme classes (`bs-card`, `bs-outline-btn`, `bs-accent-btn`) and add `bs-danger-btn` following the exact same CSS pattern as the other `@layer theme` button classes in `frontend/theme.py`.
- Every backend/pure-logic change needs a pytest test in the matching existing test file (`tests/test_store.py`, `tests/test_processor_updates.py`, `tests/test_library.py`). UI wiring (dialogs, buttons, debounce) is not unit-tested in this codebase (confirmed: `tests/test_components.py` only tests pure helper functions, never dialog code) — those get a manual verification step instead.
- Run `pytest` after every task; all prior tests must keep passing.

---

### Task 1: Persist library sort/search/page state across reloads

**Files:**
- Modify: `frontend/context.py` (add field to `AppState`)
- Modify: `frontend/pages/library.py:1-10, 57-59` (add helper, use it in `render`)
- Test: `tests/test_library.py`

**Interfaces:**
- Produces: `frontend.context.AppState.ui_state: Dict[str, Dict[str, Any]]` (default `{}`)
- Produces: `frontend.pages.library.get_library_state(ui_state: Dict[str, Dict[str, Any]]) -> Dict[str, Any]`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_library.py` (keep existing imports, add `get_library_state` to the import line):

```python
from frontend.pages.library import filter_and_sort_medias, get_library_state, paginate_medias, total_pages
```

```python
def test_get_library_state_defaults_on_first_call():
    ui_state = {}
    state = get_library_state(ui_state)
    assert state == {"query": "", "sort": "Titre", "page": 1}


def test_get_library_state_persists_across_calls():
    ui_state = {}
    state1 = get_library_state(ui_state)
    state1["sort"] = "Date d'ajout"
    state1["page"] = 3

    state2 = get_library_state(ui_state)
    assert state2["sort"] == "Date d'ajout"
    assert state2["page"] == 3


def test_get_library_state_independent_per_ui_state_dict():
    ui_state_a = {}
    ui_state_b = {}
    get_library_state(ui_state_a)["sort"] = "Note"

    state_b = get_library_state(ui_state_b)
    assert state_b["sort"] == "Titre"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_library_state'`

- [ ] **Step 3: Implement `AppState.ui_state`**

In `frontend/context.py`, change the import line and `AppState`:

```python
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.core.processor import EnrichmentProcessor
from backend.core.store import MediaStore


@dataclass
class AppState:
    all_medias: List[Any] = field(default_factory=list)
    medias: List[Any] = field(default_factory=list)
    force: bool = False
    running: bool = False
    last_synced: Optional[str] = None
    ui_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
```

- [ ] **Step 4: Implement `get_library_state` and use it in `render`**

In `frontend/pages/library.py`, change the top import and add the helper just above `render`:

```python
import re
from typing import Any, Dict, List, Optional
```

```python
def get_library_state(ui_state: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return ui_state.setdefault("library", {"query": "", "sort": SORT_OPTIONS[0], "page": 1})
```

Then change the start of `render`:

```python
def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    state = get_library_state(ctx.state.ui_state)
```

(Remove the old `state = {"query": "", "sort": SORT_OPTIONS[0], "page": 1}` line.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_library.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 6: Manual verification**

Run the app, go to Bibliothèque, set sort to "Date d'ajout", open a movie's detail dialog, change the rating, click "Enregistrer". Confirm the library still shows "Date d'ajout" selected and the same search/page after the reload.

- [ ] **Step 7: Commit**

```bash
git add frontend/context.py frontend/pages/library.py tests/test_library.py
git commit -m "fix: persist library sort/search/page across reloads"
```

---

### Task 2: Debounce the library search input

**Files:**
- Modify: `frontend/pages/library.py` (inside `render`)

**Interfaces:**
- Consumes: `state` dict from Task 1 (`get_library_state`), `_refresh()` (existing local function in `render`)

- [ ] **Step 1: Replace `_on_search` with a debounced version**

In `frontend/pages/library.py`, inside `render`, replace:

```python
        def _on_search(e) -> None:
            state["query"] = e.value
            state["page"] = 1
            _refresh()
```

with:

```python
        search_timer = {"handle": None}

        def _apply_search(value: str) -> None:
            state["query"] = value
            state["page"] = 1
            _refresh()

        def _on_search(e) -> None:
            if search_timer["handle"] is not None:
                search_timer["handle"].cancel()
            value = e.value
            search_timer["handle"] = ui.timer(0.3, lambda: _apply_search(value), once=True)
```

This must stay above the `ui.input(...)` line that wires `on_change=_on_search`, since `_refresh` is defined further down in the same function and Python resolves it at call time (closures), matching the file's existing structure — no reordering of the rest of `render` is needed.

- [ ] **Step 2: Run existing tests to confirm nothing broke**

Run: `pytest tests/test_library.py -v`
Expected: PASS (this change has no pure-logic test — it's UI event wiring, consistent with how `_on_sort`/`_on_search` were never unit-tested before)

- [ ] **Step 3: Manual verification**

Run the app, go to Bibliothèque, type quickly in the search box. Confirm the grid doesn't re-render on every keystroke, but settles ~300ms after you stop typing, and shows the right filtered results.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/library.py
git commit -m "feat: debounce library search input"
```

---

### Task 3: Add `MediaStore.delete()`

**Files:**
- Modify: `backend/core/store.py` (add `_delete_sync` after `_update_sync`, add `delete` after `update`)
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `backend.core.store.MediaStore.delete(media_id: str) -> bool` (async; `True` if a row was deleted, `False` if `media_id` didn't exist)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`:

```python
def test_delete_removes_media(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))

    ok = asyncio.run(store.delete(media.id))
    assert ok is True
    assert asyncio.run(store.fetch_one(media.id)) is None


def test_delete_returns_false_for_unknown_id(tmp_path):
    store = _store(tmp_path)
    ok = asyncio.run(store.delete("unknown"))
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -v`
Expected: FAIL with `AttributeError: 'MediaStore' object has no attribute 'delete'`

- [ ] **Step 3: Implement `delete`**

In `backend/core/store.py`, add right after `_update_sync` (after line 105, before `async def fetch_all`):

```python
    def _delete_sync(self, media_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
            return cursor.rowcount > 0
```

Add at the end of the class, after `async def update`:

```python
    async def delete(self, media_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, media_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/store.py tests/test_store.py
git commit -m "feat: add MediaStore.delete()"
```

---

### Task 4: Delete button + confirmation dialog in the movie detail dialog

**Files:**
- Modify: `frontend/theme.py` (add `--danger` token + `.bs-danger-btn` class)
- Modify: `frontend/components.py` (add delete button + confirm dialog to `open_media_detail_dialog`)

**Interfaces:**
- Consumes: `ctx.store.delete(media.id)` from Task 3, `ctx.reload()` (existing, `frontend/context.py`)

- [ ] **Step 1: Add the danger button style**

In `frontend/theme.py`, add the token:

```python
TOKENS = {
    "--bg": "#faf6ef",
    "--surface": "#ffffff",
    "--border": "#ece4d6",
    "--text": "#2b2420",
    "--text-muted": "#8a8578",
    "--accent": "#7a2331",
    "--accent-gold": "#c9a35c",
    "--danger": "#b3352c",
    "--font-display": "Georgia,'Times New Roman',serif",
    "--font-body": "Arial,Helvetica,sans-serif",
    "--radius": "10px",
}
```

And add the class inside the existing `@layer theme { ... }` block, right after `.q-btn.bs-outline-btn { ... }`:

```css
.q-btn.bs-danger-btn {
  border: 1px solid var(--danger) !important;
  color: var(--danger) !important;
  border-radius: 999px !important;
  background: transparent !important;
  font-family: var(--font-body);
}
```

- [ ] **Step 2: Add the delete button and confirmation dialog**

In `frontend/components.py`, inside `open_media_detail_dialog`, add this function before the final button row (right after `_save`):

```python
        async def _delete() -> None:
            confirm_dialog = ui.dialog()
            with confirm_dialog, ui.card().classes("bs-card p-6"):
                ui.label(f"Supprimer définitivement « {media.title} » ?").classes("bs-title text-base")
                ui.label("Cette action est irréversible.").classes("text-sm mt-1").style("color:var(--text-muted)")

                async def _confirm() -> None:
                    await ctx.store.delete(media.id)
                    ui.notify(f"« {media.title} » supprimé.", type="positive")
                    confirm_dialog.close()
                    dialog.close()
                    await ctx.reload()

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    ui.button("Annuler", on_click=confirm_dialog.close).classes("bs-outline-btn")
                    ui.button("Confirmer la suppression", on_click=_confirm).classes("bs-danger-btn")
            confirm_dialog.open()
```

Then replace the existing final button row:

```python
        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Fermer", on_click=dialog.close).classes("bs-outline-btn")
            ui.button("Enregistrer", on_click=_save).classes("bs-accent-btn")
```

with:

```python
        with ui.row().classes("w-full justify-between items-center mt-4"):
            ui.button("Supprimer", on_click=_delete).classes("bs-danger-btn")
            with ui.row().classes("gap-2"):
                ui.button("Fermer", on_click=dialog.close).classes("bs-outline-btn")
                ui.button("Enregistrer", on_click=_save).classes("bs-accent-btn")
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: PASS (no pure-logic test for this — dialog wiring, same convention as `_save`/`open_media_detail_dialog` which have no direct tests today)

- [ ] **Step 4: Manual verification**

Run the app, open a movie's detail dialog, click "Supprimer". Confirm the confirmation dialog appears. Click "Annuler" — confirm nothing happens and both dialogs behave correctly (confirm dialog closes, detail dialog stays open). Reopen and click "Supprimer" → "Confirmer la suppression" — confirm the movie disappears from the library grid and a positive notification appears.

- [ ] **Step 5: Commit**

```bash
git add frontend/theme.py frontend/components.py
git commit -m "feat: add delete movie button with confirmation dialog"
```

---

### Task 5: Add `force` flag to TMDB metadata application

**Files:**
- Modify: `backend/core/processor.py:236-258, 266-315` (`enrich_media_with_tmdb_id`, `_prepare_updates`)
- Test: `tests/test_processor_updates.py`

**Interfaces:**
- Consumes: nothing new (existing `Media`, `TMDBClient`, `_bare_processor()` test helper)
- Produces: `EnrichmentProcessor._prepare_updates(media, tmdb_data, force: bool = False) -> tuple[Dict[str, Any], Optional[str]]`
- Produces: `EnrichmentProcessor.enrich_media_with_tmdb_id(media_id: str, tmdb_id: int, force: bool = False) -> bool`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_processor_updates.py`:

```python
def test_prepare_updates_force_overwrites_existing_fields():
    p = _bare_processor()
    media = Media(
        id="x", title="Dune", director="Ancien réal", synopsis="Ancien synopsis",
        categories=["Ancien genre"], release_date=date(2000, 1, 1),
    )
    tmdb_data = {
        "release_date": "2021-10-22",
        "overview": "Nouveau synopsis",
        "genres": [{"name": "Horreur"}, {"name": "Thriller"}],
        "credits": {"crew": [{"job": "Director", "name": "Nouveau réal"}]},
    }

    updates, _ = p._prepare_updates(media, tmdb_data, force=True)

    assert updates["director"] == "Nouveau réal"
    assert updates["synopsis"] == "Nouveau synopsis"
    assert updates["categories"] == ["Horreur", "Thriller"]
    assert updates["release_date"] == date(2021, 10, 22)


def test_prepare_updates_without_force_still_does_not_overwrite():
    p = _bare_processor()
    media = Media(id="x", title="Dune", director="Ancien réal")
    tmdb_data = {"credits": {"crew": [{"job": "Director", "name": "Nouveau réal"}]}}

    updates, _ = p._prepare_updates(media, tmdb_data, force=False)

    assert "director" not in updates
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_processor_updates.py -v`
Expected: FAIL with `TypeError: _prepare_updates() got an unexpected keyword argument 'force'`

- [ ] **Step 3: Implement `force` in `_prepare_updates`**

In `backend/core/processor.py`, replace the method signature and the four `if not media.X:` gates:

```python
    def _prepare_updates(self, media: Media, tmdb_data: Optional[Dict[str, Any]], force: bool = False) -> tuple[Dict[str, Any], Optional[str]]:
        updates: Dict[str, Any] = {}
        poster_url = None
        today = date.today()

        if not media.status:
            updates["status"] = Values.STATUS_TO_WATCH

        # Date (depuis la fiche si présente, sinon TMDB)
        release_date = media.release_date
        if tmdb_data and (not release_date or force):
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
            if not media.director or force:
                director = self.tmdb.get_director(tmdb_data)
                if director:
                    updates["director"] = director

            if not media.synopsis or force:
                overview = tmdb_data.get("overview")
                if overview:
                    updates["synopsis"] = overview[:2000]

            genres = self.tmdb.get_genres(tmdb_data)
            if (not media.categories or force) and genres:
                updates["categories"] = genres

            if (not media.tags or force) and genres:
                suggested_tags = self._map_genres_to_tags(genres)
                if suggested_tags:
                    updates["tags"] = suggested_tags

            updates["tmdb_ok"] = True
            poster_url = self.tmdb.get_poster_url(tmdb_data)

        return updates, poster_url
```

- [ ] **Step 4: Implement `force` in `enrich_media_with_tmdb_id`**

In `backend/core/processor.py`, replace:

```python
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
```

with:

```python
    async def enrich_media_with_tmdb_id(self, media_id: str, tmdb_id: int, force: bool = False):
        """Enrichissement manuel : l'utilisateur a choisi explicitement ce film TMDB."""
        logger.info("Enrichissement manuel de %s avec TMDB ID %s", media_id, tmdb_id)

        media = await self.store.fetch_one(media_id)
        if media is None:
            raise ValueError("Impossible de récupérer la fiche")

        tmdb_details = await self.tmdb.get_details(tmdb_id, is_series=is_series(media.type))
        if not tmdb_details:
            raise ValueError("Impossible de récupérer les détails TMDB")

        updates, poster_url = self._prepare_updates(media, tmdb_details, force=force)

        cover_todo = poster_url if (not media.cover_url or force) else None
        changes = summarize_changes(media, updates, poster_url=cover_todo)

        await self._apply_updates(media_id, updates, cover_url=cover_todo)

        history.record(media_id, media.title, changes, source="manual")
        await self._mark_processed_after_update(media_id, media)
        return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_processor_updates.py -v`
Expected: PASS

- [ ] **Step 6: Run full suite (regression check)**

Run: `pytest -v`
Expected: PASS — in particular `tests/test_processor_pass.py` / `tests/test_processor_match.py`, which exercise `enrich_media_with_tmdb_id` and `_prepare_updates` without `force`, must be unaffected (default `force=False` preserves old behavior).

- [ ] **Step 7: Commit**

```bash
git add backend/core/processor.py tests/test_processor_updates.py
git commit -m "feat: add force flag to overwrite existing metadata from a chosen TMDB match"
```

---

### Task 6: "Corriger via TMDB" dialog in the movie detail dialog

**Files:**
- Modify: `frontend/components.py` (add import, add button + dialog to `open_media_detail_dialog`)

**Interfaces:**
- Consumes: `ctx.processor.search_candidates(query: str, is_series_flag: bool = False, year: Optional[int] = None) -> List[Dict[str, Any]]` (existing, `backend/core/processor.py:151-154`; each result dict has `id`, `title`, `release_date`, `poster_url`)
- Consumes: `ctx.processor.enrich_media_with_tmdb_id(media_id, tmdb_id, force: bool = False)` from Task 5
- Consumes: `backend.core.mapping.is_series(media_type) -> bool` (existing)
- Consumes: `media_poster(cover_url, *, width=None, height=None)` (existing, same file)

- [ ] **Step 1: Add the import**

In `frontend/components.py`, add to the top imports:

```python
from backend.core.mapping import is_series
```

- [ ] **Step 2: Add the correction dialog function and button**

Inside `open_media_detail_dialog`, add this function right after `_delete` (from Task 4) and before the final button row:

```python
        async def _open_correction_dialog() -> None:
            correction_dialog = ui.dialog()
            with correction_dialog, ui.card().classes("bs-card w-full max-w-lg p-6"):
                ui.label(f"Corriger « {media.title} » via TMDB").classes("bs-title text-base")

                results_box = ui.column().classes("w-full mt-4")

                async def _apply(cand: dict) -> None:
                    await ctx.processor.enrich_media_with_tmdb_id(media.id, cand["id"], force=True)
                    ui.notify(f"« {media.title} » mis à jour depuis TMDB.", type="positive")
                    correction_dialog.close()
                    dialog.close()
                    await ctx.reload()

                def _render_results(candidates: list) -> None:
                    results_box.clear()
                    with results_box:
                        if not candidates:
                            ui.label("Aucun résultat.").style("color:var(--text-muted)")
                        for cand in candidates:
                            row = ui.element("div").classes("bs-card p-2 cursor-pointer mt-2") \
                                .on("click", lambda c=cand: _apply(c))
                            with row, ui.row().classes("w-full items-center gap-3"):
                                media_poster(cand.get("poster_url"), width="50px")
                                year = (cand.get("release_date") or "")[:4] or "—"
                                ui.label(f"{cand.get('title')} ({year})").classes("text-sm")

                with ui.row().classes("w-full items-center gap-2 mt-2"):
                    query_input = ui.input(value=media.title).classes("flex-grow")

                    async def _search() -> None:
                        query = (query_input.value or "").strip()
                        if not query:
                            return
                        results_box.clear()
                        with results_box:
                            ui.spinner("dots", size="2rem").classes("self-center")
                        candidates = await ctx.processor.search_candidates(query, is_series_flag=is_series(media.type))
                        _render_results(candidates)

                    ui.button(icon="search", on_click=_search).props("flat round")

                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Annuler", on_click=correction_dialog.close).classes("bs-outline-btn")

            correction_dialog.open()
            await _search()
```

Then update the left side of the final button row (added in Task 4) to include this new button:

```python
        with ui.row().classes("w-full justify-between items-center mt-4"):
            with ui.row().classes("gap-2"):
                ui.button("Supprimer", on_click=_delete).classes("bs-danger-btn")
                ui.button("Corriger via TMDB", on_click=_open_correction_dialog).classes("bs-outline-btn")
            with ui.row().classes("gap-2"):
                ui.button("Fermer", on_click=dialog.close).classes("bs-outline-btn")
                ui.button("Enregistrer", on_click=_save).classes("bs-accent-btn")
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: PASS (dialog wiring, no direct unit test — same convention as the rest of `open_media_detail_dialog`)

- [ ] **Step 4: Manual verification**

Run the app, open the detail dialog for a movie with a known-wrong poster (e.g. "Odyssée"). Click "Corriger via TMDB" — confirm a spinner briefly appears then a list of candidates with thumbnails and years. Click a candidate — confirm both dialogs close, a positive notification appears, and the movie's poster/director/synopsis/genres are updated in the library. Also test with an empty query and a query with no results (should show "Aucun résultat.").

- [ ] **Step 5: Commit**

```bash
git add frontend/components.py
git commit -m "feat: add TMDB re-match dialog to correct a movie's image and metadata"
```

---

## Self-Review Notes

- **Spec coverage:** Section 1 (sort fix) → Task 1. Section 2 (delete) → Tasks 3-4. Section 3 (TMDB correction) → Tasks 5-6. Section 4 (debounce, spinner) → Task 2 (debounce) and Task 6 (spinner inline in the search flow).
- **Type consistency:** `get_library_state` (Task 1) returns the same shape `{"query": str, "sort": str, "page": int}` consumed by `filter_and_sort_medias`/`paginate_medias` unchanged. `enrich_media_with_tmdb_id(media_id, tmdb_id, force=False)` (Task 5) signature matches its Task 6 call site (`force=True`) and its unchanged wizard.py call site (`force` defaults to `False`, so `frontend/pages/wizard.py`'s existing call with no `force` arg keeps working).
- **No placeholders:** every step has full, concrete code — no "add error handling" or "similar to Task N" placeholders.
