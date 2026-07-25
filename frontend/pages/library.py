import re
from typing import Any, Dict, List, Optional

from nicegui import ui

from backend.core.models import Media
from frontend.components import media_card, open_media_detail_dialog
from frontend.context import AppContext

SORT_OPTIONS = ["Titre", "Année", "Note", "Date d'ajout"]
PAGE_SIZE = 24


def _rating_value(media: Media) -> Optional[float]:
    if not media.rating:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)?)", media.rating)
    return float(match.group(1)) if match else None


def distinct_filter_options(medias: List[Media], field: str) -> List[str]:
    if field == "categories":
        values = {c for m in medias for c in m.categories}
    else:
        values = {getattr(m, field) for m in medias if getattr(m, field)}
    return sorted(values)


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

    if sort_key == "Année":
        with_date = sorted((m for m in filtered if m.release_date), key=lambda m: m.release_date, reverse=True)
        without_date = [m for m in filtered if not m.release_date]
        return with_date + without_date

    if sort_key == "Note":
        rated = sorted((m for m in filtered if _rating_value(m) is not None), key=_rating_value, reverse=True)
        unrated = [m for m in filtered if _rating_value(m) is None]
        return rated + unrated

    if sort_key == "Date d'ajout":
        # No created_at column exists; the store returns rows in insertion (rowid) order,
        # so reversing the already-filtered list surfaces the most recently added first.
        return list(reversed(filtered))

    raise ValueError(f"Tri inconnu : {sort_key}")


def total_pages(count: int, page_size: int = PAGE_SIZE) -> int:
    if count <= 0:
        return 1
    return -(-count // page_size)  # ceiling division


def paginate_medias(medias: List[Media], page: int, page_size: int = PAGE_SIZE) -> List[Media]:
    start = (page - 1) * page_size
    return medias[start:start + page_size]


def get_library_state(ui_state: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return ui_state.setdefault("library", {
        "query": "",
        "sort": SORT_OPTIONS[0],
        "page": 1,
        "filters": {"genres": [], "statuses": [], "supports": []},
    })


def render(container: ui.element, ctx: AppContext) -> None:
    container.clear()
    state = get_library_state(ctx.state.ui_state)

    genre_options = distinct_filter_options(ctx.state.all_medias, "categories")
    status_options = distinct_filter_options(ctx.state.all_medias, "status")
    support_options = distinct_filter_options(ctx.state.all_medias, "support")

    with container:
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

            with ui.button(_filter_button_label(), icon="filter_list").props("flat") as filter_button:
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

        grid_box = ui.column().classes("w-full")
        pager_box = ui.row().classes("w-full items-center justify-center gap-3 mt-4")

        def _go_to_page(page: int) -> None:
            state["page"] = page
            _refresh()

        def _refresh() -> None:
            grid_box.clear()
            pager_box.clear()
            results = filter_and_sort_medias(ctx.state.all_medias, state["query"], state["sort"], filters=state["filters"])
            pages = total_pages(len(results))
            state["page"] = min(max(state["page"], 1), pages)
            page_items = paginate_medias(results, state["page"])

            with grid_box:
                if not results:
                    ui.label("Aucun résultat.").style("color:var(--text-muted)")
                else:
                    with ui.grid(columns=4).classes("w-full gap-3"):
                        for m in page_items:
                            media_card(m, on_click=lambda m=m: open_media_detail_dialog(m, ctx))

            if results and pages > 1:
                with pager_box:
                    ui.button(icon="chevron_left", on_click=lambda: _go_to_page(state["page"] - 1)) \
                        .props("flat round dense").set_enabled(state["page"] > 1)
                    ui.label(f"Page {state['page']} / {pages}").classes("text-sm")
                    ui.button(icon="chevron_right", on_click=lambda: _go_to_page(state["page"] + 1)) \
                        .props("flat round dense").set_enabled(state["page"] < pages)

        _refresh()
