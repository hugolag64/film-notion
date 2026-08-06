from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional
from datetime import date, datetime


class Media(BaseModel):
    id: str  # identifiant local (uuid, ou id Notion importé)
    title: str
    original_title: Optional[str] = None
    type: Optional[str] = None  # Film, Série, etc.
    status: Optional[str] = None  # Terminé, À voir, etc.
    is_watchlist: bool = False  # projection personnalisée de l'utilisateur courant
    support: Optional[str] = None  # NAS, Netflix, etc.
    rating: Optional[str] = None

    release_date: Optional[date] = None
    director: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    synopsis: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    review: Optional[str] = None
    tmdb_ok: bool = False
    tmdb_id: Optional[int] = None

    # URL de l'image de couverture et de bannière horizontale
    cover_url: Optional[str] = None
    backdrop_url: Optional[str] = None

    # Acteurs principaux
    cast: List[str] = Field(default_factory=list)

    # Nouvelles métadonnées de visionnage (Stripe / A24 UI)
    watched_in_cinema: bool = False
    watched_date: Optional[str] = None
    created_at: Optional[datetime] = None


RentalStatus = Literal[
    "requested", "downloading", "available", "keep_requested", "kept", "expired", "cancelled",
]


class Rental(BaseModel):
    id: str
    media_id: str
    backstage_user_id: str
    status: RentalStatus = "requested"
    requested_at: datetime
    available_at: Optional[datetime] = None
    first_played_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    keep_requested_at: Optional[datetime] = None
    storage_policy: Literal["temporary", "permanent"] = "temporary"
    rental_scope: Literal["movie", "series"] = "movie"
    size_bytes: Optional[int] = Field(default=None, ge=0)
    keep_decision: Optional[Literal["accepted", "refused"]] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class Notification(BaseModel):
    id: str
    backstage_user_id: str
    kind: str
    message: str
    dedupe_key: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class UserMediaState(BaseModel):
    backstage_user_id: str
    media_id: str
    status: Optional[str] = None
    rating: Optional[str] = None
    review: Optional[str] = None
    is_favorite: bool = False
    is_watchlist: bool = False
    added_to_watchlist_at: Optional[datetime] = None
    first_started_at: Optional[datetime] = None
    last_interacted_at: datetime


RecommendationEventType = Literal[
    "shown", "picked", "dismissed", "more_like_this", "less_like_this",
    "question_answered", "session_completed", "skipped", "not_now",
    "hard_reject", "already_seen",
]


class RecommendationEvent(BaseModel):
    id: str
    backstage_user_id: str
    session_id: Optional[str] = None
    media_id: Optional[str] = None
    event_type: RecommendationEventType
    value: Optional[str] = None
    numeric_value: Optional[float] = None
    created_at: datetime


class RecommendationSession(BaseModel):
    id: str
    backstage_user_id: str
    question_count: int = 0
    session_preferences: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["active", "completed", "cancelled"] = "active"
    created_at: datetime
    completed_at: Optional[datetime] = None
