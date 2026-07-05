from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import date

class Media(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str  # Notion Page ID
    title: str = Field(..., alias="Nom")
    type: Optional[str] = Field(None, alias="Type") # Film, Série, etc.
    status: Optional[str] = Field(None, alias="Statut") # Terminé, À voir, etc.
    support: Optional[str] = Field(None, alias="Support") # NAS, Netflix, etc.
    rating: Optional[str] = Field(None, alias="Note /10") # Note (Select)
    
    release_date: Optional[date] = Field(None, alias="Date de sortie")
    director: Optional[str] = Field(None, alias="Réalisateur")
    categories: List[str] = Field(default_factory=list, alias="Catégorie")
    synopsis: Optional[str] = Field(None, alias="Synopsis")
    tags: List[str] = Field(default_factory=list, alias="Tags")
    review: Optional[str] = Field(None, alias="Avis")
    tmdb_ok: bool = Field(False, alias="TMDB_OK")
    
    # URL de l'image de couverture
    cover_url: Optional[str] = None
