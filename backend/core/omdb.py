"""
Enrichissement complémentaire via OMDb (optionnel) : note IMDb + classification d'âge.

Activé seulement si OMDB_API_KEY est défini. Renvoie None si indisponible.
"""
import logging
from typing import Optional, Dict, Any

from backend.config import Config
from backend.core import http

logger = logging.getLogger(__name__)

BASE_URL = "https://www.omdbapi.com/"


async def fetch(title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retourne {'imdb_rating', 'rated', 'imdb_id'} ou None."""
    if not Config.omdb_enabled():
        return None

    params = {"apikey": Config.OMDB_API_KEY, "t": title}
    if year:
        params["y"] = year

    try:
        response = await http.request_with_retry("GET", BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("Response") != "True":
            return None
        return {
            "imdb_rating": data.get("imdbRating") if data.get("imdbRating") not in ("N/A", None) else None,
            "rated": data.get("Rated") if data.get("Rated") not in ("N/A", None) else None,
            "imdb_id": data.get("imdbID"),
        }
    except Exception as e:
        logger.error("Erreur OMDb pour '%s': %s", title, e)
        return None
