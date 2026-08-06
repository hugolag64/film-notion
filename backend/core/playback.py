"""Per-user playback state synchronized from Jellyfin."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class PlaybackProgress(BaseModel):
    backstage_user_id: str
    jellyfin_id: str
    media_id: Optional[str] = None
    episode_id: Optional[str] = None
    title: str
    series_title: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    position_ticks: int = 0
    runtime_ticks: int = 0
    percent: float = Field(default=0, ge=0, le=100)
    played: bool = False
    last_played_at: Optional[datetime] = None
    synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
