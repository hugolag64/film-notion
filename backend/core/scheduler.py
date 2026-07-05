"""Synchronisation incrémentale automatique (optionnelle).

Active si SYNC_INTERVAL_MIN > 0. Toutes les N minutes, enrichit automatiquement
les fiches incomplètes (les cas ambigus sont ignorés — ils restent pour le wizard).
"""
import asyncio
import logging

from backend.config import Config
from backend.core.processor import EnrichmentProcessor

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _run_once():
    processor = EnrichmentProcessor()
    medias = await processor.notion.fetch_all_media()
    todo = [
        m for m in medias
        if not (m.director and m.release_date and m.support) or not m.tmdb_ok
    ]
    if not todo:
        logger.info("[sync] Rien à enrichir.")
        return
    counters = await processor.run_auto_pass(todo)
    logger.info(
        "[sync] Auto: %s enrichis, %s ambigus laissés, %s ignorés, %s erreurs",
        counters['processed'], len(counters['ambiguous']), counters['skipped'], counters['errors'],
    )


async def _loop():
    interval = Config.SYNC_INTERVAL_MIN * 60
    logger.info("Sync auto activée (toutes les %s min).", Config.SYNC_INTERVAL_MIN)
    while True:
        await asyncio.sleep(interval)
        try:
            await _run_once()
        except Exception as e:
            logger.exception("[sync] Erreur durant la synchronisation: %s", e)


def start():
    """Démarre la boucle de sync si configurée. À appeler dans la boucle asyncio de l'app."""
    global _task
    if Config.SYNC_INTERVAL_MIN <= 0:
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
