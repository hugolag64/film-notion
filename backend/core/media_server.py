"""Shared models for the local media-server integration."""
from datetime import datetime
from datetime import timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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

    def __init__(self, store, *, radarr=None, sonarr=None, jellyfin=None):
        self.store = store
        self.radarr = radarr
        self.sonarr = sonarr
        self.jellyfin = jellyfin

    async def add(
        self, media, quality_profile_id: int, root_folder: str,
        language_profile_id: Optional[int], monitor: str,
    ) -> Availability:
        if not media.tmdb_id:
            raise ValueError("Associez d'abord ce média à TMDB")
        if media.type == "Série":
            if not self.sonarr or language_profile_id is None:
                raise RuntimeError("Sonarr n'est pas configuré")
            remote = await self.sonarr.add_series(
                media.tmdb_id, quality_profile_id, language_profile_id, root_folder, monitor,
            )
            provider = "sonarr"
        else:
            if not self.radarr:
                raise RuntimeError("Radarr n'est pas configuré")
            remote = await self.radarr.add_movie(media.tmdb_id, quality_profile_id, root_folder)
            provider = "radarr"
        return await self.store.upsert_availability(Availability(
            media_id=media.id, provider=provider, arr_id=remote.get("id"),
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
            jellyfin_item = await self.jellyfin.find_by_tmdb(media.tmdb_id, media.type) if self.jellyfin else None
            availability = Availability(
                media_id=media.id, provider=provider, arr_id=remote.get("id"),
                jellyfin_id=jellyfin_item.get("Id") if jellyfin_item else None,
                state="available" if jellyfin_item else "imported" if remote.get("hasFile") else "requested",
                last_synced_at=datetime.now(timezone.utc),
            )
            saved = await self.store.upsert_availability(availability)
            if remote.get("hasFile") and not media.support:
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

    async def import_existing_libraries(self) -> int:
        """Link already-managed Arr items to local TMDB-linked records."""
        medias = await self.store.fetch_all()
        linked = 0
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
                    continue
                await self.store.upsert_availability(Availability(
                    media_id=media.id, provider=provider, arr_id=remote.get("id"),
                    state="imported" if remote.get("hasFile") else "requested",
                    last_synced_at=datetime.now(timezone.utc),
                ))
                linked += 1
        return linked
