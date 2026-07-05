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
