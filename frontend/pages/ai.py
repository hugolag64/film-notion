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
