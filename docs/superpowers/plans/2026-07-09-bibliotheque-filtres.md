# Filtres bibliothèque (Genre / Statut / Support) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Filtrer" control to the library page (`frontend/pages/library.py`) that lets the user narrow the movie grid by genre, status, and support, combined with the existing search and sort.

**Architecture:** Two new pure functions (`distinct_filter_options`, `apply_filters`) handle the filtering logic and are unit-tested in isolation, exactly like the existing `filter_and_sort_medias`/`paginate_medias` functions. `filter_and_sort_medias` gains an optional `filters` parameter so existing callers/tests are unaffected. The UI adds a "Filtrer" button that opens a `ui.menu` with three multi-select dropdowns, wired to `state["filters"]` (persisted in `ctx.state.ui_state["library"]`, same mechanism as `query`/`sort`/`page`).

**Tech Stack:** Python, NiceGUI (`ui.menu`, `ui.select` with `multiple=True`), pytest.

## Global Constraints

- Filter options (genre/status/support values) are derived dynamically from `ctx.state.all_medias` — no hardcoded value lists.
- Within one filter dimension: OR logic (any selected value matches). Across dimensions (genre/status/support/search): AND logic.
- Selecting/clearing filters resets `state["page"]` to 1, matching existing search/sort behavior.
- `filter_and_sort_medias`'s existing signature must stay backward-compatible (`filters` is optional, defaults to no-op) so all 12 existing tests in `tests/test_library.py` keep passing unmodified except the one asserting the exact default state shape (Task 3 updates that one deliberately).

---

### Task 1: `distinct_filter_options` helper

**Files:**
- Modify: `frontend/pages/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Produces: `distinct_filter_options(medias: List[Media], field: str) -> List[str]` — for `field="categories"` flattens each media's `categories` list; for any other field (`"status"`, `"support"`) collects `getattr(m, field)`, skipping falsy values. Returns a sorted list of unique values (French locale default `sorted()` is fine — no accent-aware ordering required by the spec).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_library.py`:

```python
from frontend.pages.library import distinct_filter_options


def test_distinct_filter_options_categories_flattened_and_sorted():
    medias = [
        _media("A", categories=["Drame", "Action"]),
        _media("B", categories=["Comédie"]),
        _media("C", categories=["Action"]),
    ]
    assert distinct_filter_options(medias, "categories") == ["Action", "Comédie", "Drame"]


def test_distinct_filter_options_status_skips_missing():
    medias = [_media("A", status="Terminé"), _media("B", status=None), _media("C", status="À revoir")]
    assert distinct_filter_options(medias, "status") == ["Terminé", "À revoir"] or \
        distinct_filter_options(medias, "status") == sorted(["Terminé", "À revoir"])


def test_distinct_filter_options_empty_list():
    assert distinct_filter_options([], "categories") == []
```

Update the `_media` helper at the top of `tests/test_library.py` to accept the new fields used above:

```python
def _media(title, release_date=None, rating=None, categories=None, status=None, support=None):
    return Media(
        id=title,
        title=title,
        release_date=release_date,
        rating=rating,
        categories=categories or [],
        status=status,
        support=support,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library.py -k distinct_filter_options -v`
Expected: FAIL with `ImportError: cannot import name 'distinct_filter_options'`

- [ ] **Step 3: Implement `distinct_filter_options`**

In `frontend/pages/library.py`, add after the imports (near the top, before `_rating_value`):

```python
def distinct_filter_options(medias: List[Media], field: str) -> List[str]:
    if field == "categories":
        values = {c for m in medias for c in m.categories}
    else:
        values = {getattr(m, field) for m in medias if getattr(m, field)}
    return sorted(values)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_library.py -k distinct_filter_options -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/library.py tests/test_library.py
git commit -m "feat: add distinct_filter_options helper for library filters"
```

---

### Task 2: `apply_filters` pure filtering function

