"""Optional periodic refresh for the local media-server integration."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from backend.config import Config
from backend.core.arr import RadarrClient, SonarrClient
from backend.core.jellyfin import JellyfinClient
from backend.core.seerr import SeerrClient
from backend.core.media_server import MediaServerService
from backend.core.store import MediaStore
from backend.core.auth import AuthStore
from backend.core.models import Notification
from backend.core.backup import create_backup, get_backup_status

logger = logging.getLogger(__name__)
_media_task: asyncio.Task | None = None


def should_sync_media_servers() -> bool:
    return Config.media_server_enabled() or Config.jellyfin_enabled()


async def _media_loop():
    while True:
        await asyncio.sleep(Config.MEDIA_SYNC_INTERVAL_SEC)
        try:
            service = MediaServerService(
                MediaStore(Config.DB_PATH),
                radarr=RadarrClient(Config.RADARR_URL, Config.RADARR_API_KEY) if Config.radarr_enabled() else None,
                sonarr=SonarrClient(Config.SONARR_URL, Config.SONARR_API_KEY) if Config.sonarr_enabled() else None,
                seerr=SeerrClient(Config.SEERR_URL, Config.SEERR_API_KEY) if Config.seerr_enabled() else None,
                jellyfin=JellyfinClient(
                    Config.JELLYFIN_URL, Config.JELLYFIN_API_KEY,
                    server_id=Config.JELLYFIN_SERVER_ID,
                ) if Config.jellyfin_enabled() else None,
            )
            if should_sync_media_servers():
                await service.sync_all()
            await service.store.expire_rentals(datetime.now(timezone.utc))
            if Config.media_server_enabled() or Config.jellyfin_enabled():
                await notify_automatic_events(service, service.store, AuthStore(Config.DB_PATH))
            if service.jellyfin:
                for user in AuthStore(Config.DB_PATH).list_users():
                    if not user["is_active"] or not user.get("jellyfin_user_id"):
                        continue
                    try:
                        await service.sync_playback(user["id"], user["jellyfin_user_id"])
                    except Exception:
                        logger.exception("[playback-sync] Erreur pour %s", user["id"])
            try:
                await backup_if_due()
            except Exception:
                logger.exception("[backup] Erreur de sauvegarde")
        except Exception:
            logger.exception("[media-sync] Erreur de synchronisation")


async def backup_if_due(*, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    status = await asyncio.to_thread(get_backup_status, Config.BACKUP_DIR)
    latest = status.get("latest")
    if latest:
        created_at = datetime.fromisoformat(latest["created_at"])
        if now - created_at < timedelta(hours=Config.BACKUP_INTERVAL_HOURS):
            return latest
    return await asyncio.to_thread(
        create_backup, Config.DB_PATH, Config.BACKUP_DIR,
        retention_days=Config.BACKUP_RETENTION_DAYS, now=now,
    )


async def notify_automatic_events(service, store, auth_store, *, now: datetime | None = None):
    """Create deduplicated internal notifications from the current server state."""
    now = now or datetime.now(timezone.utc)
    users = auth_store.list_users()
    names = {user["id"]: user["display_name"] for user in users}
    for item in await store.list_admin_rentals():
        rental = item["rental"]
        if rental.status not in {"available", "keep_requested"}:
            continue
        if rental.expires_at and rental.expires_at <= now + timedelta(days=2):
            expiry_day = rental.expires_at.date().isoformat()
            label = "série" if rental.rental_scope == "series" else "film"
            await store.create_notification(Notification(
                id=str(uuid.uuid4()), backstage_user_id=rental.backstage_user_id,
                kind="rental_expiring",
                message=f"La location de la {label} {item['media_title']} expire le {rental.expires_at.astimezone().strftime('%d/%m/%Y')}.",
                dedupe_key=f"rental_expiring:{rental.id}:{expiry_day}", created_at=now,
            ))

    for availability in await store.list_availabilities():
        if availability.state != "available":
            continue
        for item in await store.list_admin_rentals():
            rental = item["rental"]
            if rental.media_id != availability.media_id or rental.status not in {"available", "keep_requested"}:
                continue
            sync_day = (availability.last_synced_at or now).date().isoformat()
            await store.create_notification(Notification(
                id=str(uuid.uuid4()), backstage_user_id=rental.backstage_user_id,
                kind="media_available", message=f"{item['media_title']} est disponible sur Jellyfin.",
                dedupe_key=f"media_available:{rental.id}:{sync_day}", created_at=now,
            ))

    storage = await service.storage_status()
    if storage.get("low_space") or storage.get("temporary_quota_reached"):
        reason = "espace disque faible" if storage.get("low_space") else "quota temporaire atteint"
        for user in users:
            if user["role"] != "admin":
                continue
            await store.create_notification(Notification(
                id=str(uuid.uuid4()), backstage_user_id=user["id"], kind="storage_alert",
                message=f"Alerte stockage : {reason}.",
                dedupe_key=f"storage_alert:{now.date().isoformat()}:{reason}", created_at=now,
            ))


def start_media_server_sync():
    global _media_task
    if not (Config.media_server_enabled() or Config.jellyfin_enabled() or Config.BACKUP_INTERVAL_HOURS > 0) or Config.MEDIA_SYNC_INTERVAL_SEC <= 0:
        return
    if _media_task is None or _media_task.done():
        _media_task = asyncio.create_task(_media_loop())


_cinema_task: asyncio.Task | None = None


async def run_cinema_sync_once():
    """Une passe : programmation du Ciné Grand Sud, puis dates de sortie des films suivis."""
    from backend.core.cinema_store import CinemaStore
    from backend.core.cinema_sync import (
        fetch_site_page, refresh_cinema, refresh_tracked_release_dates, reunion_now,
    )
    from backend.core.tmdb import TMDBClient

    store = MediaStore(Config.DB_PATH)
    cinema = CinemaStore(Config.DB_PATH)
    try:
        tmdb = TMDBClient()
    except ValueError:
        logger.warning("[cinema] TMDB non configuré : association des films ignorée")
        tmdb = None
    try:
        await refresh_cinema(store, cinema, tmdb, fetch_site_page, reunion_now())
    except Exception:
        logger.exception("[cinema] Erreur de synchronisation")
    if tmdb is not None:
        try:
            await refresh_tracked_release_dates(store, cinema, tmdb, reunion_now().date())
        except Exception:
            logger.exception("[cinema] Erreur de relecture des dates de sortie")


async def _cinema_loop():
    while True:
        await run_cinema_sync_once()
        await asyncio.sleep(max(Config.CINEMA_REFRESH_HOURS, 1) * 3600)


def start_cinema_sync():
    global _cinema_task
    if not Config.CINEMA_ENABLED:
        return
    if _cinema_task is None or _cinema_task.done():
        _cinema_task = asyncio.create_task(_cinema_loop())
