# Fiche film enrichie (note, avis, réalisateur, synopsis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show director, synopsis, genre, personal rating and review for each movie in the Backstage library, and let the user edit the rating/review from a detail dialog opened by clicking a card.

**Architecture:** `frontend/components.py` gains two pure helper functions (rating badge text, primary genre) plus an enriched `media_card` (new badges, optional `on_click`) and a new `open_media_detail_dialog(media, ctx)` function that renders a read-only info block and an editable rating/review form, saving via the existing `MediaStore.update()`. `frontend/pages/library.py` and `frontend/pages/dashboard.py` wire their card grids to open this dialog on click. `frontend/theme.py` gains one new CSS class for the secondary badges.

**Tech Stack:** Python, NiceGUI, Pydantic (`Media` model), sqlite3 (via `MediaStore`), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-07-fiche-film-bibliotheque-design.md`
- Only `rating` and `review` are editable in the detail dialog — no other field, no new DB columns.
- Rating stays a free-text field (e.g. `"8/10"`), no format validation, consistent with the existing "Ajouter un film" dialog.
- The compact card's genre badge shows only `media.categories[0]` (first category), never the full list.
- No new dependencies. Follow existing code style: small single-purpose files, `bs-*` CSS classes from `frontend/theme.py`, `ctx.store` / `ctx.reload()` from `AppContext`.

---

### Task 1: Pure helper functions for the card badges

**Files:**
- Modify: `frontend/components.py`
- Test: Create `tests/test_components.py`

**Interfaces:**
- Produces: `rating_badge_text(media: Any) -> Optional[str]` — returns `f"⭐ {media.rating}"` if `media.rating` is truthy, else `None`.
- Produces: `primary_genre(media: Any) -> Optional[str]` — returns `media.categories[0]` if `media.categories` is non-empty, else `None`.
- Consumes: `backend.core.models.Media` (only in tests, to build fixtures).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_components.py`:

```python
from backend.core.models import Media
from frontend.components import primary_genre, rating_badge_text


def _media(**overrides):
    fields = {"id": "1", "title": "Test"}
    fields.update(overrides)
    return Media(**fields)


def test_rating_badge_text_with_rating():
    assert rating_badge_text(_media(rating="8/10")) == "⭐ 8/10"


def test_rating_badge_text_without_rating():
    assert rating_badge_text(_media(rating=None)) is None


def test_primary_genre_with_categories():
    assert primary_genre(_media(categories=["Drame", "Thriller"])) == "Drame"


def test_primary_genre_without_categories():
    assert primary_genre(_media(categories=[])) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_components.py -v`
