# Navbar ivoire + page Bibliothèque Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dark, hard-to-read `bs-topbar` with an ivory bar matching the rest of the app, and add a "Bibliothèque" section that lists every media in the local store with search + sort.

**Architecture:** Two independent, additive changes to `frontend/`. (1) CSS-only edit in `theme.py` recolors the existing topbar/nav-link classes — no structural change to `ui.py`'s rendering logic. (2) A new `frontend/pages/library.py` module, wired into the existing `SECTIONS` / `PAGE_RENDERERS` pattern already used by `dashboard.py`, `stats.py`, etc. Its poster card is extracted from `dashboard.py` into `frontend/components.py` (`media_card`) so both pages share one implementation. Library data comes from `AppState.all_medias`, already loaded by `ui.py`'s `reload()` — no backend or `MediaStore` changes.

**Tech Stack:** Python, NiceGUI (Quasar-based UI), pytest.

## Global Constraints

- No changes to `backend/core/*` (spec: "Aucune modification du backend").
- No faceted filters (type/support/category), no detail/edit view, no pagination — search + sort only (spec: "Hors scope").
- Reuse `frontend/components.py` for the poster card; do not duplicate it between `dashboard.py` and `library.py`.
- Follow existing repo convention: frontend rendering functions (anything using `nicegui.ui`) are not unit-tested; pure logic extracted into plain functions is unit-tested with pytest (see `tests/test_theme.py`, `tests/test_format_utils.py` for the pattern already in place).

---

### Task 1: Ivory topbar CSS

**Files:**
- Modify: `frontend/theme.py:54-56`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no API change — `build_theme_css()` signature and `TOKENS` dict are unchanged; only the CSS text for `.bs-topbar`, `.bs-navlink`, `.bs-navlink.active` changes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_theme.py`:

```python
def test_topbar_is_ivory_not_dark():
    css = build_theme_css()
    assert ".bs-topbar { background: var(--surface); border-bottom: 1px solid var(--border); }" in css
    assert ".bs-navlink { color: var(--text-muted) !important; opacity: 1; font-size: 0.85rem; }" in css
    assert ".bs-navlink.active { color: var(--accent) !important; border-bottom: 2px solid var(--accent-gold); }" in css
    assert "background: var(--text); color: var(--bg); }} .bs-topbar" not in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py::test_topbar_is_ivory_not_dark -v`
Expected: FAIL (current CSS still has `background: var(--text)` for `.bs-topbar` and `color: var(--bg) !important; opacity: 0.75` for `.bs-navlink`).

- [ ] **Step 3: Implement the CSS change**

In `frontend/theme.py`, replace the last three rule lines (currently):

```python
.bs-topbar {{ background: var(--text); color: var(--bg); }}
.bs-navlink {{ color: var(--bg) !important; opacity: 0.75; font-size: 0.85rem; }}
.bs-navlink.active {{ opacity: 1; border-bottom: 2px solid var(--accent-gold); }}
```

with:

```python
.bs-topbar {{ background: var(--surface); border-bottom: 1px solid var(--border); }}
.bs-navlink {{ color: var(--text-muted) !important; opacity: 1; font-size: 0.85rem; }}
.bs-navlink.active {{ color: var(--accent) !important; border-bottom: 2px solid var(--accent-gold); }}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_theme.py -v`
Expected: all PASS, including the new test.

- [ ] **Step 5: Commit**

```bash
git add frontend/theme.py tests/test_theme.py
git commit -m "fix(frontend): recolor topbar to ivory, dark bar was unreadable behind modals"
```

---

### Task 2: Extract shared poster card into `components.py`

**Files:**
- Modify: `frontend/components.py`
- Modify: `frontend/pages/dashboard.py:1-58`

**Interfaces:**
- Consumes: `frontend.components.media_poster` (already exists, unchanged).
- Produces: `frontend.components.media_card(media: Any) -> None` — renders the poster + title + year/type badge card. Task 4 (library page) imports this.

There is no automated test for this task: `dashboard.py`'s rendering was never unit-tested (NiceGUI element trees require a running client), and this step is a pure move, not new logic. Verification is manual, folded into Task 4's manual check since both pages render the same function.

- [ ] **Step 1: Add `media_card` to `frontend/components.py`**

Current `frontend/components.py`:

```python
from typing import Optional

