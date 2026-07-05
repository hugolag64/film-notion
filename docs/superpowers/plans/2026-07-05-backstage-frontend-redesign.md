# Backstage Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Backstage's generic "SaaS" NiceGUI interface with an editorial "Ivoire & Bordeaux" cinema design, split across dedicated page modules, per `docs/superpowers/specs/2026-07-05-refonte-graphique-backstage-design.md`.

**Architecture:** `frontend/theme.py` centralizes design tokens as CSS custom properties. `frontend/ui.py` becomes a thin orchestrator (top bar + section routing) that delegates rendering to `frontend/pages/{dashboard,wizard,stats,history,ai}.py`, all sharing a small `AppContext` dataclass and `frontend/components.py` helpers. Backend (`backend/core/*`) is untouched except one additive function.

**Tech Stack:** Python 3.13, NiceGUI 3.6.1 (Quasar/ECharts bundled, no new frontend dependency needed — `ui.echart` ships with NiceGUI), pytest 9.0.3.

## Global Constraints

- No new pip dependencies — `ui.echart` (verified present on the installed NiceGUI 3.6.1) covers all chart needs.
- `backend/core/*` behavior is unchanged except the additive `compute_enrichment_progression` function in `backend/core/stats.py` — no existing function signature changes.
- Design tokens must match the spec exactly: `--bg:#faf6ef; --surface:#ffffff; --border:#ece4d6; --text:#2b2420; --text-muted:#8a8578; --accent:#7a2331; --accent-gold:#c9a35c; --font-display:Georgia,'Times New Roman',serif; --font-body:Arial,Helvetica,sans-serif; --radius:10px`.
- No dark mode toggle is implemented now — only CSS variables that a future toggle could swap.
- Tests follow existing conventions: `pytest`, files under `tests/`, `python_files = test_*.py` (see `pytest.ini`).
- NiceGUI page-rendering code has no automated test harness in this repo (only `backend/core/*` has unit tests today). Pure-logic extractions (timestamp formatting, stats aggregation, CSS token building) get real pytest tests; anything that only builds NiceGUI elements is verified manually with the exact steps listed in each task — this is a deliberate scope decision, not a gap.
- Commit after each task.

---

### Task 1: Design tokens module (`frontend/theme.py`)

**Files:**
- Create: `frontend/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: `TOKENS: Dict[str, str]`, `build_theme_css() -> str` (pure, no NiceGUI import), `apply_theme() -> None` (imports `nicegui.ui`, calls `ui.add_head_html(build_theme_css())`). Later tasks call `apply_theme()` from `frontend/ui.py` and use the CSS classes it defines: `bs-card`, `bs-title`, `bs-accent-btn`, `bs-outline-btn`, `bs-badge`, `bs-poster-placeholder`, `bs-topbar`, `bs-navlink` (with `.active` modifier).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py
from frontend.theme import TOKENS, build_theme_css


def test_tokens_match_spec():
    assert TOKENS["--bg"] == "#faf6ef"
    assert TOKENS["--accent"] == "#7a2331"
    assert TOKENS["--accent-gold"] == "#c9a35c"
    assert TOKENS["--text"] == "#2b2420"


def test_build_theme_css_declares_all_tokens():
    css = build_theme_css()
    assert css.strip().startswith("<style>")
    for name, value in TOKENS.items():
        assert f"{name}: {value};" in css


def test_build_theme_css_defines_component_classes():
    css = build_theme_css()
    for class_name in (".bs-card", ".bs-title", ".bs-accent-btn", ".bs-outline-btn",
                       ".bs-badge", ".bs-poster-placeholder", ".bs-topbar", ".bs-navlink"):
        assert class_name in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'frontend.theme'`

- [ ] **Step 3: Write the implementation**

```python
# frontend/theme.py
TOKENS = {
    "--bg": "#faf6ef",
    "--surface": "#ffffff",
    "--border": "#ece4d6",
    "--text": "#2b2420",
    "--text-muted": "#8a8578",
    "--accent": "#7a2331",
    "--accent-gold": "#c9a35c",
    "--font-display": "Georgia, 'Times New Roman', serif",
    "--font-body": "Arial, Helvetica, sans-serif",
    "--radius": "10px",
}


def build_theme_css() -> str:
    variables = "\n".join(f"  {name}: {value};" for name, value in TOKENS.items())
    return f"""<style>
:root {{
{variables}
}}
body {{ background-color: var(--bg); font-family: var(--font-body); color: var(--text); }}
.bs-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 2px 10px rgba(43, 36, 32, 0.05);
  transition: border-color 0.15s ease;
}}
.bs-card:hover {{ border-color: var(--accent); }}
.bs-title {{ font-family: var(--font-display); color: var(--text); font-weight: 700; }}
.bs-accent-btn {{
  background: var(--accent) !important;
  color: var(--bg) !important;
  border-radius: 999px !important;
  font-family: var(--font-body);
}}
.bs-outline-btn {{
  border: 1px solid var(--accent) !important;
  color: var(--accent) !important;
  border-radius: 999px !important;
  background: transparent !important;
  font-family: var(--font-body);
}}
.bs-badge {{ background: var(--accent) !important; color: var(--bg) !important; }}
.bs-poster-placeholder {{
  background: linear-gradient(135deg, var(--border), var(--accent-gold));
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
}}
.bs-topbar {{ background: var(--text); color: var(--bg); }}
.bs-navlink {{ color: var(--bg) !important; opacity: 0.75; font-size: 0.85rem; }}
.bs-navlink.active {{ opacity: 1; border-bottom: 2px solid var(--accent-gold); }}
</style>
"""


def apply_theme() -> None:
    from nicegui import ui
    ui.add_head_html(build_theme_css())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/theme.py tests/test_theme.py
git commit -m "feat(frontend): add Ivoire & Bordeaux design tokens module"
```

