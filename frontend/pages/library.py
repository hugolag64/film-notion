import re
from typing import List, Optional

from backend.core.models import Media

SORT_OPTIONS = ["Titre", "Année", "Note"]


def _rating_value(media: Media) -> Optional[float]:
    if not media.rating:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)?)", media.rating)
    return float(match.group(1)) if match else None


def filter_and_sort_medias(medias: List[Media], query: str, sort_key: str) -> List[Media]:
    query_norm = (query or "").strip().lower()
    filtered = [m for m in medias if query_norm in m.title.lower()] if query_norm else list(medias)

    if sort_key == "Titre":
        return sorted(filtered, key=lambda m: m.title.lower())

    if sort_key == "Année":
        with_date = sorted((m for m in filtered if m.release_date), key=lambda m: m.release_date, reverse=True)
        without_date = [m for m in filtered if not m.release_date]
        return with_date + without_date

    if sort_key == "Note":
        rated = sorted((m for m in filtered if _rating_value(m) is not None), key=_rating_value, reverse=True)
        unrated = [m for m in filtered if _rating_value(m) is None]
        return rated + unrated

    raise ValueError(f"Tri inconnu : {sort_key}")
