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
