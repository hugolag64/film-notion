"""Optional periodic refresh for the local media-server integration."""
import asyncio
import logging

from backend.config import Config
from backend.core.arr import RadarrClient, SonarrClient
from backend.core.jellyfin import JellyfinClient
from backend.core.media_server import MediaServerService
from backend.core.store import MediaStore
from backend.core.auth import AuthStore

logger = logging.getLogger(__name__)
_media_task: asyncio.Task | None = None


async def _media_loop():
    while True:
        await asyncio.sleep(Config.MEDIA_SYNC_INTERVAL_SEC)
        try:
            service = MediaServerService(
                MediaStore(Config.DB_PATH),
                radarr=RadarrClient(Config.RADARR_URL, Config.RADARR_API_KEY) if Config.radarr_enabled() else None,
                sonarr=SonarrClient(Config.SONARR_URL, Config.SONARR_API_KEY) if Config.sonarr_enabled() else None,
                jellyfin=JellyfinClient(
                    Config.JELLYFIN_URL, Config.JELLYFIN_API_KEY,
                    server_id=Config.JELLYFIN_SERVER_ID,
                ) if Config.jellyfin_enabled() else None,
            )
            if Config.media_server_enabled():
                await service.sync_all()
            if jellyfin:
                for user in AuthStore(Config.DB_PATH).list_users():
                    if not user["is_active"] or not user.get("jellyfin_user_id"):
                        continue
                    try:
                        await service.sync_playback(user["id"], user["jellyfin_user_id"])
                    except Exception:
                        logger.exception("[playback-sync] Erreur pour %s", user["id"])
        except Exception:
            logger.exception("[media-sync] Erreur de synchronisation")


def start_media_server_sync():
    global _media_task
    if not (Config.media_server_enabled() or Config.jellyfin_enabled()) or Config.MEDIA_SYNC_INTERVAL_SEC <= 0:
        return
    if _media_task is None or _media_task.done():
        _media_task = asyncio.create_task(_media_loop())
