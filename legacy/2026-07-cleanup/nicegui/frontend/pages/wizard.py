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
            thumb_elements: Dict[str, ui.element] = {}
            selected = {"id": candidates[0]["id"] if candidates else None}
            with ui.grid(columns=4).classes("w-full gap-3 mt-4"):
                for cand in candidates:
                    thumb_elements[cand["id"]] = _candidate_thumb(
                        cand, future, detail_box, thumb_elements, selected
                    )
            detail_box.move(target_index=-1)
            _render_detail(detail_box, candidates[0], future)

        with ui.row().classes("w-full justify-center mt-4"):
            ui.button("Ignorer cette fiche", on_click=lambda: _resolve(future, None)).classes("bs-outline-btn")


def _candidate_thumb(
    cand: Dict[str, Any],
    future: "asyncio.Future[Any]",
    detail_box: ui.element,
    thumb_elements: Dict[str, ui.element],
    selected: Dict[str, Any],
) -> ui.element:
    def _select() -> None:
        _render_detail(detail_box, cand, future)
        selected["id"] = cand["id"]
        for cid, el in thumb_elements.items():
            if cid == cand["id"]:
                el.style("border: 2px solid var(--accent);")
            else:
                el.style("border: 1px solid var(--border);")

    thumb = ui.element("div").classes("bs-card p-2 cursor-pointer").on("click", _select)
    if cand["id"] == selected["id"]:
        thumb.style("border: 2px solid var(--accent);")
    with thumb:
        media_poster(cand.get("poster_url"), height="120px")
        year = (cand.get("release_date") or "N/A")[:4]
        ui.badge(year).classes("bs-badge mt-1")
    return thumb


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
