"""Shared models for the local media-server integration."""
from datetime import datetime, timedelta
from datetime import timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.core.playback import PlaybackProgress
from backend.config import Config


AvailabilityState = Literal[
    "requested", "searching", "downloading", "imported", "available", "error",
]
Provider = Literal["radarr", "sonarr"]


class Availability(BaseModel):
    media_id: str
    provider: Provider
    arr_id: Optional[int] = None
    jellyfin_id: Optional[str] = None
    state: AvailabilityState = "requested"
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)
    root_folder: Optional[str] = None
    quality_profile_id: Optional[int] = None
    language_profile_id: Optional[int] = None
    last_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None


class MediaServerService:
    """Maps Arr/Jellyfin state into durable, UI-safe availability records."""

    def __init__(self, store, *, radarr=None, sonarr=None, jellyfin=None, seerr=None):
        self.store = store
        self.radarr = radarr
        self.sonarr = sonarr
        self.jellyfin = jellyfin
        self.seerr = seerr

    async def add(
        self, media, quality_profile_id: Optional[int], root_folder: Optional[str],
        language_profile_id: Optional[int], monitor: str,
    ) -> Availability:
        if not media.tmdb_id:
            raise ValueError("Associez d'abord ce média à TMDB")
        provider = "sonarr" if media.type == "Série" else "radarr"
        if self.seerr:
            remote = await self.seerr.request_media(
                tmdb_id=media.tmdb_id, media_type=media.type,
                quality_profile_id=None, root_folder=None,
                language_profile_id=None, monitor=monitor,
            )
        elif media.type == "Série":
            if not self.sonarr or quality_profile_id is None or not root_folder or language_profile_id is None:
                raise RuntimeError("Sonarr n'est pas configuré")
            remote = await self.sonarr.add_series(
                media.tmdb_id, quality_profile_id, language_profile_id, root_folder, monitor,
            )
        else:
            if not self.radarr or quality_profile_id is None or not root_folder:
                raise RuntimeError("Radarr n'est pas configuré")
            remote = await self.radarr.add_movie(media.tmdb_id, quality_profile_id, root_folder)
        return await self.store.upsert_availability(Availability(
            media_id=media.id, provider=provider, arr_id=None if self.seerr else remote.get("id"),
            state="requested", root_folder=root_folder,
            quality_profile_id=quality_profile_id, language_profile_id=language_profile_id,
            last_synced_at=datetime.now(timezone.utc),
        ))

    async def sync_media(self, media_id: str) -> Optional[Availability]:
        media = await self.store.fetch_one(media_id)
        if not media or not media.tmdb_id:
            return None
        provider = "sonarr" if media.type == "Série" else "radarr"
        arr = self.sonarr if provider == "sonarr" else self.radarr
        if arr is None:
            return await self.store.get_availability(media_id)
        try:
            remote = next((item for item in await arr.list_library() if item.get("tmdbId") == media.tmdb_id), None)
            if not remote:
                return await self.store.get_availability(media_id)
            queue_id_key = "seriesId" if provider == "sonarr" else "movieId"
            queue_item = next(
                (item for item in await arr.list_queue() if item.get(queue_id_key) == remote.get("id")),
                None,
            )
            jellyfin_item = await self.jellyfin.find_by_tmdb(media.tmdb_id, media.type) if self.jellyfin else None
            progress_percent = None
            last_error = None
            if queue_item and queue_item.get("errorMessage"):
                state = "error"
                last_error = str(queue_item["errorMessage"])
            elif queue_item and isinstance(queue_item.get("size"), (int, float)) and queue_item["size"] > 0:
                progress_percent = round((1 - queue_item.get("sizeleft", queue_item["size"]) / queue_item["size"]) * 100)
                state = "downloading"
            elif queue_item:
                state = "searching"
            else:
                state = "available" if jellyfin_item else "imported" if remote.get("hasFile") else "requested"
            availability = Availability(
                media_id=media.id, provider=provider, arr_id=remote.get("id"),
                jellyfin_id=jellyfin_item.get("Id") if jellyfin_item else None,
                state=state, progress_percent=progress_percent, last_error=last_error,
                last_synced_at=datetime.now(timezone.utc),
            )
            if availability.arr_id is not None:
                await self.store.clear_arr_id_conflict(provider, availability.arr_id, media.id)
            saved = await self.store.upsert_availability(availability)
            if availability.state == "available" and availability.jellyfin_id:
                available_at = datetime.now(timezone.utc)
                size_bytes = remote.get("sizeOnDisk")
                if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
                    size_bytes = None
                await self.store.mark_rentals_available(
                    media.id, available_at, available_at + timedelta(days=21),
                    int(size_bytes) if size_bytes is not None else None,
                )
            if remote.get("hasFile") or availability.jellyfin_id:
                await self.store.update(media.id, {"support": "Serveur"})
            return saved
        except Exception:
            current = await self.store.get_availability(media_id)
            if current:
                return await self.store.upsert_availability(current.model_copy(update={
                    "last_error": "Synchronisation indisponible",
                }))
            return None

    async def playback_url(self, media_id: str) -> Optional[str]:
        availability = await self.store.get_availability(media_id)
        if availability and availability.jellyfin_id and self.jellyfin:
            return self.jellyfin.playback_url(availability.jellyfin_id)
        return None

    async def playback_manifest(self, media_id: str) -> Optional[dict[str, str]]:
        availability = await self.store.get_availability(media_id)
        if availability and availability.jellyfin_id and self.jellyfin:
            return {
                "item_id": availability.jellyfin_id,
                "url": self.jellyfin.playback_manifest_url(availability.jellyfin_id),
            }
        return None

    async def playback_resource(self, media_id: str, resource_path: str, query: dict[str, str]):
        availability = await self.store.get_availability(media_id)
        if not availability or not availability.jellyfin_id or not self.jellyfin:
            return None
        return await self.jellyfin.fetch_playback_resource(availability.jellyfin_id, resource_path, query)

    async def import_existing_libraries(self) -> dict[str, int]:
        """Link already-managed Arr items to local TMDB-linked records."""
        medias = await self.store.fetch_all()
        linked = 0
        created = 0
        for provider, client, media_type in (
            ("radarr", self.radarr, "Film"),
            ("sonarr", self.sonarr, "Série"),
        ):
            if client is None:
                continue
            for remote in await client.list_library():
                tmdb_id = remote.get("tmdbId")
                media = next((item for item in medias if item.type == media_type and item.tmdb_id == tmdb_id), None)
                if not media:
                    title = remote.get("title") or remote.get("sortTitle") or "Sans titre"
                    media = await self.store.create({
                        "title": title, "type": media_type, "tmdb_id": tmdb_id,
                        "tmdb_ok": bool(tmdb_id), "status": "À regarder",
                    })
                    medias.append(media)
                    created += 1
                await self.store.upsert_availability(Availability(
                    media_id=media.id, provider=provider, arr_id=remote.get("id"),
                    state="imported" if remote.get("hasFile") else "requested",
                    last_synced_at=datetime.now(timezone.utc),
                ))
                linked += 1
        return {"linked": linked, "created": created}

    async def sync_all(self) -> dict[str, int]:
        synced = 0
        for media in await self.store.fetch_all():
            if media.tmdb_id and media.type in {"Film", "Série"}:
                if await self.sync_media(media.id):
                    synced += 1
        return {"synced": synced}

    async def activity(self) -> dict[str, list[dict[str, Any]]]:
        disks: list[dict[str, Any]] = []
        for provider, client in (("radarr", self.radarr), ("sonarr", self.sonarr)):
            if client is None or not hasattr(client, "disk_space"):
                continue
            try:
                for disk in await client.disk_space():
                    disks.append({"provider": provider, **disk})
            except Exception:
                continue
        return {
            "items": [availability.model_dump(mode="json") for availability in await self.store.list_availabilities()],
            "disks": disks,
        }

    async def storage_status(self) -> dict[str, Any]:
        activity = await self.activity()
        disks = activity["disks"]
        data_disks = [
            disk for disk in disks
            if str(disk.get("path", "")).startswith("/data")
        ]
        relevant_disks = data_disks or disks
        free_values = [
            int(disk["freeSpace"])
            for disk in relevant_disks
            if isinstance(disk.get("freeSpace"), (int, float))
        ]
        min_free_bytes = min(free_values) if free_values else None
        temporary_bytes = await self.store.active_temporary_bytes()
        return {
            "min_free_bytes": min_free_bytes,
            "min_free_gb": round(min_free_bytes / 1024**3, 2) if min_free_bytes is not None else None,
            "temporary_bytes": temporary_bytes,
            "temporary_gb": round(temporary_bytes / 1024**3, 2),
            "min_free_threshold_bytes": Config.min_free_bytes(),
            "min_free_threshold_gb": Config.MIN_FREE_GB,
            "temporary_max_bytes": Config.temporary_max_bytes(),
            "temporary_max_gb": Config.TEMPORARY_MAX_GB,
            "low_space": min_free_bytes is not None and min_free_bytes < Config.min_free_bytes(),
            "temporary_quota_reached": temporary_bytes >= Config.temporary_max_bytes(),
        }

    async def sync_playback(self, backstage_user_id: str, jellyfin_user_id: str) -> dict[str, int]:
        if not self.jellyfin:
            raise RuntimeError("Jellyfin n'est pas configuré")
        remote_items = await self.jellyfin.user_playback(jellyfin_user_id)
        synced = 0
        for item in remote_items:
            media_id, episode_id = await self.store.resolve_playback_item(item)
            progress = PlaybackProgress(
                backstage_user_id=backstage_user_id,
                jellyfin_id=item["jellyfin_id"],
                media_id=media_id,
                episode_id=episode_id,
                title=item["title"],
                series_title=item.get("series_title"),
                season_number=item.get("season_number"),
                episode_number=item.get("episode_number"),
                position_ticks=item.get("position_ticks", 0),
                runtime_ticks=item.get("runtime_ticks", 0),
                percent=min(100, max(0, float(item.get("percent", 0)))),
                played=bool(item.get("played")) or float(item.get("percent", 0)) >= 95,
                last_played_at=item.get("last_played_at"),
            )
            await self.store.upsert_playback(progress)
            if media_id and progress.position_ticks > 0:
                first_played_at = datetime.now(timezone.utc)
                await self.store.mark_rental_first_played(
                    backstage_user_id, media_id, first_played_at, first_played_at + timedelta(days=7),
                )
            synced += 1
        return {"synced": synced}

    async def playback_summary(self, backstage_user_id: str) -> dict[str, Any]:
        return {
            "resume": await self.store.list_resume_progress(backstage_user_id),
            "next_episodes": await self.store.list_next_episodes(backstage_user_id),
            "recently_completed": await self.store.list_recently_completed(backstage_user_id),
            "last_synced_at": await self.store.last_playback_sync(backstage_user_id),
        }