**Files:**
- Modify: `frontend/pages/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: `Media` model fields `categories: List[str]`, `status: Optional[str]`, `support: Optional[str]`.
- Produces: `apply_filters(medias: List[Media], filters: Dict[str, List[str]]) -> List[Media]`. `filters` has keys `"genres"`, `"statuses"`, `"supports"`, each a list of selected values (possibly empty). A media passes if, for every non-empty key, at least one of its own values matches one of the selected values (OR within a dimension). Empty/missing key = dimension not filtered.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_library.py`:

```python
from frontend.pages.library import apply_filters


def test_apply_filters_no_filters_returns_all():
    medias = [_media("A"), _media("B")]
    result = apply_filters(medias, {"genres": [], "statuses": [], "supports": []})
    assert result == medias


def test_apply_filters_genre_or_logic():
    medias = [
        _media("A", categories=["Action"]),
        _media("B", categories=["Comédie"]),
        _media("C", categories=["Drame"]),
    ]
    result = apply_filters(medias, {"genres": ["Action", "Comédie"], "statuses": [], "supports": []})
    assert [m.title for m in result] == ["A", "B"]


def test_apply_filters_status_exact_match():
    medias = [_media("A", status="Terminé"), _media("B", status="À revoir")]
    result = apply_filters(medias, {"genres": [], "statuses": ["Terminé"], "supports": []})
    assert [m.title for m in result] == ["A"]


def test_apply_filters_support_exact_match():
    medias = [_media("A", support="NAS"), _media("B", support="Cinéma")]
    result = apply_filters(medias, {"genres": [], "statuses": [], "supports": ["NAS"]})
    assert [m.title for m in result] == ["A"]


def test_apply_filters_and_logic_across_dimensions():
    medias = [
        _media("A", categories=["Action"], status="Terminé"),
        _media("B", categories=["Action"], status="À revoir"),
        _media("C", categories=["Drame"], status="Terminé"),
    ]
    result = apply_filters(medias, {"genres": ["Action"], "statuses": ["Terminé"], "supports": []})
    assert [m.title for m in result] == ["A"]


def test_apply_filters_missing_dimension_key_treated_as_empty():
    medias = [_media("A"), _media("B")]
    assert apply_filters(medias, {}) == medias
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library.py -k apply_filters -v`
Expected: FAIL with `ImportError: cannot import name 'apply_filters'`

- [ ] **Step 3: Implement `apply_filters`**

In `frontend/pages/library.py`, add directly after `distinct_filter_options`:

```python
def apply_filters(medias: List[Media], filters: Dict[str, List[str]]) -> List[Media]:
    genres = set(filters.get("genres") or [])
    statuses = set(filters.get("statuses") or [])
    supports = set(filters.get("supports") or [])

    def _matches(m: Media) -> bool:
        if genres and not (set(m.categories) & genres):
            return False
        if statuses and m.status not in statuses:
            return False
        if supports and m.support not in supports:
            return False
        return True

    return [m for m in medias if _matches(m)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_library.py -k apply_filters -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/library.py tests/test_library.py
git commit -m "feat: add apply_filters for genre/status/support library filtering"
```

---

### Task 3: Wire filters into `get_library_state` and `filter_and_sort_medias`

**Files:**
- Modify: `frontend/pages/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: `apply_filters` from Task 2.
- Produces: `get_library_state(ui_state) -> Dict[str, Any]` now defaults to `{"query": "", "sort": SORT_OPTIONS[0], "page": 1, "filters": {"genres": [], "statuses": [], "supports": []}}`. `filter_and_sort_medias(medias, query, sort_key, filters=None)` applies `apply_filters` (when `filters` is truthy) between the text-search step and the sort step.

- [ ] **Step 1: Update the existing default-state test and add new tests**

In `tests/test_library.py`, replace `test_get_library_state_defaults_on_first_call`:

```python
def test_get_library_state_defaults_on_first_call():
    ui_state = {}
    state = get_library_state(ui_state)
    assert state == {
        "query": "",
        "sort": "Titre",
        "page": 1,
        "filters": {"genres": [], "statuses": [], "supports": []},
    }
```

Add new tests for the combined behavior:

```python
def test_filter_and_sort_medias_applies_filters_before_sort():
    medias = [
        _media("Zeta", categories=["Action"]),
        _media("Alpha", categories=["Action"]),
        _media("Beta", categories=["Drame"]),
    ]
    result = filter_and_sort_medias(medias, "", "Titre", filters={"genres": ["Action"], "statuses": [], "supports": []})
    assert [m.title for m in result] == ["Alpha", "Zeta"]


