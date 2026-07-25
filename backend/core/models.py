from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime


class Media(BaseModel):
    id: str  # identifiant local (uuid, ou id Notion importé)
    title: str
    original_title: Optional[str] = None
    type: Optional[str] = None  # Film, Série, etc.
    status: Optional[str] = None  # Terminé, À voir, etc.
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