from nicegui import ui


def media_poster(cover_url: Optional[str], *, height: str = "160px") -> None:
    """Affiche le poster TMDB si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if cover_url:
        ui.image(cover_url).classes("rounded w-full").style(f"height:{height}; object-fit:cover;")
    else:
        with ui.element("div").classes("bs-poster-placeholder w-full").style(f"height:{height};"):
            ui.icon("movie", size="2rem").classes("opacity-70")


def source_badge(source: str) -> None:
    color = "#7a2331" if source == "manual" else "#c9a35c"
    ui.badge("Manuel" if source == "manual" else "Auto", color=color)
```

Replace it with:

```python
from typing import Any, Optional

from nicegui import ui


def media_poster(cover_url: Optional[str], *, height: str = "160px") -> None:
    """Affiche le poster TMDB si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if cover_url:
        ui.image(cover_url).classes("rounded w-full").style(f"height:{height}; object-fit:cover;")
    else:
        with ui.element("div").classes("bs-poster-placeholder w-full").style(f"height:{height};"):
            ui.icon("movie", size="2rem").classes("opacity-70")


def media_card(media: Any) -> None:
    """Carte poster + titre + badge année/type, partagée par le dashboard et la bibliothèque."""
    with ui.element("div").classes("bs-card p-2"):
        media_poster(media.cover_url, height="140px")
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")


def source_badge(source: str) -> None:
    color = "#7a2331" if source == "manual" else "#c9a35c"
    ui.badge("Manuel" if source == "manual" else "Auto", color=color)
```

- [ ] **Step 2: Update `frontend/pages/dashboard.py` to use it**

Change the import line (currently `from frontend.components import media_poster`) to:

```python
from frontend.components import media_card, media_poster
```

Delete the now-duplicate local function:

```python
def _media_card(media: Any) -> None:
    with ui.element("div").classes("bs-card p-2"):
        media_poster(media.cover_url, height="140px")
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")
```

And update its one call site — in `_render_dashboard`, change:

```python
    with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
        for m in medias:
            _media_card(m)
```

to:

```python
    with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
        for m in medias:
            media_card(m)
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `pytest -v`
Expected: all PASS (this task touches no logic covered by existing tests, so the suite should be unaffected).

- [ ] **Step 4: Commit**

```bash
git add frontend/components.py frontend/pages/dashboard.py
git commit -m "refactor(frontend): move media card into components.py for reuse"
```

---

### Task 3: Library filter/sort logic (TDD)

**Files:**
- Create: `frontend/pages/library.py` (pure functions only in this task — no `nicegui` UI calls yet)
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: `backend.core.models.Media` (existing dataclass — fields used: `title: str`, `release_date: Optional[date]`, `rating: Optional[str]`).
- Produces:
  - `SORT_OPTIONS: List[str]` = `["Titre", "Année", "Note"]`
  - `filter_and_sort_medias(medias: List[Media], query: str, sort_key: str) -> List[Media]`
  - Task 4 imports both of these plus adds `render(container, ctx)` to the same file.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_library.py`:

```python
from datetime import date

import pytest

from backend.core.models import Media
from frontend.pages.library import filter_and_sort_medias


def _media(title, release_date=None, rating=None):
    return Media(id=title, title=title, release_date=release_date, rating=rating)


def test_filter_by_title_substring_case_insensitive():
    medias = [_media("Blade Runner"), _media("The Matrix"), _media("blade of glory")]
    result = filter_and_sort_medias(medias, "blade", "Titre")
    assert [m.title for m in result] == ["Blade Runner", "blade of glory"]


def test_empty_query_returns_all():
    medias = [_media("B"), _media("A")]
    result = filter_and_sort_medias(medias, "", "Titre")
    assert len(result) == 2