def test_filter_and_sort_medias_combines_search_and_filters():
    medias = [
        _media("Blade Runner", categories=["Science-Fiction"]),
        _media("Blade of Glory", categories=["Comédie"]),
    ]
    result = filter_and_sort_medias(medias, "blade", "Titre", filters={"genres": ["Comédie"], "statuses": [], "supports": []})
    assert [m.title for m in result] == ["Blade of Glory"]


def test_filter_and_sort_medias_no_filters_arg_behaves_as_before():
    medias = [_media("B"), _media("A")]
    result = filter_and_sort_medias(medias, "", "Titre")
    assert [m.title for m in result] == ["A", "B"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library.py -v`
Expected: `test_get_library_state_defaults_on_first_call` fails (missing `filters` key); the two new `filter_and_sort_medias` filter tests fail with `TypeError: filter_and_sort_medias() got an unexpected keyword argument 'filters'`.

- [ ] **Step 3: Implement the changes**

In `frontend/pages/library.py`, update `get_library_state`:

```python
def get_library_state(ui_state: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return ui_state.setdefault("library", {
        "query": "",
        "sort": SORT_OPTIONS[0],
        "page": 1,
        "filters": {"genres": [], "statuses": [], "supports": []},
    })
```

Update `filter_and_sort_medias` signature and body (insert the `apply_filters` call between the text-search filter and the `if sort_key == "Titre":` block):

```python
def filter_and_sort_medias(
    medias: List[Media],
    query: str,
    sort_key: str,
    filters: Optional[Dict[str, List[str]]] = None,
) -> List[Media]:
    query_norm = (query or "").strip().lower()
    filtered = [m for m in medias if query_norm in m.title.lower()] if query_norm else list(medias)

    if filters:
        filtered = apply_filters(filtered, filters)

    if sort_key == "Titre":
        return sorted(filtered, key=lambda m: m.title.lower())
    ...
```

(Keep the rest of the function body — the `"Année"`, `"Note"`, `"Date d'ajout"`, and `raise ValueError` branches — unchanged, just operating on the now-filtered `filtered` list.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_library.py -v`
Expected: all tests pass (26 tests after Task 1+2 [17 original + 3 + 6], plus 3 new tests here = 29 total; `test_get_library_state_defaults_on_first_call` is updated in place, not added)

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/library.py tests/test_library.py
git commit -m "feat: wire filters into get_library_state and filter_and_sort_medias"
```

---

### Task 4: "Filtrer" UI — button, menu, and wiring in `render()`

**Files:**
- Modify: `frontend/pages/library.py`

**Interfaces:**
- Consumes: `distinct_filter_options`, `apply_filters` (via `filter_and_sort_medias`'s `filters` param), `get_library_state`, `ctx.state.all_medias`, `ctx.state.ui_state` (all pre-existing/Task 1-3).
- Produces: no new importable symbols — this is the UI wiring inside `render()`.

- [ ] **Step 1: Compute filter options and read persisted filter state**

In `frontend/pages/library.py`, inside `render()`, right after `state = get_library_state(ctx.state.ui_state)` (currently line 63), add:

```python
    genre_options = distinct_filter_options(ctx.state.all_medias, "categories")
    status_options = distinct_filter_options(ctx.state.all_medias, "status")
    support_options = distinct_filter_options(ctx.state.all_medias, "support")
```

- [ ] **Step 2: Add the "Filtrer" button and menu to the top row**

The current top row (lines 65-86) is:

```python
        with ui.row().classes("w-full items-center gap-3 mb-4"):
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

            def _on_sort(e) -> None:
                state["sort"] = e.value
                state["page"] = 1
                _refresh()

            ui.input(placeholder="Rechercher un titre…", value=state["query"], on_change=_on_search).classes("flex-grow")
            ui.select(SORT_OPTIONS, value=state["sort"], label="Trier par", on_change=_on_sort).classes("w-48")
```

Replace it with (adds the filter button/menu after the sort select, using `_refresh` which is defined later in the function — Python closures resolve this at call time, matching the existing `_on_search`/`_on_sort` pattern):

```python
        with ui.row().classes("w-full items-center gap-3 mb-4"):
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

            def _on_sort(e) -> None:
                state["sort"] = e.value
                state["page"] = 1
                _refresh()

            ui.input(placeholder="Rechercher un titre…", value=state["query"], on_change=_on_search).classes("flex-grow")
            ui.select(SORT_OPTIONS, value=state["sort"], label="Trier par", on_change=_on_sort).classes("w-48")

            def _filter_button_label() -> str:
                count = sum(len(v) for v in state["filters"].values())
                return f"Filtrer ({count})" if count else "Filtrer"

            filter_button = ui.button(_filter_button_label(), icon="filter_list").props("flat")

            with ui.menu() as filter_menu:
                with ui.column().classes("p-4 gap-3").style("min-width:280px"):
                    genre_select = ui.select(
                        genre_options, multiple=True, label="Genre",
                        value=list(state["filters"]["genres"]),
                    ).classes("w-full").props("use-chips")
                    status_select = ui.select(
                        status_options, multiple=True, label="Statut",
                        value=list(state["filters"]["statuses"]),
                    ).classes("w-full").props("use-chips")
                    support_select = ui.select(
                        support_options, multiple=True, label="Support",
                        value=list(state["filters"]["supports"]),
                    ).classes("w-full").props("use-chips")

                    def _apply_filter_selection() -> None:
                        state["filters"]["genres"] = genre_select.value or []
                        state["filters"]["statuses"] = status_select.value or []
                        state["filters"]["supports"] = support_select.value or []
                        state["page"] = 1
                        filter_button.set_text(_filter_button_label())
                        filter_menu.close()
                        _refresh()

                    def _reset_filter_selection() -> None:
                        genre_select.value = []
                        status_select.value = []
                        support_select.value = []
                        _apply_filter_selection()

                    with ui.row().classes("w-full justify-between mt-2"):
                        ui.button("Réinitialiser", on_click=_reset_filter_selection).classes("bs-outline-btn")
                        ui.button("Appliquer", on_click=_apply_filter_selection).classes("bs-accent-btn")

            filter_button.on("click", filter_menu.open)
```

- [ ] **Step 3: Pass filters into `filter_and_sort_medias` inside `_refresh`**

In `_refresh()` (around what is currently line 98), change:

```python
            results = filter_and_sort_medias(ctx.state.all_medias, state["query"], state["sort"])
```

to:

```python
            results = filter_and_sort_medias(ctx.state.all_medias, state["query"], state["sort"], filters=state["filters"])
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest tests/test_library.py -v`
Expected: all tests still pass (this task only touches UI wiring, no new pure-function tests — `render()` has no existing unit tests per the codebase's established pattern of only testing pure functions).

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/library.py
git commit -m "feat: add Filtrer button and menu to library page"
```

---

### Task 5: Manual verification in the browser

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass, no regressions.

- [ ] **Step 2: Start the dev server**

Run: `python main.py`
Expected: server starts on `http://localhost:8090` (or `$PORT` if set).

- [ ] **Step 3: Exercise the feature live**

Using the `run` skill or a browser:
1. Navigate to the "Bibliothèque" page.
2. Click "Filtrer" — the menu opens with Genre/Statut/Support multi-selects populated from real data.
3. Select one genre (e.g. "Action") and click "Appliquer" — grid updates to only show Action films, button label shows "Filtrer (1)", page resets to 1.
4. Add a status filter too — grid narrows further (AND across dimensions).
5. Select two genres — grid shows films matching either (OR within dimension).
6. Combine with the search box — results respect both search and filters.
7. Click "Filtrer" → "Réinitialiser" — all filters clear, button label reverts to "Filtrer", full grid returns.
8. Change page, then reopen the page (e.g. navigate away and back) — confirm filters persist via `ctx.state.ui_state`, matching existing sort/search persistence behavior.

- [ ] **Step 4: Report results**

Confirm in conversation that all 8 manual checks passed, or note any deviations found.
