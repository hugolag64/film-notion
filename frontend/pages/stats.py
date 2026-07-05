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
