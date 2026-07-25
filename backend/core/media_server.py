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