---

### Task 2: Relative timestamp formatting (`frontend/format_utils.py`)

**Files:**
- Create: `frontend/format_utils.py`
- Test: `tests/test_format_utils.py`

**Interfaces:**
- Produces: `format_relative_timestamp(ts_iso: str, now: Optional[datetime] = None) -> str`. Consumed by Task 6 (`frontend/pages/history.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_format_utils.py
from datetime import datetime, timezone

from frontend.format_utils import format_relative_timestamp

NOW = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)


def test_less_than_a_minute_ago():
    ts = "2026-07-05T21:29:45+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "à l'instant"


def test_minutes_ago():
    ts = "2026-07-05T21:26:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "il y a 4 min"


def test_same_day_over_an_hour_ago():
    ts = "2026-07-05T09:14:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "aujourd'hui à 09:14"


def test_yesterday():
    ts = "2026-07-04T21:14:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "hier à 21:14"


def test_older_than_yesterday():
    ts = "2026-06-20T10:00:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "20/06/2026 à 10:00"


def test_naive_iso_timestamp_is_treated_as_utc():
    ts = "2026-07-05T21:26:00"
    assert format_relative_timestamp(ts, now=NOW) == "il y a 4 min"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_format_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'frontend.format_utils'`

- [ ] **Step 3: Write the implementation**

```python
# frontend/format_utils.py
from datetime import datetime, timezone
from typing import Optional


def format_relative_timestamp(ts_iso: str, now: Optional[datetime] = None) -> str:
    """Formate un timestamp ISO en libellé relatif court pour la timeline Historique."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    ts = datetime.fromisoformat(ts_iso)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    seconds = (now - ts).total_seconds()

    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {int(seconds // 60)} min"

    time_str = ts.strftime("%H:%M")
    day_delta = (now.date() - ts.date()).days
    if day_delta == 0:
        return f"aujourd'hui à {time_str}"
    if day_delta == 1:
        return f"hier à {time_str}"
    return ts.strftime("%d/%m/%Y à %H:%M")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_format_utils.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/format_utils.py tests/test_format_utils.py
git commit -m "feat(frontend): add relative timestamp formatter for history timeline"
```

---

### Task 3: Enrichment progression aggregation (`backend/core/stats.py`)

**Files:**
- Modify: `backend/core/stats.py` (append function, no changes to existing functions)
- Test: `tests/test_stats.py` (append tests, no changes to existing tests)

**Interfaces:**
- Produces: `compute_enrichment_progression(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]`, each item `{"date": "YYYY-MM-DD", "cumulative": int}`, sorted ascending by date. Consumed by Task 5 (`frontend/pages/stats.py`), fed with `backend.core.history.read_recent(limit=100000)`.

- [ ] **Step 1: Write the failing test**

```python
# appended to tests/test_stats.py
from backend.core.stats import compute_enrichment_progression


def test_compute_enrichment_progression_cumulative_by_day():
    entries = [
        {"ts": "2026-07-01T10:00:00+00:00"},
        {"ts": "2026-07-01T18:00:00+00:00"},
        {"ts": "2026-07-03T09:00:00+00:00"},
    ]
    progression = compute_enrichment_progression(entries)
    assert progression == [
        {"date": "2026-07-01", "cumulative": 2},
        {"date": "2026-07-03", "cumulative": 3},
    ]


def test_compute_enrichment_progression_empty():
    assert compute_enrichment_progression([]) == []


def test_compute_enrichment_progression_ignores_entries_without_ts():
    entries = [{"ts": ""}, {"ts": "2026-07-01T10:00:00+00:00"}]
    progression = compute_enrichment_progression(entries)
    assert progression == [{"date": "2026-07-01", "cumulative": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats.py -v -k progression`
Expected: FAIL with `ImportError: cannot import name 'compute_enrichment_progression'`

- [ ] **Step 3: Write the implementation**

```python
# appended to backend/core/stats.py
def compute_enrichment_progression(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Progression cumulée du nombre de fiches enrichies, groupée par jour (à partir de history.jsonl)."""
    by_day = Counter()
    for e in entries:
        day = (e.get("ts") or "")[:10]
        if day:
            by_day[day] += 1

    cumulative = 0
    progression = []
    for day in sorted(by_day):
        cumulative += by_day[day]
        progression.append({"date": day, "cumulative": cumulative})
    return progression
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stats.py -v`
Expected: all passed (existing 3 + new 3)

- [ ] **Step 5: Commit**

```bash
git add backend/core/stats.py tests/test_stats.py
git commit -m "feat(stats): add enrichment progression aggregation for stats dashboard"
```

---

### Task 4: Orchestrator, shared context/components, Dashboard and Wizard (core workflow)

This is the largest task: it replaces `frontend/ui.py` with the new top-bar orchestrator and ships the two pages that make up Backstage's primary workflow (browse the to-do list, launch enrichment, resolve ambiguities). It has no isolated pytest step (no NiceGUI test harness in this repo, see Global Constraints) — verification is the manual walkthrough in Step 6.

**Files:**
- Create: `frontend/context.py`
- Create: `frontend/components.py`
- Create: `frontend/pages/__init__.py` (empty)
- Create: `frontend/pages/dashboard.py`
- Create: `frontend/pages/wizard.py`
- Modify: `frontend/ui.py` (full rewrite, replaces the current monolithic 416-line file)

**Interfaces:**
- Produces: `AppState` (dataclass: `all_medias`, `medias`, `force`, `running`), `AppContext` (dataclass: `processor: EnrichmentProcessor`, `state: AppState`, `reload: Callable[[], Awaitable[None]]`, `rerender: Callable[[], None]`, `navigate: Callable[[str], None]`), `media_poster(cover_url: Optional[str], *, height: str = "160px") -> None`, `dashboard.render(container: ui.element, ctx: AppContext) -> None`, `wizard.render(container: ui.element, ctx: AppContext) -> None` (async).
- Consumes: `frontend.theme.apply_theme` (Task 1).

- [ ] **Step 1: Create the shared context**

```python
# frontend/context.py
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List

from backend.core.processor import EnrichmentProcessor


@dataclass
class AppState:
    all_medias: List[Any] = field(default_factory=list)
    medias: List[Any] = field(default_factory=list)
    force: bool = False
    running: bool = False


@dataclass
class AppContext:
    processor: EnrichmentProcessor
    state: AppState
    reload: Callable[[], Awaitable[None]]
    rerender: Callable[[], None]
    navigate: Callable[[str], None]
```

- [ ] **Step 2: Create shared poster/placeholder component**

```python
# frontend/components.py
from typing import Optional

from nicegui import ui


def media_poster(cover_url: Optional[str], *, height: str = "160px") -> None:
    """Affiche le poster TMDB si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if cover_url:
        ui.image(cover_url).classes("rounded w-full").style(f"height:{height}; object-fit:cover;")
    else:
        with ui.element("div").classes("bs-poster-placeholder w-full").style(f"height:{height};"):
            ui.icon("movie", size="2rem").classes("opacity-70")
```

- [ ] **Step 3: Create the pages package and Dashboard page**

```python
# frontend/pages/__init__.py
```

```python
# frontend/pages/dashboard.py
from typing import Any

from nicegui import ui

from frontend.components import media_poster
from frontend.context import AppContext


def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    with container:
        _render_dashboard(ctx)


def _render_dashboard(ctx: AppContext) -> None:
    medias = ctx.state.medias

    if not medias:
        with ui.column().classes("w-full items-center justify-center py-16 opacity-70"):
            ui.icon("check_circle", size="5rem").style("color:var(--accent-gold)")
            ui.label("Tout est à jour !").classes("bs-title text-xl mt-4")
        _force_switch(ctx)
        return

    with ui.row().classes("w-full items-center justify-between mb-4"):
        with ui.column().classes("gap-0"):
            ui.label(f"{len(medias)} fiche(s) en attente").classes("bs-title text-lg")
            ui.label("Prêt à enrichir").classes("text-xs").style("color:var(--text-muted)")
        with ui.row().classes("gap-2"):
            ui.button("Lancer l'enrichissement", on_click=lambda: _start_wizard(ctx)) \
                .classes("bs-accent-btn px-4 py-2")
            ui.button("Prévisualiser (dry-run)", on_click=lambda: _run_preview(ctx)) \
                .classes("bs-outline-btn px-4 py-2")

    _force_switch(ctx)

    with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
        for m in medias:
            _media_card(m)


def _media_card(media: Any) -> None:
    with ui.element("div").classes("bs-card p-2"):
        media_poster(media.cover_url, height="140px")
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")


def _force_switch(ctx: AppContext) -> None:
    def _on_change(e):
        ctx.state.force = e.value
        ctx.rerender()

    ui.switch(
        "Forcer le re-traitement (ignorer le cache)",
        value=ctx.state.force,
        on_change=_on_change,
    ).classes("text-xs mt-2").style("color:var(--text-muted)")


def _start_wizard(ctx: AppContext) -> None:
    if not ctx.state.medias or ctx.state.running:
        return
    ctx.navigate("wizard")


async def _run_preview(ctx: AppContext) -> None:
    if not ctx.state.medias:
        return
    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("bs-card w-full max-w-2xl p-6 items-center"):
        ui.icon("visibility", size="2.5rem").style("color:var(--accent)")
        ui.label("Prévisualisation (aucune écriture)").classes("bs-title text-lg")
        spinner = ui.spinner("dots", size="2rem")
        results_box = ui.column().classes("w-full")
    dialog.open()

    previews = []
    for media in ctx.state.medias:
        res = await ctx.processor.process_one_media(media, force=ctx.state.force, dry_run=True)
        if res["status"] == "PREVIEW" and res["changes"]:
            previews.append(res)

    spinner.delete()
    with results_box:
        if not previews:
            ui.label("Aucun changement à appliquer.").style("color:var(--text-muted)")
        else:
            ui.label(f"{len(previews)} fiche(s) seraient modifiées :").classes("text-sm mb-2")
            with ui.scroll_area().classes("h-[420px] w-full"):
                for p in previews:
                    with ui.element("div").classes("bs-card p-3 mb-2"):
                        ui.label(p["title"]).classes("bs-title text-sm")
                        for ch in p["changes"]:
                            ui.label(f"• {ch['field']} : {ch['old']} → {ch['new']}") \
                                .classes("text-xs").style("color:var(--text-muted)")
        ui.button("Fermer", on_click=dialog.close).classes("bs-outline-btn mt-2")
```

- [ ] **Step 4: Create the Wizard page (full-screen gallery + detail panel)**

```python
# frontend/pages/wizard.py
import asyncio
from typing import Any, Dict, List, Optional

from nicegui import ui

from frontend.components import media_poster
from frontend.context import AppContext


async def render(container: ui.element, ctx: AppContext) -> None:
    ctx.state.running = True
    medias = ctx.state.medias
    total = len(medias)

    container.clear()
    with container:
        ui.icon("auto_fix_high", size="3rem").classes("self-center").style("color:var(--accent)")
        ui.label("Enrichissement en cours...").classes("bs-title text-xl self-center mt-2")
        status_label = ui.label("Préparation...").classes("self-center").style("color:var(--text-muted)")
        progress = ui.linear_progress(value=0, show_value=False).classes("w-full mt-4")
        with ui.expansion("Journal d'activité", icon="list").classes("w-full mt-4"):
            log = ui.log().classes("w-full h-40 text-xs")

    def progress_cb(done: int, _total: int, result: Dict[str, Any]) -> None:
        media = result["media"]
        progress.set_value(done / total if total else 1)
        status_label.set_text(f"{done}/{total} traités")
        st = result["status"]
        if st == "PROCESSED":
            log.push(f"✅ {media.title} enrichi.")
        elif st == "SKIPPED":
            log.push(f"⏩ {media.title} ignoré ({result.get('reason')}).")
        elif st == "AMBIGUOUS":
            log.push(f"🤔 {media.title} : à confirmer manuellement.")
        elif st == "ERROR":
            log.push(f"❌ {media.title} : {result.get('error')}")
            ui.notify(f"Erreur sur {media.title}", type="negative")

    counters = await ctx.processor.run_auto_pass(medias, force=ctx.state.force, progress_cb=progress_cb)

    resolved = 0
    for amb in counters["ambiguous"]:
        if await _resolve_ambiguous(container, ctx, amb):
            resolved += 1
    counters["resolved"] = resolved

    _render_finished(container, ctx, counters)


async def _resolve_ambiguous(container: ui.element, ctx: AppContext, amb: Dict[str, Any]) -> bool:
    title = amb["original_title"]
    media_id = amb["media_id"]
    candidates = amb["candidates"]
    is_series = amb.get("is_series", False)
    future: "asyncio.Future[Any]" = asyncio.Future()

    _render_gallery(container, ctx, title, candidates, future, media_id, is_series)
    tmdb_id = await future

    if tmdb_id:
        try:
            await ctx.processor.enrich_media_with_tmdb_id(media_id, tmdb_id)
            ui.notify(f"« {title} » enrichi.", type="positive")
            return True
        except Exception as e:
            ui.notify(f"Erreur enrichissement « {title} » : {e}", type="negative")
    return False


def _render_gallery(
    container: ui.element,
    ctx: AppContext,
    title: str,
    candidates: List[Dict[str, Any]],
    future: "asyncio.Future[Any]",
    media_id: str,
    is_series: bool,
) -> None:
    container.clear()
    with container:
        ui.label(f"Ambiguïté : {title}").classes("bs-title text-lg")
        ui.label("Choisissez le bon résultat, ou recherchez autrement") \
            .classes("text-xs").style("color:var(--text-muted)")

        with ui.row().classes("w-full items-center gap-2 mt-2"):
            search_input = ui.input(placeholder="Rechercher un autre titre…", value=title).classes("flex-grow")
            year_input = ui.input(placeholder="Année").classes("w-24")

            async def do_search() -> None:
                q = search_input.value.strip()
                if not q:
                    return
                yr = int(year_input.value) if (year_input.value or "").strip().isdigit() else None
                new_cands = await ctx.processor.search_candidates(q, is_series_flag=is_series, year=yr)
                _render_gallery(container, ctx, q, new_cands, future, media_id, is_series)

            ui.button(icon="search", on_click=do_search).props("flat round")

        detail_box = ui.column().classes("w-full mt-4")

        if not candidates:
            ui.label("Aucun résultat. Essayez un autre titre ci-dessus.").style("color:var(--text-muted)")
        else:
            with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
                for cand in candidates:
                    _candidate_thumb(cand, future, detail_box)
            detail_box.move(target_index=-1)
            _render_detail(detail_box, candidates[0], future)

        with ui.row().classes("w-full justify-center mt-4"):
            ui.button("Ignorer cette fiche", on_click=lambda: _resolve(future, None)).classes("bs-outline-btn")


def _candidate_thumb(cand: Dict[str, Any], future: "asyncio.Future[Any]", detail_box: ui.element) -> None:
    def _select() -> None:
        _render_detail(detail_box, cand, future)

    with ui.element("div").classes("bs-card p-2 cursor-pointer").on("click", _select):
        media_poster(cand.get("poster_url"), height="120px")
        year = (cand.get("release_date") or "N/A")[:4]
        ui.badge(year).classes("bs-badge mt-1")


def _render_detail(detail_box: ui.element, cand: Optional[Dict[str, Any]], future: "asyncio.Future[Any]") -> None:
    detail_box.clear()
    if not cand:
        return
    with detail_box:
        with ui.element("div").classes("bs-card p-4"):
            ui.label(cand["title"]).classes("bs-title text-lg")
            meta = []
            if cand.get("director"):
                meta.append(f"🎬 {cand['director']}")
            if cand.get("imdb_rating"):
                meta.append(f"⭐ IMDb {cand['imdb_rating']}")
            if cand.get("rated"):
                meta.append(f"🔞 {cand['rated']}")
            if meta:
                ui.label("   ".join(meta)).classes("text-xs mt-1").style("color:var(--text-muted)")
            if cand.get("overview"):
                ui.label(cand["overview"]).classes("text-sm mt-2").style("color:var(--text-muted)")
            for tag in (cand.get("suggested_tags") or []):
                ui.badge(tag).classes("bs-badge mt-1")
            ui.button("Confirmer ce titre", on_click=lambda: _resolve(future, cand["id"])) \
                .classes("bs-accent-btn mt-3")


def _resolve(future: "asyncio.Future[Any]", value: Any) -> None:
    if not future.done():
        future.set_result(value)


def _render_finished(container: ui.element, ctx: AppContext, counters: Dict[str, Any]) -> None:
    container.clear()
    ctx.state.running = False
    with container:
        with ui.column().classes("w-full items-center text-center"):
            ui.icon("check_circle", size="4rem").style("color:var(--accent)")
            ui.label("Enrichissement terminé !").classes("bs-title text-2xl mt-4")
            ui.label(
                f"✅ {counters['processed']} auto · ✨ {counters.get('resolved', 0)} manuels · "
                f"⏩ {counters['skipped']} ignorés · ❌ {counters['errors']} erreurs"
            ).classes("mt-2").style("color:var(--text-muted)")

            async def _on_close() -> None:
                ctx.navigate("dashboard")
                await ctx.reload()

            ui.button("Fermer et rafraîchir", on_click=_on_close).classes("bs-accent-btn mt-4")
```

- [ ] **Step 5: Rewrite `frontend/ui.py` as the top-bar orchestrator**

```python
# frontend/ui.py
import asyncio
from typing import Callable, Dict

from nicegui import ui

from backend.config import Config
from backend.core.notion import NotionService
from backend.core.processor import EnrichmentProcessor
from frontend.context import AppContext, AppState
from frontend.pages import dashboard, wizard
from frontend.theme import apply_theme

SECTIONS = [
    ("dashboard", "À traiter"),
]

PAGE_RENDERERS: Dict[str, Callable] = {
    "dashboard": dashboard.render,
    "wizard": wizard.render,
}


@ui.page("/")
async def main_page():
    apply_theme()

    processor = EnrichmentProcessor()
    state = AppState()
    active_section = {"key": "dashboard"}
    nav_buttons: Dict[str, ui.element] = {}

    content = ui.column().classes("w-full max-w-5xl mx-auto p-4")

    def _compute_todo() -> None:
        if state.force:
            state.medias = list(state.all_medias)
        else:
            state.medias = [
                m for m in state.all_medias
                if not (m.director and m.release_date and m.support) or not m.tmdb_ok
            ]

    def render_section(section_key: str) -> None:
        content.clear()
        handler = PAGE_RENDERERS.get(section_key)
        if handler is None:
            with content:
                ui.label("Bientôt disponible").classes("bs-title")
            return

        if asyncio.iscoroutinefunction(handler):
            with content:
                ui.spinner("dots", size="3rem").classes("self-center")

            async def _run() -> None:
                await handler(content, ctx)

            ui.timer(0.05, _run, once=True)
        else:
            handler(content, ctx)

    def navigate(section_key: str) -> None:
        active_section["key"] = section_key
        for key, btn in nav_buttons.items():
            btn.classes(remove="active", add="active" if key == section_key else "")
        render_section(section_key)

    def rerender() -> None:
        _compute_todo()
        render_section(active_section["key"])

    async def reload() -> None:
        content.clear()
        with content:
            ui.spinner("dots", size="3rem").classes("self-center")
        try:
            state.all_medias = await NotionService.fetch_all_media()
        except Exception as e:
            content.clear()
            ui.notify(f"Erreur de connexion à Notion : {e}", type="negative")
            with content:
                ui.label("Impossible de charger les données Notion.").classes("bs-title")
            return
        rerender()

    ctx = AppContext(processor=processor, state=state, reload=reload, rerender=rerender, navigate=navigate)

    with ui.row().classes("bs-topbar w-full items-center justify-between px-6 py-3"):
        ui.label("🎬 Backstage").classes("bs-title text-xl")
        with ui.row().classes("gap-2"):
            for key, label in SECTIONS:
                if key == "ai" and not Config.ai_enabled():
                    continue
                btn = ui.button(label, on_click=lambda k=key: navigate(k)).props("flat no-caps").classes("bs-navlink")
                if key == active_section["key"]:
                    btn.classes(add="active")
                nav_buttons[key] = btn

    ui.timer(0.1, reload, once=True)
```

- [ ] **Step 6: Manual verification**

Run: `python main.py`, open `http://localhost:8080`.

Check:
1. Top bar shows "🎬 Backstage" in serif on a dark bar, "À traiter" link underlined in gold (active).
2. Background is ivoire (`#faf6ef`), not the old light-gray.
3. If there are pending fiches: a summary line + "Lancer l'enrichissement" (bordeaux pill) and "Prévisualiser (dry-run)" (bordeaux outline) buttons, then a 4-column grid of cards — each with either a poster or the gradient placeholder, title in serif, a bordeaux year/type badge.
4. If nothing is pending: the green check + "Tout est à jour !" empty state.
5. Click "Lancer l'enrichissement": the dashboard is replaced (no modal) by the full-screen progress view (icon, progress bar, expandable log).
6. If any fiche is ambiguous: a poster gallery appears with a detail panel below it; clicking a different thumbnail updates the detail panel; "Confirmer ce titre" resolves it and moves to the next one or to the finished screen.
7. On the finished screen, click "Fermer et rafraîchir": returns to the dashboard with fresh data from Notion.
8. Toggle "Forcer le re-traitement": the grid updates immediately (no full Notion refetch, near-instant).
9. Click "Prévisualiser (dry-run)": a dialog opens showing the changes that would be applied, no Notion writes occur.

- [ ] **Step 7: Commit**

```bash
git add frontend/context.py frontend/components.py frontend/pages/__init__.py \
        frontend/pages/dashboard.py frontend/pages/wizard.py frontend/ui.py
git commit -m "feat(frontend): rebuild orchestrator, dashboard and wizard with editorial redesign"
```

---

### Task 5: Statistics page (real dashboard: donut, line, bars)

**Files:**
- Create: `frontend/pages/stats.py`
- Modify: `frontend/ui.py:16-19` (`SECTIONS` list) and `frontend/ui.py:21-24` (`PAGE_RENDERERS` dict + import)

**Interfaces:**
- Consumes: `backend.core.stats.compute_stats`, `backend.core.stats.compute_enrichment_progression` (Task 3), `backend.core.stats.find_duplicates`, `backend.core.history.read_recent`.
- Produces: `stats.render(container: ui.element, ctx: AppContext) -> None`.

- [ ] **Step 1: Create the Stats page**

```python
# frontend/pages/stats.py
from typing import Any

from nicegui import ui

from backend.core import history as history_mod
from backend.core import stats as stats_mod
from frontend.context import AppContext


def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    with container:
        _render_stats(ctx)


def _render_stats(ctx: AppContext) -> None:
    s = stats_mod.compute_stats(ctx.state.all_medias)

    with ui.row().classes("w-full gap-3 flex-wrap mb-4"):
        _stat_tile("Total", s["total"])
        _stat_tile("Enrichis", f"{s['enriched']} ({s['enriched_pct']}%)")
        _stat_tile("Notés", s["rated"])
        _stat_tile("Sans réalisateur", s["without_director"])

    with ui.row().classes("w-full gap-3 flex-wrap"):
        with ui.element("div").classes("bs-card p-4 flex-grow"):
            ui.label("Répartition support").classes("bs-title text-sm mb-2")
            if s["by_support"]:
                ui.echart({
                    "series": [{
                        "type": "pie",
                        "radius": ["45%", "70%"],
                        "data": [{"value": c, "name": n} for n, c in s["by_support"]],
                        "color": ["#7a2331", "#c9a35c", "#2b2420", "#d8c9ab", "#8a8578"],
                    }],
                    "legend": {"bottom": 0, "textStyle": {"color": "#8a8578"}},
                }).classes("w-full").style("height:220px")
            else:
                ui.label("Pas encore de données.").style("color:var(--text-muted)")

        with ui.element("div").classes("bs-card p-4 flex-grow"):
            ui.label("Progression de l'enrichissement").classes("bs-title text-sm mb-2")
            progression = stats_mod.compute_enrichment_progression(history_mod.read_recent(limit=100000))
            if progression:
                ui.echart({
                    "xAxis": {"type": "category", "data": [p["date"] for p in progression]},
                    "yAxis": {"type": "value"},
                    "series": [{
                        "type": "line",
                        "smooth": True,
                        "data": [p["cumulative"] for p in progression],
                        "lineStyle": {"color": "#7a2331"},
                        "areaStyle": {"color": "rgba(122,35,49,0.12)"},
                    }],
                }).classes("w-full").style("height:220px")
            else:
                ui.label("Aucun historique pour le moment.").style("color:var(--text-muted)")

    with ui.element("div").classes("bs-card p-4 w-full mt-3"):
        ui.label("Top genres").classes("bs-title text-sm mb-2")
        if s["top_genres"]:
            ui.echart({
                "xAxis": {"type": "category", "data": [g for g, _ in s["top_genres"]]},
                "yAxis": {"type": "value"},
                "series": [{
                    "type": "bar",
                    "data": [c for _, c in s["top_genres"]],
                    "itemStyle": {"color": "#7a2331"},
                }],
            }).classes("w-full").style("height:220px")
        else:
            ui.label("Pas encore de données.").style("color:var(--text-muted)")

    dups = stats_mod.find_duplicates(ctx.state.all_medias)
    with ui.element("div").classes("bs-card p-4 w-full mt-3"):
        ui.label(f"Doublons potentiels ({len(dups)})").classes("bs-title text-sm mb-2")
        if not dups:
            ui.label("Aucun doublon détecté.").style("color:var(--text-muted)")
        for d in dups:
            ui.label(f"⚠️ {d['title']} — {d['count']} fiches").classes("text-sm").style("color:#b8892f")


def _stat_tile(label: str, value: Any) -> None:
    with ui.element("div").classes("bs-card p-4 items-center flex-grow"):
        ui.label(str(value)).classes("bs-title text-2xl")
        ui.label(label).classes("text-xs uppercase").style("color:var(--text-muted); letter-spacing:0.05em;")
```

- [ ] **Step 2: Wire the Stats section into the orchestrator**

In `frontend/ui.py`, update the imports, `SECTIONS`, and `PAGE_RENDERERS`:

```python
# frontend/ui.py — replace the import line "from frontend.pages import dashboard, wizard" with:
from frontend.pages import dashboard, stats, wizard
```

```python
# frontend/ui.py — replace SECTIONS with:
SECTIONS = [
    ("dashboard", "À traiter"),
    ("stats", "Statistiques"),
]
```

```python
# frontend/ui.py — replace PAGE_RENDERERS with:
PAGE_RENDERERS: Dict[str, Callable] = {
    "dashboard": dashboard.render,
    "wizard": wizard.render,
    "stats": stats.render,
}
```

- [ ] **Step 3: Manual verification**

Run: `python main.py`, open `http://localhost:8080`, click "Statistiques" in the top bar.

Check:
1. Four stat tiles (Total, Enrichis, Notés, Sans réalisateur) in bordeaux/serif styling.
2. A donut chart for support repartition and a line chart for enrichment progression, side by side.
3. A bar chart for top genres below.
4. The duplicates block at the bottom, unchanged in content, restyled to match.
5. If `history.jsonl` has no entries yet, the progression chart shows "Aucun historique pour le moment." instead of an empty chart.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/stats.py frontend/ui.py
git commit -m "feat(frontend): add real stats dashboard (donut, line, bar charts)"
```

---

### Task 6: History page (chronological timeline)

**Files:**
- Modify: `frontend/components.py` (append `source_badge`)
- Create: `frontend/pages/history.py`
- Modify: `frontend/ui.py` (`SECTIONS` list, `PAGE_RENDERERS` dict + import)

**Interfaces:**
- Consumes: `frontend.format_utils.format_relative_timestamp` (Task 2), `backend.core.history.read_recent`.
- Produces: `source_badge(source: str) -> None` (appended to `frontend/components.py`), `history.render(container: ui.element, ctx: AppContext) -> None`.

- [ ] **Step 1: Add the source badge helper**

```python
# appended to frontend/components.py
# (relies on the `from nicegui import ui` import already at the top of this file from Task 4)
def source_badge(source: str) -> None:
    color = "#7a2331" if source == "manual" else "#c9a35c"
    ui.badge("Manuel" if source == "manual" else "Auto", color=color)
```

- [ ] **Step 2: Create the History page**

```python
# frontend/pages/history.py
from nicegui import ui

from backend.core import history as history_mod
from frontend.components import source_badge
from frontend.context import AppContext
from frontend.format_utils import format_relative_timestamp


def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    with container:
        _render_history()


def _render_history() -> None:
    entries = history_mod.read_recent(limit=50)
    if not entries:
        ui.label("Aucune modification enregistrée pour le moment.").style("color:var(--text-muted)")
        return

    with ui.column().classes("w-full gap-0"):
        for e in entries:
            with ui.row().classes("w-full items-start gap-3 py-2"):
                with ui.column().classes("items-center gap-0"):
                    dot_color = "#7a2331" if e.get("source") == "manual" else "#c9a35c"
                    ui.element("div").style(f"width:8px; height:8px; border-radius:50%; background:{dot_color};")
                    ui.element("div").style("width:2px; min-height:24px; background:var(--border);")
                with ui.column().classes("gap-0"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(e.get("title", "?")).classes("bs-title text-sm")
                        source_badge(e.get("source", "auto"))
                    ts = format_relative_timestamp(e.get("ts", ""))
                    ui.label(f"{ts} · {', '.join(e.get('fields', []))}") \
                        .classes("text-xs").style("color:var(--text-muted)")
```

- [ ] **Step 3: Wire the History section into the orchestrator**

```python
# frontend/ui.py — replace the import line with:
from frontend.pages import dashboard, history, stats, wizard
```

```python
# frontend/ui.py — replace SECTIONS with:
SECTIONS = [
    ("dashboard", "À traiter"),
    ("stats", "Statistiques"),
    ("history", "Historique"),
]
```

```python
# frontend/ui.py — replace PAGE_RENDERERS with:
PAGE_RENDERERS: Dict[str, Callable] = {
    "dashboard": dashboard.render,
    "wizard": wizard.render,
    "stats": stats.render,
    "history": history.render,
}
```

- [ ] **Step 4: Manual verification**

Run: `python main.py`, open `http://localhost:8080`, click "Historique" in the top bar.

Check:
1. A vertical line connects a colored dot per entry (bordeaux dot = manual, gold dot = auto).
2. Each entry shows title, an "Auto"/"Manuel" badge, and a relative timestamp ("à l'instant", "il y a N min", "aujourd'hui à HH:MM", "hier à HH:MM", or a full date for older entries) followed by the modified fields.
3. If `history.jsonl` is empty, the "Aucune modification enregistrée pour le moment." message shows instead.

- [ ] **Step 5: Commit**

```bash
git add frontend/components.py frontend/pages/history.py frontend/ui.py
git commit -m "feat(frontend): add chronological timeline for history section"
```

---

### Task 7: AI recommendations tab (light restyle only)

**Files:**
- Create: `frontend/pages/ai.py`
- Modify: `frontend/ui.py` (`SECTIONS` list, `PAGE_RENDERERS` dict + import)

**Interfaces:**
- Consumes: `backend.core.ai.recommend`, `backend.core.ai.AIUnavailable`, `backend.core.mapping.Values`.
- Produces: `ai.render(container: ui.element, ctx: AppContext) -> None`.

- [ ] **Step 1: Create the AI page**

```python
# frontend/pages/ai.py
from nicegui import ui

from backend.core import ai as ai_mod
from backend.core.mapping import Values
from frontend.context import AppContext


def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    with container:
        _render_ai(ctx)


def _render_ai(ctx: AppContext) -> None:
    ui.label("Recommandations personnalisées (Claude)").classes("bs-title text-lg")
    ui.label("Basé sur vos films notés, parmi votre liste « à regarder ».") \
        .classes("text-sm").style("color:var(--text-muted)")
    result_box = ui.column().classes("w-full mt-3")

    async def recommend() -> None:
        result_box.clear()
        with result_box:
            ui.spinner("dots", size="2rem")
        watched = [
            {"title": m.title, "rating": m.rating, "genres": m.categories}
            for m in ctx.state.all_medias if m.rating
        ]
        candidates = [
            {"title": m.title, "genres": m.categories}
            for m in ctx.state.all_medias if m.status == Values.STATUS_TO_WATCH
        ]
        try:
            text = await ai_mod.recommend(watched, candidates)
            result_box.clear()
            with result_box:
                with ui.element("div").classes("bs-card p-4 w-full"):
                    ui.markdown(text)
        except ai_mod.AIUnavailable as e:
            result_box.clear()
            ui.notify(f"IA indisponible : {e}", type="negative")

    ui.button("Recommander 3 films", on_click=recommend).classes("bs-accent-btn mt-2")
```

- [ ] **Step 2: Wire the AI section into the orchestrator**

```python
# frontend/ui.py — replace the import line with:
from frontend.pages import ai as ai_page
from frontend.pages import dashboard, history, stats, wizard
```

```python
# frontend/ui.py — replace SECTIONS with:
SECTIONS = [
    ("dashboard", "À traiter"),
    ("stats", "Statistiques"),
    ("history", "Historique"),
    ("ai", "Reco IA"),
]
```

```python
# frontend/ui.py — replace PAGE_RENDERERS with:
PAGE_RENDERERS: Dict[str, Callable] = {
    "dashboard": dashboard.render,
    "wizard": wizard.render,
    "stats": stats.render,
    "history": history.render,
    "ai": ai_page.render,
}
```

(The existing `if key == "ai" and not Config.ai_enabled(): continue` guard in the nav-building loop already hides the link when `ANTHROPIC_API_KEY` is unset — no further change needed there.)

- [ ] **Step 3: Manual verification**

With `ANTHROPIC_API_KEY` set in `.env`: run `python main.py`, open `http://localhost:8080`, confirm "Reco IA" appears in the top bar, click it, click "Recommander 3 films", confirm a bordeaux-card result (or a clear "IA indisponible" notification if the key/model call fails).

Without `ANTHROPIC_API_KEY` set: confirm the "Reco IA" link does not appear in the top bar at all.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/ai.py frontend/ui.py
git commit -m "feat(frontend): restyle AI recommendations tab to match editorial theme"
```

---

### Task 8: Cleanup, README update, full regression pass

**Files:**
- Modify: `README.md:79-92` (Architecture section)
- No code changes beyond documentation — this task verifies the whole redesign together.

- [ ] **Step 1: Update the README architecture diagram**

Replace the `## Architecture` code block in `README.md` (currently lines 79-92) with:

```
main.py                → bootstrap NiceGUI
backend/config.py      → variables d'environnement
backend/core/
  models.py            → modèle pydantic Media
  notion.py            → client Notion (httpx async)
  tmdb.py              → client TMDB (httpx async)
  processor.py         → matching + règles + orchestration
  cache_service.py      → cache « déjà traité » (avec hash de contenu)
  stats.py             → agrégats stats + détection de doublons + progression
  history.py           → journal d'audit (history.jsonl)
  ai.py                → recommandations Claude (optionnel)
frontend/
  theme.py             → design tokens (Ivoire & Bordeaux) + injection CSS
  format_utils.py       → formatage de timestamps relatifs
  components.py        → éléments partagés (poster/placeholder, badge source)
  context.py           → AppState / AppContext partagés entre les pages
  ui.py                → orchestrateur : top bar + routing des sections
  pages/
    dashboard.py       → section "À traiter" (bandeau + grille de cards)
    wizard.py          → résolution d'ambiguïté (page plein écran)
    stats.py           → tableau de bord (donut / courbe / barres)
    history.py         → timeline chronologique
    ai.py              → reco IA (restyle léger)
scripts/                → scripts de debug manuels
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass, including the new `tests/test_theme.py`, `tests/test_format_utils.py`, and the appended `tests/test_stats.py` cases from Tasks 1-3.

- [ ] **Step 3: Full manual walkthrough**

Run: `python main.py`, open `http://localhost:8080`, and re-confirm every approved design decision end-to-end in one pass:

1. **Palette/typography**: ivoire background, bordeaux accents, serif titles + sans body text throughout all four sections.
2. **Navigation**: top bar with "🎬 Backstage" + underlined active section, no Quasar tabs remain.
3. **Dashboard**: bandeau résumé + full-width card grid with poster/placeholder.
4. **Wizard**: full-screen (no modal) poster gallery + detail panel flow, reachable only via "Lancer l'enrichissement".
5. **Stats**: donut + line + bar charts, duplicates block.
6. **History**: chronological dot-and-line timeline with relative timestamps.
7. **Reco IA**: present only when `ANTHROPIC_API_KEY` is set, restyled cards.
8. No leftover reference to the old indigo/`glass-card`/`media-card` styling anywhere (`grep -r "glass-card\|media-card\|indigo" frontend/` returns nothing).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update architecture section for the frontend redesign"
```
