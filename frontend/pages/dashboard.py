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
