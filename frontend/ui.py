import asyncio
from typing import Dict, Any, List

from nicegui import ui

from backend.config import Config
from backend.core.notion import NotionService
from backend.core.processor import EnrichmentProcessor
from backend.core import stats as stats_mod
from backend.core import history as history_mod
from backend.core import ai as ai_mod
from backend.core.mapping import Values


@ui.page('/')
async def main_page():
    ui.add_head_html('''
    <style>
        body { background-color: #f8fafc; }
        .glass-card {
            background: white;
            border-radius: 16px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .media-card:hover {
            border-color: #6366f1;
            background-color: #f5f3ff;
        }
    </style>
    ''')

    state: Dict[str, Any] = {
        'all_medias': [],
        'medias': [],       # liste à traiter (dérivée)
        'force': False,
        'running': False,
    }

    processor = EnrichmentProcessor()

    # --- Wizard dialog (créé une fois) ---
    wizard_dialog = ui.dialog().props("persistent")
    with wizard_dialog:
        wizard_card = ui.card().classes("w-full max-w-2xl bg-white glass-card p-6")

    # --- Preview (dry-run) dialog ---
    preview_dialog = ui.dialog()
    with preview_dialog:
        preview_card = ui.card().classes("w-full max-w-2xl bg-white glass-card p-6")

    root = ui.column().classes("w-full max-w-5xl mx-auto p-4")

    # ============ Chargement ============

    def _compute_todo():
        if state['force']:
            state['medias'] = list(state['all_medias'])
        else:
            state['medias'] = [
                m for m in state['all_medias']
                if not (m.director and m.release_date and m.support) or not m.tmdb_ok
            ]

    async def load_data():
        root.clear()
        with root:
            ui.spinner('dots', size='3rem').classes('self-center')
        try:
            state['all_medias'] = await NotionService.fetch_all_media()
        except Exception as e:
            root.clear()
            ui.notify(f"Erreur de connexion à Notion : {e}", type='negative')
            with root:
                ui.label("Impossible de charger les données Notion.").classes("text-red-500")
            return
        _compute_todo()
        render_app()

    async def on_force_change(e):
        state['force'] = e.value
        _compute_todo()
        render_app()

    # ============ Layout à onglets ============

    def render_app():
        root.clear()
        with root:
            with ui.row().classes("w-full justify-between items-center mb-4"):
                ui.label("🎬 Backstage").classes("text-3xl font-extrabold text-slate-800")
                ui.button(icon="refresh", on_click=load_data).props("flat round color=grey")

            with ui.tabs().classes("w-full") as tabs:
                t_todo = ui.tab("À traiter", icon="auto_fix_high")
                t_stats = ui.tab("Statistiques", icon="insights")
                t_hist = ui.tab("Historique", icon="history")
                t_ai = ui.tab("Reco IA", icon="smart_toy") if Config.ai_enabled() else None

            with ui.tab_panels(tabs, value=t_todo).classes("w-full"):
                with ui.tab_panel(t_todo):
                    render_dashboard()
                with ui.tab_panel(t_stats):
                    render_stats()
                with ui.tab_panel(t_hist):
                    render_history()
                if t_ai:
                    with ui.tab_panel(t_ai):
                        render_ai()

    # ============ Onglet : à traiter ============

    def render_dashboard():
        if not state['medias']:
            with ui.column().classes("w-full items-center justify-center py-16 opacity-70"):
                ui.icon("check_circle", size="5rem", color="green-400")
                ui.label("Tout est à jour !").classes("text-xl font-medium mt-4 text-slate-600")
            _force_switch()
            return

        with ui.column().classes("w-full items-center mb-6 gap-2"):
            with ui.row().classes("gap-3"):
                ui.button("Lancer l'Enrichissement ✨", on_click=start_wizard) \
                    .props("color=indigo-600 rounded unelevated").classes("text-lg px-6 py-3 shadow-lg")
                ui.button("Prévisualiser (dry-run)", on_click=run_preview) \
                    .props("color=indigo-600 outline rounded").classes("px-4 py-3")
            _force_switch()

        ui.label(f"{len(state['medias'])} fiche(s) en attente :") \
            .classes("text-slate-500 font-medium mb-2 uppercase text-xs tracking-wider")
        with ui.card().classes("w-full glass-card p-0"):
            rows = [{'title': m.title} for m in state['medias']]
            columns = [{'name': 'title', 'label': 'Titre', 'field': 'title', 'align': 'left'}]
            ui.table(rows=rows, columns=columns).classes("w-full no-shadow").props("flat dense hide-header")

    def _force_switch():
        ui.switch(
            "Forcer le re-traitement (ignorer le cache)",
            value=state['force'], on_change=on_force_change,
        ).classes("text-xs text-slate-500")

    # ============ Wizard (auto + manuel) ============

    async def start_wizard():
        if not state['medias'] or state['running']:
            return
        state['running'] = True
        wizard_dialog.open()

        wizard_card.clear()
        with wizard_card.classes("items-center"):
            ui.icon("auto_fix_high", size="3rem").classes("mb-4 text-indigo-500 animate-pulse")
            ui.label("Enrichissement en cours...").classes("text-xl font-bold mb-2")
            status_label = ui.label("Préparation...").classes("text-gray-500 mb-4")
            progress = ui.linear_progress(value=0, show_value=False).classes("w-full h-2 mb-4 rounded")
            with ui.expansion("Journal d'activité", icon="list").classes("w-full border rounded"):
                log = ui.log().classes("w-full h-40 text-xs bg-slate-50 p-2")

        total = len(state['medias'])

        def progress_cb(done: int, _total: int, result: Dict[str, Any]):
            media = result['media']
            progress.set_value(done / total if total else 1)
            status_label.set_text(f"{done}/{total} traités")
            st = result['status']
            if st == 'PROCESSED':
                log.push(f"✅ {media.title} enrichi.")
            elif st == 'SKIPPED':
                log.push(f"⏩ {media.title} ignoré ({result.get('reason')}).")
            elif st == 'AMBIGUOUS':
                log.push(f"🤔 {media.title} : à confirmer manuellement.")
            elif st == 'ERROR':
                log.push(f"❌ {media.title} : {result.get('error')}")
                ui.notify(f"Erreur sur {media.title}", type='negative')

        counters = await processor.run_auto_pass(
            state['medias'], force=state['force'], progress_cb=progress_cb,
        )

        resolved = 0
        for amb in counters['ambiguous']:
            if await resolve_ambiguous(amb):
                resolved += 1
        counters['resolved'] = resolved
        render_wizard_finished(counters)

    async def resolve_ambiguous(amb: Dict[str, Any]) -> bool:
        title = amb['original_title']
        media_id = amb['media_id']
        candidates = amb['candidates']
        is_series = amb.get('is_series', False)
        future: asyncio.Future = asyncio.Future()

        render_manual_selection(title, candidates, future, media_id, is_series)
        tmdb_id = await future

        if tmdb_id:
            try:
                await processor.enrich_media_with_tmdb_id(media_id, tmdb_id)
                ui.notify(f"« {title} » enrichi.", type='positive')
                return True
            except Exception as e:
                ui.notify(f"Erreur enrichissement « {title} » : {e}", type='negative')
        return False

    def render_manual_selection(title: str, candidates: List[Dict[str, Any]],
                                future: asyncio.Future, media_id: str, is_series: bool):
        wizard_card.clear()
        with wizard_card:
            with ui.column().classes("w-full gap-3"):
                with ui.row().classes("items-center gap-3 p-2"):
                    ui.icon("find_in_page", color="indigo").classes("text-3xl")
                    with ui.column().classes("gap-0"):
                        ui.label(f"Ambiguïté : {title}").classes("text-lg font-bold")
                        ui.label("Choisissez le bon résultat, ou recherchez autrement").classes("text-xs text-slate-500")

                # Recherche manuelle libre
                with ui.row().classes("w-full items-center gap-2"):
                    search_input = ui.input(placeholder="Rechercher un autre titre…", value=title) \
                        .props("dense outlined").classes("flex-grow")
                    year_input = ui.input(placeholder="Année") \
                        .props("dense outlined").classes("w-24")

                    async def do_search():
                        q = search_input.value.strip()
                        if not q:
                            return
                        yr = None
                        if (year_input.value or "").strip().isdigit():
                            yr = int(year_input.value.strip())
                        new_cands = await processor.search_candidates(q, is_series_flag=is_series, year=yr)
                        render_manual_selection(q, new_cands, future, media_id, is_series)

                    ui.button(icon="search", on_click=do_search).props("flat round color=indigo")

                with ui.scroll_area().classes("h-[400px] pr-4"):
                    if not candidates:
                        ui.label("Aucun résultat. Essayez un autre titre ci-dessus.").classes("text-slate-400 p-4")
                    for cand in candidates:
                        _candidate_card(cand, future)

                with ui.row().classes("w-full justify-center"):
                    ui.button("Ignorer cette fiche", on_click=lambda: _resolve(future, None)).props("flat color=grey")

    def _candidate_card(cand: Dict[str, Any], future: asyncio.Future):
        with ui.card().classes("media-card w-full mb-3 cursor-pointer p-4 transition-all"):
            with ui.row().classes("no-wrap items-start w-full gap-4"):
                poster = cand.get('poster_url')
                if poster:
                    ui.image(poster).classes("w-16 rounded shadow-sm")
                else:
                    ui.icon("movie", size="2.5rem").classes("text-slate-300 w-16")

                with ui.column().classes("flex-grow gap-1"):
                    with ui.row().classes("justify-between w-full items-center"):
                        ui.label(cand['title']).classes("font-bold text-slate-800")
                        ui.badge((cand.get('release_date') or 'N/A')[:4], color="orange")

                    meta = []
                    if cand.get('director'):
                        meta.append(f"🎬 {cand['director']}")
                    if cand.get('imdb_rating'):
                        meta.append(f"⭐ IMDb {cand['imdb_rating']}")
                    if cand.get('rated'):
                        meta.append(f"🔞 {cand['rated']}")
                    if meta:
                        ui.label("   ".join(meta)).classes("text-xs text-slate-500")

                    overview = cand.get('overview')
                    if overview:
                        snippet = overview[:160] + ("…" if len(overview) > 160 else "")
                        ui.label(snippet).classes("text-xs text-slate-400")

                    for tag in (cand.get('suggested_tags') or []):
                        ui.badge(tag, color="teal").classes("opacity-80")

                    ui.button("CE TITRE", on_click=lambda id=cand['id']: _resolve(future, id)) \
                        .props("unelevated rounded color=indigo").classes("mt-2 w-full")

    def _resolve(future: asyncio.Future, value):
        if not future.done():
            future.set_result(value)

    def render_wizard_finished(counters: Dict[str, Any]):
        wizard_card.clear()
        with wizard_card.classes("items-center text-center"):
            ui.icon("check_circle", size="4rem", color="green")
            ui.label("Enrichissement Terminé !").classes("text-2xl font-bold mt-4 mb-2")
            ui.label(
                f"✅ {counters['processed']} auto · ✨ {counters.get('resolved', 0)} manuels · "
                f"⏩ {counters['skipped']} ignorés · ❌ {counters['errors']} erreurs"
            ).classes("text-gray-500 mb-6")
            state['running'] = False
            ui.button("Fermer et Rafraîchir",
                      on_click=lambda: [wizard_dialog.close(), load_data()]).props("color=green")

    # ============ Dry-run (prévisualisation) ============

    async def run_preview():
        if not state['medias']:
            return
        preview_card.clear()
        preview_dialog.open()
        with preview_card.classes("items-center"):
            ui.icon("visibility", size="2.5rem").classes("text-indigo-500 mb-2")
            ui.label("Prévisualisation (aucune écriture)").classes("text-lg font-bold")
            spin = ui.spinner('dots', size='2rem')

        previews = []
        for media in state['medias']:
            res = await processor.process_one_media(media, force=state['force'], dry_run=True)
            if res['status'] == 'PREVIEW' and res['changes']:
                previews.append(res)

        spin.delete()
        with preview_card:
            if not previews:
                ui.label("Aucun changement à appliquer.").classes("text-slate-500 py-6")
            else:
                ui.label(f"{len(previews)} fiche(s) seraient modifiées :").classes("text-slate-500 text-sm mb-2")
                with ui.scroll_area().classes("h-[420px] w-full"):
                    for p in previews:
                        with ui.card().classes("w-full mb-2 p-3 glass-card"):
                            ui.label(f"🎬 {p['title']}").classes("font-bold text-slate-800")
                            for ch in p['changes']:
                                ui.label(f"• {ch['field']} : {ch['old']} → {ch['new']}") \
                                    .classes("text-xs text-slate-500")
            ui.button("Fermer", on_click=preview_dialog.close).props("flat color=grey").classes("mt-2")

    # ============ Onglet : statistiques + doublons ============

    def render_stats():
        s = stats_mod.compute_stats(state['all_medias'])
        with ui.row().classes("w-full gap-4 flex-wrap mb-6"):
            _stat_card("Total", s['total'], "movie")
            _stat_card("Enrichis", f"{s['enriched']} ({s['enriched_pct']}%)", "check_circle")
            _stat_card("Notés", s['rated'], "star")
            _stat_card("Sans réalisateur", s['without_director'], "person_off")

        with ui.row().classes("w-full gap-4 flex-wrap"):
            with ui.card().classes("glass-card p-4 flex-grow"):
                ui.label("Top genres").classes("font-bold text-slate-700 mb-2")
                for name, count in s['top_genres']:
                    ui.label(f"{name} — {count}").classes("text-sm text-slate-500")
            with ui.card().classes("glass-card p-4 flex-grow"):
                ui.label("Par support").classes("font-bold text-slate-700 mb-2")
                for name, count in s['by_support']:
                    ui.label(f"{name} — {count}").classes("text-sm text-slate-500")

        dups = stats_mod.find_duplicates(state['all_medias'])
        with ui.card().classes("glass-card p-4 w-full mt-4"):
            ui.label(f"Doublons potentiels ({len(dups)})").classes("font-bold text-slate-700 mb-2")
            if not dups:
                ui.label("Aucun doublon détecté.").classes("text-sm text-slate-400")
            for d in dups:
                ui.label(f"⚠️ {d['title']} — {d['count']} fiches").classes("text-sm text-amber-600")

    def _stat_card(label, value, icon):
        with ui.card().classes("glass-card p-4 items-center flex-grow"):
            ui.icon(icon, size="1.8rem").classes("text-indigo-500")
            ui.label(str(value)).classes("text-2xl font-extrabold text-slate-800")
            ui.label(label).classes("text-xs text-slate-500 uppercase tracking-wide")

    # ============ Onglet : historique ============

    def render_history():
        entries = history_mod.read_recent(limit=50)
        if not entries:
            ui.label("Aucune modification enregistrée pour le moment.").classes("text-slate-400 py-6")
            return
        with ui.column().classes("w-full gap-2"):
            for e in entries:
                with ui.card().classes("w-full p-3 glass-card"):
                    with ui.row().classes("justify-between w-full items-center"):
                        ui.label(f"🎬 {e.get('title', '?')}").classes("font-bold text-slate-800")
                        ui.badge(e.get('source', 'auto'),
                                 color="indigo" if e.get('source') == 'manual' else "teal")
                    ts = (e.get('ts', '')[:19]).replace('T', ' ')
                    ui.label(f"{ts} · {', '.join(e.get('fields', []))}").classes("text-xs text-slate-400")

    # ============ Onglet : recommandations IA ============

    def render_ai():
        with ui.column().classes("w-full gap-3"):
            ui.label("Recommandations personnalisées (Claude)").classes("text-lg font-bold text-slate-700")
            ui.label("Basé sur vos films notés, parmi votre liste « à regarder ».").classes("text-sm text-slate-500")
            result_box = ui.column().classes("w-full")

            async def recommend():
                result_box.clear()
                with result_box:
                    spin = ui.spinner('dots', size='2rem')
                watched = [
                    {'title': m.title, 'rating': m.rating, 'genres': m.categories}
                    for m in state['all_medias'] if m.rating
                ]
                candidates = [
                    {'title': m.title, 'genres': m.categories}
                    for m in state['all_medias'] if m.status == Values.STATUS_TO_WATCH
                ]
                try:
                    text = await ai_mod.recommend(watched, candidates)
                    result_box.clear()
                    with result_box:
                        with ui.card().classes("glass-card p-4 w-full"):
                            ui.markdown(text)
                except ai_mod.AIUnavailable as e:
                    result_box.clear()
                    ui.notify(f"IA indisponible : {e}", type='negative')

            ui.button("Recommander 3 films ✨", on_click=recommend) \
                .props("color=indigo-600 unelevated rounded").classes("self-start")

    # --- Initial load ---
    ui.timer(0.1, load_data, once=True)
