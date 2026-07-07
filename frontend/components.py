from typing import Any, Callable, Optional

from nicegui import ui

from backend.core.mapping import is_series
from frontend.context import AppContext


def rating_badge_text(media: Any) -> Optional[str]:
    """Texte du badge note. Les notes déjà saisies en étoiles (ex. '⭐️⭐️⭐️') sont affichées
    telles quelles ; les notes textuelles (ex. '8/10') sont préfixées d'une étoile."""
    if not media.rating:
        return None
    rating = media.rating.strip()
    return rating if "⭐" in rating else f"⭐ {rating}"


def primary_genre(media: Any) -> Optional[str]:
    """Première catégorie du média (genre principal), ou None si absente."""
    return media.categories[0] if media.categories else None


def media_poster(cover_url: Optional[str], *, width: Optional[str] = None, height: Optional[str] = None) -> None:
    """Affiche le poster TMDB (ratio affiche 2:3) si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if not width and not height:
        width = "100%"
    dims = "".join(f"{prop}:{value}; " for prop, value in (("width", width), ("height", height)) if value)
    style = f"{dims}aspect-ratio:2/3; object-fit:cover;"
    if cover_url:
        ui.image(cover_url).classes("rounded").style(style)
    else:
        with ui.element("div").classes("bs-poster-placeholder").style(style):
            ui.icon("movie", size="2rem").classes("opacity-70")


def media_card(media: Any, *, on_click: Optional[Callable[[], None]] = None) -> None:
    """Carte poster + titre + badges année/type/note/genre, partagée par le dashboard et la bibliothèque."""
    card = ui.element("div").classes("bs-card p-2")
    if on_click is not None:
        card.classes("cursor-pointer").on("click", on_click)
    with card:
        media_poster(media.cover_url)
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")

        rating_text = rating_badge_text(media)
        genre_text = primary_genre(media)
        if rating_text or genre_text:
            with ui.row().classes("gap-1 mt-1"):
                if rating_text:
                    ui.badge(rating_text).classes("bs-badge-secondary")
                if genre_text:
                    ui.badge(genre_text).classes("bs-badge-secondary")


def source_badge(source: str) -> None:
    color = "#7a2331" if source == "manual" else "#c9a35c"
    ui.badge("Manuel" if source == "manual" else "Auto", color=color)


def open_media_detail_dialog(media: Any, ctx: AppContext) -> None:
    """Fiche détaillée d'un média : infos en lecture seule + note/avis éditables."""
    dialog = ui.dialog()
    with dialog, ui.card().classes("bs-card w-full max-w-2xl p-6"):
        with ui.row().classes("w-full justify-end -mb-2"):
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        with ui.row().classes("w-full gap-4 items-start"):
            media_poster(media.cover_url, width="180px")
            with ui.column().classes("gap-1"):
                ui.label(media.title).classes("bs-title text-lg")
                year = media.release_date.year if media.release_date else "—"
                ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge")
                ui.label(f"Réalisateur : {media.director or '—'}").classes("text-sm mt-2")
                genres = ", ".join(media.categories) if media.categories else "—"
                ui.label(f"Genre : {genres}").classes("text-sm")

        ui.label("Synopsis").classes("bs-title text-sm mt-4")
        ui.label(media.synopsis or "—").classes("text-sm").style("color:var(--text-muted)")

        ui.label("Votre note et avis").classes("bs-title text-sm mt-4")
        rating_input = ui.input("Note /10", value=media.rating or "").classes("w-full")
        review_input = ui.textarea("Avis", value=media.review or "").classes("w-full")

        async def _save() -> None:
            await ctx.store.update(media.id, {
                "rating": (rating_input.value or "").strip() or None,
                "review": (review_input.value or "").strip() or None,
            })
            ui.notify(f"« {media.title} » mis à jour.", type="positive")
            dialog.close()
            await ctx.reload()

        async def _delete() -> None:
            confirm_dialog = ui.dialog()
            with confirm_dialog, ui.card().classes("bs-card p-6"):
                ui.label(f"Supprimer définitivement « {media.title} » ?").classes("bs-title text-base")
                ui.label("Cette action est irréversible.").classes("text-sm mt-1").style("color:var(--text-muted)")

                async def _confirm() -> None:
                    await ctx.store.delete(media.id)
                    ui.notify(f"« {media.title} » supprimé.", type="positive")
                    confirm_dialog.close()
                    dialog.close()
                    await ctx.reload()

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    ui.button("Annuler", on_click=confirm_dialog.close).classes("bs-outline-btn")
                    ui.button("Confirmer la suppression", on_click=_confirm).classes("bs-danger-btn")
            confirm_dialog.open()

        async def _open_correction_dialog() -> None:
            correction_dialog = ui.dialog()
            with correction_dialog, ui.card().classes("bs-card w-full max-w-lg p-6"):
                ui.label(f"Corriger « {media.title} » via TMDB").classes("bs-title text-base")

                results_box = ui.column().classes("w-full mt-4")

                async def _apply(cand: dict) -> None:
                    await ctx.processor.enrich_media_with_tmdb_id(media.id, cand["id"], force=True)
                    ui.notify(f"« {media.title} » mis à jour depuis TMDB.", type="positive")
                    correction_dialog.close()
                    dialog.close()
                    await ctx.reload()

                def _render_results(candidates: list) -> None:
                    results_box.clear()
                    with results_box:
                        if not candidates:
                            ui.label("Aucun résultat.").style("color:var(--text-muted)")
                        for cand in candidates:
                            row = ui.element("div").classes("bs-card p-2 cursor-pointer mt-2") \
                                .on("click", lambda c=cand: _apply(c))
                            with row, ui.row().classes("w-full items-center gap-3"):
                                media_poster(cand.get("poster_url"), width="50px")
                                year = (cand.get("release_date") or "")[:4] or "—"
                                ui.label(f"{cand.get('title')} ({year})").classes("text-sm")

                with ui.row().classes("w-full items-center gap-2 mt-2"):
                    query_input = ui.input(value=media.title).classes("flex-grow")

                    async def _search() -> None:
                        query = (query_input.value or "").strip()
                        if not query:
                            return
                        results_box.clear()
                        with results_box:
                            ui.spinner("dots", size="2rem").classes("self-center")
                        candidates = await ctx.processor.search_candidates(query, is_series_flag=is_series(media.type))
                        _render_results(candidates)

                    ui.button(icon="search", on_click=_search).props("flat round")

                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Annuler", on_click=correction_dialog.close).classes("bs-outline-btn")

            correction_dialog.open()
            await _search()

        with ui.row().classes("w-full justify-between items-center mt-4"):
            with ui.row().classes("gap-2"):
                ui.button("Supprimer", on_click=_delete).classes("bs-danger-btn")
                ui.button("Corriger via TMDB", on_click=_open_correction_dialog).classes("bs-outline-btn")
            with ui.row().classes("gap-2"):
                ui.button("Fermer", on_click=dialog.close).classes("bs-outline-btn")
                ui.button("Enregistrer", on_click=_save).classes("bs-accent-btn")

    dialog.open()
