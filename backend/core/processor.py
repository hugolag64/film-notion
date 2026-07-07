import asyncio
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Callable

from backend.core.models import Media
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient
from backend.core.cache_service import CacheService
from backend.core.mapping import Values, GENRE_TAG_RULES, is_series
from backend.core import history, omdb
from backend.core.diff import summarize_changes

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 5


class EnrichmentProcessor:
    def __init__(self, store: MediaStore):
        self.store = store
        self.tmdb = TMDBClient()
        self.cache = CacheService()

    async def process_all(self, force: bool = False):
        """Lance le processus d'enrichissement complet (Mode Automatique)."""
        logger.info("Début de l'enrichissement...")
        medias = await self.store.fetch_all()

        updated_count = 0
        skipped_count = 0

        for media in medias:
            result = await self.process_one_media(media, force=force)
            if result['status'] == 'PROCESSED':
                updated_count += 1
            elif result['status'] in ('SKIPPED', 'AMBIGUOUS'):
                skipped_count += 1

        logger.info("Enrichissement terminé. Mis à jour : %s, Ignorés : %s", updated_count, skipped_count)
        return updated_count, skipped_count

    async def run_auto_pass(
        self,
        medias: List[Media],
        force: bool = False,
        progress_cb: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> Dict[str, Any]:
        """
        Traite tous les médias en parallèle (concurrence bornée).
        Les cas non ambigus sont enrichis automatiquement ; les ambigus sont
        collectés pour résolution manuelle ultérieure (interactive, séquentielle).

        `progress_cb(done, total, result)` est appelé après chaque média terminé.
        Retourne {'processed', 'skipped', 'errors', 'ambiguous': [result, ...]}.
        """
        total = len(medias)
        semaphore = asyncio.Semaphore(max(1, concurrency))
        counters = {'processed': 0, 'skipped': 0, 'errors': 0, 'ambiguous': []}
        done = 0

        async def worker(media: Media) -> Dict[str, Any]:
            async with semaphore:
                return media, await self.process_one_media(media, force=force)

        tasks = [asyncio.create_task(worker(m)) for m in medias]
        for coro in asyncio.as_completed(tasks):
            media, result = await coro
            done += 1
            status = result['status']
            if status == 'PROCESSED':
                counters['processed'] += 1
            elif status == 'AMBIGUOUS':
                counters['ambiguous'].append(result)
            elif status == 'ERROR':
                counters['errors'] += 1
            else:
                counters['skipped'] += 1

            if progress_cb:
                progress_cb(done, total, {'media': media, **result})

        return counters

    async def process_one_media(self, media: Media, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        Traite un seul média et retourne son statut :
        - {'status': 'SKIPPED', 'reason': '...'}
        - {'status': 'PROCESSED', 'title': '...', 'tmdb_id': ...}
        - {'status': 'PREVIEW', 'changes': [...], ...}        (dry_run)
        - {'status': 'AMBIGUOUS', 'candidates': [...], 'original_title': '...', 'media_id': '...'}
        - {'status': 'ERROR', 'error': '...'}
        """
        try:
            if not force and self.cache.is_processed(media):
                return {'status': 'SKIPPED', 'reason': 'Déjà traité'}

            missing_info = self._get_missing_fields(media)

            if not missing_info and media.status and media.support and media.director and media.release_date:
                if not dry_run:
                    self.cache.mark_as_processed(media)
                return {'status': 'SKIPPED', 'reason': 'Fiche complète'}

            series = is_series(media.type)
            year = media.release_date.year if media.release_date else None
            tmdb_results = await self.tmdb.search(media.title, is_series=series, year=year)

            best_match = self._find_best_match(media, tmdb_results)

            if best_match:
                tmdb_details = await self.tmdb.get_details(best_match['id'], is_series=series)
                updates, poster_url = self._prepare_updates(media, tmdb_details)

                cover_todo = poster_url if (poster_url and not media.cover_url) else None
                changes = summarize_changes(media, updates, poster_url=cover_todo)

                if dry_run:
                    return {
                        'status': 'PREVIEW',
                        'title': best_match['title'],
                        'tmdb_id': best_match['id'],
                        'media_id': media.id,
                        'changes': changes,
                    }

                if updates or cover_todo:
                    await self._apply_updates(media.id, updates, cover_url=cover_todo)
                    history.record(media.id, media.title, changes, source="auto")
                    await self._mark_processed_after_update(media.id, media)
                    return {'status': 'PROCESSED', 'title': best_match['title'], 'tmdb_id': best_match['id']}

                self.cache.mark_as_processed(media)
                return {'status': 'SKIPPED', 'reason': 'Aucune mise à jour nécessaire'}

            # Aucun match évident -> on enrichit les candidats pour le wizard
            candidates = await self._enrich_candidates(tmdb_results, is_series=series)
            return {
                'status': 'AMBIGUOUS',
                'candidates': candidates,
                'original_title': media.title,
                'media_id': media.id,
                'is_series': series,
            }

        except Exception as e:
            logger.exception("Erreur lors du traitement de %s: %s", media.title, e)
            return {'status': 'ERROR', 'error': str(e)}

    async def search_candidates(self, query: str, is_series_flag: bool = False, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Recherche manuelle libre (utilisée par le wizard quand TMDB ne trouve rien)."""
        results = await self.tmdb.search(query, is_series=is_series_flag, year=year)
        return await self._enrich_candidates(results, is_series=is_series_flag)

    async def _enrich_candidates(self, results: List[Dict[str, Any]], is_series: bool = False) -> List[Dict[str, Any]]:
        """Récupère UNE seule fois les détails de chaque candidat (réal, genres, tags, affiche, IMDb)."""
        for cand in results:
            details = await self.tmdb.get_details(cand['id'], is_series=is_series)
            if details:
                cand['director'] = self.tmdb.get_director(details)
                genres = self.tmdb.get_genres(details)
                cand['genres'] = genres
                cand['suggested_tags'] = self._map_genres_to_tags(genres)
                cand['overview'] = details.get('overview', '')
            cand['poster_url'] = self.tmdb.poster_url_from_path(cand.get('poster_path'), size="w185")

            # Enrichissement OMDb optionnel (note IMDb + classification d'âge)
            year = self._result_year(cand)
            omdb_data = await omdb.fetch(cand.get('title', ''), year=year)
            if omdb_data:
                cand['imdb_rating'] = omdb_data.get('imdb_rating')
                cand['rated'] = omdb_data.get('rated')
        return results

    def _get_missing_fields(self, media: Media) -> List[str]:
        missing = []
        if not media.director:
            missing.append("director")
        if not media.release_date:
            missing.append("release_date")
        if not media.synopsis:
            missing.append("synopsis")
        if not media.categories:
            missing.append("categories")
        return missing

    def _find_best_match(self, media: Media, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Score chaque résultat (titre + année + popularité) et retourne le meilleur
        au-dessus d'un seuil de confiance ; sinon None (ambiguïté).
        """
        if not results:
            return None

        query_norm = media.title.lower().strip()
        query_year = media.release_date.year if media.release_date else None

        best, best_score = None, 0.0
        for res in results:
            score = 0.0
            res_title = (res.get("title") or "").lower().strip()

            # Similarité de titre
            if res_title == query_norm:
                score += 1.0
            elif query_norm in res_title or res_title in query_norm:
                score += 0.6

            # Concordance d'année (forte si on l'a)
            if query_year:
                res_year = self._result_year(res)
                if res_year == query_year:
                    score += 0.5
                elif res_year and abs(res_year - query_year) <= 1:
                    score += 0.2

            # Bonus popularité (départage les homonymes obscurs)
            if res.get("popularity", 0) >= 5:
                score += 0.1

            if score > best_score:
                best, best_score = res, score

        # Seuil : titre exact, ou bonne similarité confortée par l'année
        return best if best_score >= 0.8 else None

    @staticmethod
    def _result_year(res: Dict[str, Any]) -> Optional[int]:
        rd = res.get("release_date") or ""
        try:
            return datetime.strptime(rd, "%Y-%m-%d").year
        except ValueError:
            return None

    async def enrich_media_with_tmdb_id(self, media_id: str, tmdb_id: int, force: bool = False):
        """Enrichissement manuel : l'utilisateur a choisi explicitement ce film TMDB."""
        logger.info("Enrichissement manuel de %s avec TMDB ID %s", media_id, tmdb_id)

        media = await self.store.fetch_one(media_id)
        if media is None:
            raise ValueError("Impossible de récupérer la fiche")

        tmdb_details = await self.tmdb.get_details(tmdb_id, is_series=is_series(media.type))
        if not tmdb_details:
            raise ValueError("Impossible de récupérer les détails TMDB")

        updates, poster_url = self._prepare_updates(media, tmdb_details, force=force)

        cover_todo = poster_url if (not media.cover_url or force) else None
        changes = summarize_changes(media, updates, poster_url=cover_todo)

        await self._apply_updates(media_id, updates, cover_url=cover_todo)

        history.record(media_id, media.title, changes, source="manual")
        await self._mark_processed_after_update(media_id, media)
        return True

    def _map_genres_to_tags(self, genres: List[str]) -> List[str]:
        tags = [GENRE_TAG_RULES[g] for g in genres if g in GENRE_TAG_RULES]
        if "Horreur" in genres and "Thriller" in genres:
            tags.append("⚠️ Film dur")
        return list(set(tags))

    def _prepare_updates(self, media: Media, tmdb_data: Optional[Dict[str, Any]], force: bool = False) -> tuple[Dict[str, Any], Optional[str]]:
        updates: Dict[str, Any] = {}
        poster_url = None
        today = date.today()

        if not media.status:
            updates["status"] = Values.STATUS_TO_WATCH

        # Date (depuis la fiche si présente, sinon TMDB ; toujours écrasée si force)
        release_date = media.release_date
        if tmdb_data and (not release_date or force):
            release_str = tmdb_data.get("release_date")
            if release_str:
                try:
                    release_date = datetime.strptime(release_str, "%Y-%m-%d").date()
                    updates["release_date"] = release_date
                except ValueError:
                    pass

        # Règle Support
        if not media.support:
            if release_date and release_date > today:
                updates["support"] = Values.SUPPORT_CINEMA
            else:
                updates["support"] = Values.SUPPORT_DOWNLOAD

        if tmdb_data:
            if not media.director or force:
                director = self.tmdb.get_director(tmdb_data)
                if director:
                    updates["director"] = director

            if not media.synopsis or force:
                overview = tmdb_data.get("overview")
                if overview:
                    updates["synopsis"] = overview[:2000]

            genres = self.tmdb.get_genres(tmdb_data)
            if (not media.categories or force) and genres:
                updates["categories"] = genres

            if (not media.tags or force) and genres:
                suggested_tags = self._map_genres_to_tags(genres)
                if suggested_tags:
                    updates["tags"] = suggested_tags

            updates["tmdb_ok"] = True
            poster_url = self.tmdb.get_poster_url(tmdb_data)

        return updates, poster_url

    async def _apply_updates(self, media_id: str, fields: Dict[str, Any], cover_url: Optional[str] = None):
        if cover_url:
            fields = {**fields, "cover_url": cover_url}
        success = await self.store.update(media_id, fields)
        if success:
            logger.info("Fiche locale mise à jour pour %s", media_id)
        else:
            logger.warning("Échec de mise à jour locale pour %s", media_id)

    async def _mark_processed_after_update(self, page_id: str, fallback: Media):
        """Recharge la fiche après écriture pour cacher l'empreinte de l'état réel."""
        fresh = await self.store.fetch_one(page_id)
        self.cache.mark_as_processed(fresh or fallback)