Expected: FAIL with `ImportError: cannot import name 'primary_genre'` (or similar, since the functions don't exist yet).

- [ ] **Step 3: Implement the helpers**

In `frontend/components.py`, add after the imports (keep existing `media_poster` and `media_card` below):

```python
def rating_badge_text(media: Any) -> Optional[str]:
    """Texte du badge note, ex. '⭐ 8/10', ou None si aucune note."""
    return f"⭐ {media.rating}" if media.rating else None


def primary_genre(media: Any) -> Optional[str]:
    """Première catégorie du média (genre principal), ou None si absente."""
    return media.categories[0] if media.categories else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_components.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/components.py tests/test_components.py
git commit -m "feat: add rating/genre badge helpers for media cards"
```

---

### Task 2: Secondary badge CSS class

**Files:**
- Modify: `frontend/theme.py`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Produces: CSS class `.bs-badge-secondary` (background `var(--border)`, text `var(--text)`), for the rating/genre badges added in Task 3, distinct in weight from the existing accent-colored `.bs-badge`.

- [ ] **Step 1: Write the failing test**

In `tests/test_theme.py`, extend the class tuple in `test_build_theme_css_defines_component_classes`:

```python
def test_build_theme_css_defines_component_classes():
    css = build_theme_css()
    for class_name in (".bs-card", ".bs-title", ".bs-accent-btn", ".bs-outline-btn",
                       ".bs-badge", ".bs-badge-secondary", ".bs-poster-placeholder",
                       ".bs-topbar", ".bs-navlink"):
        assert class_name in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py::test_build_theme_css_defines_component_classes -v`
Expected: FAIL — `.bs-badge-secondary` not found in the generated CSS.

- [ ] **Step 3: Add the CSS class**

In `frontend/theme.py`, inside the existing `@layer theme {{ ... }}` block, right after the `.q-badge.bs-badge` line:

```python
.q-badge.bs-badge {{ background: var(--accent) !important; color: var(--bg) !important; }}
.q-badge.bs-badge-secondary {{ background: var(--border) !important; color: var(--text) !important; }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/theme.py tests/test_theme.py
git commit -m "feat: add secondary badge style for card rating/genre badges"
```

---

### Task 3: Enrich `media_card` with badges and click support

**Files:**
- Modify: `frontend/components.py`

**Interfaces:**
- Consumes: `rating_badge_text`, `primary_genre` (Task 1); CSS class `.bs-badge-secondary` (Task 2).
- Produces: `media_card(media: Any, *, on_click: Optional[Callable[[], None]] = None) -> None` — same rendering as before, plus a row of secondary badges (rating, genre) when present, plus click support (`cursor-pointer` class and a `click` event bound to `on_click`) when `on_click` is provided. Existing callers (`media_card(m)`) keep working unchanged since `on_click` defaults to `None`.

- [ ] **Step 1: Update `media_card`**

In `frontend/components.py`, update the import line and replace `media_card`:

```python
from typing import Any, Callable, Optional
```

```python
def media_card(media: Any, *, on_click: Optional[Callable[[], None]] = None) -> None:
    """Carte poster + titre + badges année/type/note/genre, partagée par le dashboard et la bibliothèque."""
    card = ui.element("div").classes("bs-card p-2")
    if on_click is not None:
        card.classes("cursor-pointer").on("click", on_click)
    with card:
        media_poster(media.cover_url, height="140px")
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")

        rating_text = rating_badge_text(media)
        genre_text = primary_genre(media)
        if rating_text or genre_text:
            with ui.row().classes("gap-1 mt-1"):
                if rating_text:
                    ui.badge(rating_text).classes("bs-badge-secondary")
                if genre_text:
                    ui.badge(genre_text).classes("bs-badge-secondary")
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all tests pass (existing callers `media_card(m)` in `dashboard.py`/`library.py` still work — `on_click` is optional).

- [ ] **Step 3: Commit**

```bash
git add frontend/components.py
git commit -m "feat: show rating/genre badges on media cards and support click"
```

---

### Task 4: Detail dialog with editable rating/review

**Files:**
- Modify: `frontend/components.py`

**Interfaces:**
- Consumes: `frontend.context.AppContext` (`ctx.store.update(media_id, fields) -> Awaitable[bool]`, `ctx.reload() -> Awaitable[None]`); `media_poster` (existing).
- Produces: `open_media_detail_dialog(media: Any, ctx: AppContext) -> None` — opens a NiceGUI dialog showing poster, title, year/type badge, director, genres, synopsis (read-only), plus editable "Note /10" input and "Avis" textarea pre-filled from `media.rating` / `media.review`, with "Enregistrer" (saves via `ctx.store.update` then `ctx.reload()`, closes dialog, shows a positive notification) and "Fermer" (closes without saving) buttons.

- [ ] **Step 1: Add the import**

In `frontend/components.py`, add near the top (after the `nicegui` import):

```python
from frontend.context import AppContext
```

- [ ] **Step 2: Implement `open_media_detail_dialog`**

Append to `frontend/components.py`:

```python
def open_media_detail_dialog(media: Any, ctx: AppContext) -> None:
    """Fiche détaillée d'un média : infos en lecture seule + note/avis éditables."""
    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("bs-card w-full max-w-2xl p-6"):
        with ui.row().classes("w-full gap-4 items-start"):
            media_poster(media.cover_url, height="220px")
            with ui.column().classes("gap-1"):
                ui.label(media.title).classes("bs-title text-lg")
                year = media.release_date.year if media.release_date else "—"
                ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge")
                ui.label(f"Réalisateur : {media.director or '—'}").classes("text-sm mt-2")
                genres = ", ".join(media.categories) if media.categories else "—"
                ui.label(f"Genre : {genres}").classes("text-sm")

        ui.label("Synopsis").classes("bs-title text-sm mt-4")
        ui.label(media.synopsis or "—").classes("text-sm").style("color:var(--text-muted)")

        ui.label("Votre note et avis").classes("bs-title text-sm mt-4")
        rating_input = ui.input("Note /10", value=media.rating or "").classes("w-full")
        review_input = ui.textarea("Avis", value=media.review or "").classes("w-full")

        async def _save() -> None:
            await ctx.store.update(media.id, {
                "rating": (rating_input.value or "").strip() or None,
                "review": (review_input.value or "").strip() or None,
            })
            ui.notify(f"« {media.title} » mis à jour.", type="positive")
            dialog.close()
            await ctx.reload()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Fermer", on_click=dialog.close).classes("bs-outline-btn")
            ui.button("Enregistrer", on_click=_save).classes("bs-accent-btn")

    dialog.open()
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all tests pass (no test targets this function directly — it's NiceGUI UI code with no headless test harness in this project, consistent with the rest of `frontend/`; Task 5's manual verification covers it).

- [ ] **Step 4: Commit**

```bash
git add frontend/components.py
git commit -m "feat: add editable movie detail dialog"
```

---

### Task 5: Wire click-to-open-detail on both card grids

**Files:**
- Modify: `frontend/pages/library.py:1-8,66-68`
- Modify: `frontend/pages/dashboard.py:1-8,46-48`

**Interfaces:**
- Consumes: `media_card(media, *, on_click=None)` (Task 3), `open_media_detail_dialog(media, ctx)` (Task 4).

- [ ] **Step 1: Wire the library grid**

In `frontend/pages/library.py`, update the import line:

```python
from frontend.components import media_card, open_media_detail_dialog
```

And update the render loop (inside `_refresh`):

```python
                    with ui.grid(columns=4).classes("w-full gap-3"):
                        for m in results:
                            media_card(m, on_click=lambda m=m: open_media_detail_dialog(m, ctx))
```

- [ ] **Step 2: Wire the dashboard grid**

In `frontend/pages/dashboard.py`, update the import line:

```python
from frontend.components import media_card, media_poster, open_media_detail_dialog
```

And update the render loop in `_render_dashboard`:

```python
    with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
        for m in medias:
            media_card(m, on_click=lambda m=m: open_media_detail_dialog(m, ctx))
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/library.py frontend/pages/dashboard.py
git commit -m "feat: open movie detail dialog on card click"
```

---

### Task 6: Manual verification

**Files:** none (manual browser check).

- [ ] **Step 1: Start the app in dev mode**

Run: `BACKSTAGE_DEV=1 python main.py` (or on Windows PowerShell: `$env:BACKSTAGE_DEV=1; python main.py`)
Expected: server starts on `http://localhost:8080` without errors.

- [ ] **Step 2: Check the Bibliothèque grid**

Open `http://localhost:8080`, go to "Bibliothèque". For a movie that has a rating and at least one category set, confirm the card shows the new rating (⭐) and genre badges below the year/type badge. For a movie with neither, confirm no extra badges appear (no empty badges).

- [ ] **Step 3: Open and edit the detail dialog**

Click a card. Confirm the dialog shows poster, title, year/type, réalisateur, genre, synopsis, and pre-filled "Note /10" / "Avis" fields. Change the rating and avis, click "Enregistrer". Confirm a success notification appears, the dialog closes, and the card's rating badge reflects the new value after the page refresh.

- [ ] **Step 4: Confirm "Fermer" discards changes**

Click a card, change the rating field, click "Fermer" instead of "Enregistrer". Confirm the value shown on the card is unchanged (no update was persisted).

- [ ] **Step 5: Check the Dashboard grid**

Go to "À traiter" (dashboard). Confirm cards there also show the rating/genre badges and open the same detail dialog on click.

- [ ] **Step 6: Stop the dev server**

Stop the `python main.py` process (Ctrl+C).
