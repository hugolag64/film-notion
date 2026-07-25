import asyncio
from datetime import datetime, timezone
from typing import Callable, Dict

from nicegui import ui

from backend.config import Config
from backend.core.store import MediaStore
from backend.core.processor import EnrichmentProcessor
from frontend.context import AppContext, AppState
from frontend.pages import ai as ai_page
from frontend.pages import dashboard, history, library, stats, wizard
from frontend.theme import apply_theme

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


@ui.page("/")
async def main_page():
    apply_theme()

    store = MediaStore(Config.DB_PATH)
    processor = EnrichmentProcessor(store)
    state = AppState()
    active_section = {"key": "dashboard"}
    nav_buttons: Dict[str, ui.element] = {}

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
        if section_key == "wizard":
            for btn in nav_buttons.values():
                btn.disable()
        else:
            for btn in nav_buttons.values():
                btn.enable()
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
            state.all_medias = await store.fetch_all()
        except Exception as e:
            content.clear()
            ui.notify(f"Erreur de lecture de la base locale : {e}", type="negative")
            with content:
                ui.label("Impossible de charger les données locales.").classes("bs-title")
            return
        state.last_synced = datetime.now(timezone.utc).isoformat()
        rerender()

    ctx = AppContext(processor=processor, store=store, state=state, reload=reload, rerender=rerender, navigate=navigate)

    with ui.row().classes("bs-topbar w-full items-center justify-between px-6 py-3"):
        ui.image("/static/Logo.png").style("height:42px; width:auto;")
        with ui.row().classes("gap-2"):
            for key, label in SECTIONS:
                if key == "ai" and not Config.ai_enabled():
                    continue
                btn = ui.button(label, on_click=lambda k=key: navigate(k)).props("flat no-caps").classes("bs-navlink")
                if key == active_section["key"]:
                    btn.classes(add="active")
                nav_buttons[key] = btn

    content = ui.column().classes("w-full max-w-5xl mx-auto p-4")

    ui.timer(0.1, reload, once=True)
