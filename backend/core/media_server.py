"""Shared models for the local media-server integration."""
from datetime import datetime
from typing import Literal, Optional

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
