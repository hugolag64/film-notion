from datetime import date as date_cls

from nicegui import ui

from frontend.components import media_card, media_poster
from frontend.context import AppContext
from frontend.format_utils import format_relative_timestamp


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
        ui.button("Ajouter un film", on_click=lambda: _open_add_dialog(ctx)) \
            .classes("bs-outline-btn px-4 py-2 mt-2")
        return

    with ui.row().classes("w-full items-center justify-between mb-4"):
        with ui.column().classes("gap-0"):
            ui.label(f"{len(medias)} fiche(s) en attente").classes("bs-title text-lg")
            if ctx.state.last_synced:
                sync_text = f"Dernière synchro : {format_relative_timestamp(ctx.state.last_synced)}"
            else:
                sync_text = "Prêt à enrichir"
            ui.label(sync_text).classes("text-xs").style("color:var(--text-muted)")
        with ui.row().classes("gap-2"):
            ui.button("Lancer l'enrichissement", on_click=lambda: _start_wizard(ctx)) \
                .classes("bs-accent-btn px-4 py-2")
            ui.button("Prévisualiser (dry-run)", on_click=lambda: _run_preview(ctx)) \
                .classes("bs-outline-btn px-4 py-2")
            ui.button("Ajouter un film", on_click=lambda: _open_add_dialog(ctx)) \
                .classes("bs-outline-btn px-4 py-2")

    _force_switch(ctx)

    with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
        for m in medias:
            media_card(m)


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


def _open_add_dialog(ctx: AppContext) -> None:
    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("bs-card w-full max-w-2xl p-6"):
        ui.label("Ajouter un film").classes("bs-title text-lg mb-2")

        title_input = ui.input("Titre *").classes("w-full")
        type_select = ui.select(["Film", "Série"], value="Film", label="Type").classes("w-full")
        status_input = ui.input("Statut").classes("w-full")
        support_input = ui.input("Support").classes("w-full")
        rating_input = ui.input("Note /10").classes("w-full")
        release_date_input = ui.input("Date de sortie (AAAA-MM-JJ)").classes("w-full")
        director_input = ui.input("Réalisateur").classes("w-full")
        categories_input = ui.input("Catégories (séparées par des virgules)").classes("w-full")
        tags_input = ui.input("Tags (séparés par des virgules)").classes("w-full")
        synopsis_input = ui.textarea("Synopsis").classes("w-full")
        review_input = ui.textarea("Avis").classes("w-full")
        cover_url_input = ui.input("URL de l'affiche").classes("w-full")

        preview_box = ui.column().classes("w-full items-center mt-2")

        def _update_preview() -> None:
            preview_box.clear()
            with preview_box:
                media_poster(cover_url_input.value or None, height="160px")

        cover_url_input.on("blur", lambda: _update_preview())
        _update_preview()

        error_label = ui.label("").classes("text-xs mt-1").style("color:#c0392b")

        async def _submit() -> None:
            title = title_input.value.strip()
            if not title:
                error_label.set_text("Le titre est obligatoire.")
                return

            release_date_value = None
            raw_date = (release_date_input.value or "").strip()
            if raw_date:
                try:
                    release_date_value = date_cls.fromisoformat(raw_date)
                except ValueError:
                    error_label.set_text("Date invalide (attendu AAAA-MM-JJ).")
                    return

            fields = {
                "title": title,
                "type": type_select.value,
                "status": (status_input.value or "").strip() or None,
                "support": (support_input.value or "").strip() or None,
                "rating": (rating_input.value or "").strip() or None,
                "release_date": release_date_value,
                "director": (director_input.value or "").strip() or None,
                "categories": [c.strip() for c in (categories_input.value or "").split(",") if c.strip()],
                "synopsis": (synopsis_input.value or "").strip() or None,
                "tags": [t.strip() for t in (tags_input.value or "").split(",") if t.strip()],
                "review": (review_input.value or "").strip() or None,
                "cover_url": (cover_url_input.value or "").strip() or None,
            }

            await ctx.store.create(fields)
            ui.notify(f"« {title} » ajouté.", type="positive")
            dialog.close()
            await ctx.reload()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Annuler", on_click=dialog.close).classes("bs-outline-btn")
            ui.button("Ajouter", on_click=_submit).classes("bs-accent-btn")

    dialog.open()
