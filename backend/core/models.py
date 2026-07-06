from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class Media(BaseModel):
    id: str  # identifiant local (uuid, ou id Notion importé)
    title: str
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

    # URL de l'image de couverture
    cover_url: Optional[str] = None
