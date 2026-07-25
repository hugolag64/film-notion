"""Synchronisation incrémentale automatique (optionnelle).

Active si SYNC_INTERVAL_MIN > 0. Toutes les N minutes, enrichit automatiquement
les fiches incomplètes (les cas ambigus sont ignorés — ils restent pour le wizard).
"""
import asyncio
import logging

from backend.config import Config
from backend.core.processor import EnrichmentProcessor
from backend.core.store import MediaStore
from backend.core.arr import RadarrClient, SonarrClient
from backend.core.jellyfin import JellyfinClient
from backend.core.media_server import MediaServerService

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_media_task: asyncio.Task | None = None


async def _run_once():
    processor = EnrichmentProcessor(MediaStore(Config.DB_PATH))
    medias = await processor.store.fetch_all()
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


async def _media_loop():
    while True:
        await asyncio.sleep(Config.MEDIA_SYNC_INTERVAL_SEC)
        try:
            service = MediaServerService(
                MediaStore(Config.DB_PATH),
                radarr=RadarrClient(Config.RADARR_URL, Config.RADARR_API_KEY) if Config.radarr_enabled() else None,
                sonarr=SonarrClient(Config.SONARR_URL, Config.SONARR_API_KEY) if Config.sonarr_enabled() else None,
                jellyfin=JellyfinClient(Config.JELLYFIN_URL, Config.JELLYFIN_API_KEY) if Config.jellyfin_enabled() else None,
            )
            await service.sync_all()
        except Exception:
            logger.exception("[media-sync] Erreur de synchronisation")


def start_media_server_sync():
    global _media_task
    if not Config.media_server_enabled() or Config.MEDIA_SYNC_INTERVAL_SEC <= 0:
        return
    if _media_task is None or _media_task.done():
        _media_task = asyncio.create_task(_media_loop())