def test_sort_by_title_alphabetical_case_insensitive():
    medias = [_media("banana"), _media("Apple"), _media("cherry")]
    result = filter_and_sort_medias(medias, "", "Titre")
    assert [m.title for m in result] == ["Apple", "banana", "cherry"]


def test_sort_by_year_recent_first_missing_last():
    medias = [
        _media("Old", release_date=date(1990, 1, 1)),
        _media("New", release_date=date(2020, 1, 1)),
        _media("Undated"),
    ]
    result = filter_and_sort_medias(medias, "", "Année")
    assert [m.title for m in result] == ["New", "Old", "Undated"]


def test_sort_by_rating_desc_missing_last():
    medias = [
        _media("Mid", rating="6"),
        _media("Top", rating="9/10"),
        _media("Unrated"),
    ]
    result = filter_and_sort_medias(medias, "", "Note")
    assert [m.title for m in result] == ["Top", "Mid", "Unrated"]


def test_unknown_sort_key_raises():
    with pytest.raises(ValueError):
        filter_and_sort_medias([], "", "Popularité")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'frontend.pages.library'` (file doesn't exist yet).

- [ ] **Step 3: Implement the minimal logic**

Create `frontend/pages/library.py`:

```python
import re
from typing import List, Optional

from backend.core.models import Media

SORT_OPTIONS = ["Titre", "Année", "Note"]


def _rating_value(media: Media) -> Optional[float]:
    if not media.rating:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)?)", media.rating)
    return float(match.group(1)) if match else None


def filter_and_sort_medias(medias: List[Media], query: str, sort_key: str) -> List[Media]:
    query_norm = (query or "").strip().lower()
    filtered = [m for m in medias if query_norm in m.title.lower()] if query_norm else list(medias)

    if sort_key == "Titre":
        return sorted(filtered, key=lambda m: m.title.lower())

    if sort_key == "Année":
        with_date = sorted((m for m in filtered if m.release_date), key=lambda m: m.release_date, reverse=True)
        without_date = [m for m in filtered if not m.release_date]
        return with_date + without_date

    if sort_key == "Note":
        rated = sorted((m for m in filtered if _rating_value(m) is not None), key=_rating_value, reverse=True)
        unrated = [m for m in filtered if _rating_value(m) is None]
        return rated + unrated

    raise ValueError(f"Tri inconnu : {sort_key}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_library.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/library.py tests/test_library.py
git commit -m "feat(frontend): add library filter/sort logic with tests"
```

---

### Task 4: Library page UI + wire into navigation

**Files:**
- Modify: `frontend/pages/library.py` (add `render()` — the module already has `SORT_OPTIONS` and `filter_and_sort_medias` from Task 3)
- Modify: `frontend/ui.py:11-28` (imports, `SECTIONS`, `PAGE_RENDERERS`)

**Interfaces:**
- Consumes:
  - `frontend.pages.library.filter_and_sort_medias`, `SORT_OPTIONS` (Task 3)
  - `frontend.components.media_card` (Task 2)
  - `frontend.context.AppContext` — `ctx.state.all_medias: List[Media]` (existing field, already populated by `ui.py`'s `reload()`)
- Produces: `frontend.pages.library.render(container: ui.element, ctx: AppContext) -> None`, matching the signature every other entry in `PAGE_RENDERERS` uses (see `dashboard.render`, `history.render`).

No automated test: this step is NiceGUI wiring, consistent with how `dashboard.render`/`history.render`/`stats.render` are untested today. Verified manually in Step 4 below.

- [ ] **Step 1: Add `render()` to `frontend/pages/library.py`**

Replace the full contents of `frontend/pages/library.py` (which after Task 3 has only the imports, `SORT_OPTIONS`, `_rating_value`, and `filter_and_sort_medias`) with:

```python
import re
from typing import List, Optional

from nicegui import ui

from backend.core.models import Media
from frontend.components import media_card
from frontend.context import AppContext

SORT_OPTIONS = ["Titre", "Année", "Note"]


def _rating_value(media: Media) -> Optional[float]:
    if not media.rating:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)?)", media.rating)
    return float(match.group(1)) if match else None


def filter_and_sort_medias(medias: List[Media], query: str, sort_key: str) -> List[Media]:
    query_norm = (query or "").strip().lower()
    filtered = [m for m in medias if query_norm in m.title.lower()] if query_norm else list(medias)

    if sort_key == "Titre":
        return sorted(filtered, key=lambda m: m.title.lower())

    if sort_key == "Année":
        with_date = sorted((m for m in filtered if m.release_date), key=lambda m: m.release_date, reverse=True)
        without_date = [m for m in filtered if not m.release_date]
        return with_date + without_date

    if sort_key == "Note":
        rated = sorted((m for m in filtered if _rating_value(m) is not None), key=_rating_value, reverse=True)
        unrated = [m for m in filtered if _rating_value(m) is None]
        return rated + unrated

    raise ValueError(f"Tri inconnu : {sort_key}")


def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    state = {"query": "", "sort": SORT_OPTIONS[0]}

    with container:
        with ui.row().classes("w-full items-center gap-3 mb-4"):
            def _on_search(e) -> None:
                state["query"] = e.value
                _refresh()

            def _on_sort(e) -> None:
                state["sort"] = e.value
                _refresh()

            ui.input(placeholder="Rechercher un titre…", on_change=_on_search).classes("flex-grow")
            ui.select(SORT_OPTIONS, value=SORT_OPTIONS[0], label="Trier par", on_change=_on_sort).classes("w-48")

        grid_box = ui.column().classes("w-full")

        def _refresh() -> None:
            grid_box.clear()
            results = filter_and_sort_medias(ctx.state.all_medias, state["query"], state["sort"])
            with grid_box:
                if not results:
                    ui.label("Aucun résultat.").style("color:var(--text-muted)")
                else:
                    with ui.grid(columns=4).classes("w-full gap-3"):
                        for m in results:
                            media_card(m)

        _refresh()
```

- [ ] **Step 2: Wire the section into `frontend/ui.py`**

Change:

```python
from frontend.pages import ai as ai_page
from frontend.pages import dashboard, history, stats, wizard
```

to:

```python
from frontend.pages import ai as ai_page
from frontend.pages import dashboard, history, library, stats, wizard
```

Change:

```python
SECTIONS = [
    ("dashboard", "À traiter"),
    ("stats", "Statistiques"),
    ("history", "Historique"),
    ("ai", "Reco IA"),
]

PAGE_RENDERERS: Dict[str, Callable] = {
    "dashboard": dashboard.render,
    "wizard": wizard.render,
    "stats": stats.render,
    "history": history.render,
    "ai": ai_page.render,
}
```

to:

```python
SECTIONS = [
    ("dashboard", "À traiter"),
    ("library", "Bibliothèque"),
    ("stats", "Statistiques"),
    ("history", "Historique"),
    ("ai", "Reco IA"),
]

PAGE_RENDERERS: Dict[str, Callable] = {
    "dashboard": dashboard.render,
    "wizard": wizard.render,
    "library": library.render,
    "stats": stats.render,
    "history": history.render,
    "ai": ai_page.render,
}
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: all PASS (no existing test touches `ui.py` or `library.render`).

- [ ] **Step 4: Manual verification**

Run: `python main.py` (stop any other instance already bound to port 8080 first), then in a browser open `http://localhost:8080`:
1. Confirm the top bar is now ivory/white with a thin bottom border, not a dark block — check both in normal navigation and with the "Ajouter un film" dialog open (dashboard → "Ajouter un film").
2. Click the new "Bibliothèque" tab — confirm it lists every media currently in the local DB (not just the "à traiter" subset shown on the dashboard).
3. Type a partial title into the search box — confirm the grid filters live.
4. Switch the sort dropdown between Titre / Année / Note — confirm the order changes accordingly.
5. Clear the search box — confirm the full list returns.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/library.py frontend/ui.py
git commit -m "feat(frontend): add Bibliothèque section with search and sort"
```
