"""Shared, conservative helpers for linking a local media item to TMDB."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from backend.core.models import Media


def normalize_title(value: str) -> str:
    """Compare titles without case, accents, punctuation or spacing differences."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_accents.casefold())


def result_year(candidate: Dict[str, Any]) -> Optional[int]:
    value = candidate.get("release_date") or candidate.get("first_air_date") or ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").year
    except (TypeError, ValueError):
        return None


def select_confident_match(media: Media, candidates: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a match only when the title, and when known the year, are unambiguous."""
    exact_titles = [
        candidate for candidate in candidates
        if normalize_title(candidate.get("title") or candidate.get("name") or "") == normalize_title(media.title)
    ]
    if not exact_titles:
        return None

    if media.release_date:
        exact_years = [candidate for candidate in exact_titles if result_year(candidate) == media.release_date.year]
        return exact_years[0] if len(exact_years) == 1 else None

    return exact_titles[0] if len(exact_titles) == 1 else None


def build_relink_updates(media: Media, details: Dict[str, Any], tmdb: Any, tmdb_id: int) -> Dict[str, Any]:
    """Build the standard local update from TMDB details, for films and series alike."""
    return {
        "title": details.get("title") or details.get("name") or media.title,
        "original_title": details.get("original_title") or details.get("original_name") or media.original_title,
        "cover_url": tmdb.get_poster_url(details) or media.cover_url,
        "backdrop_url": tmdb.get_backdrop_url(details) or media.backdrop_url,
        "cast": tmdb.get_cast(details, limit=5) or media.cast,
        "director": tmdb.get_director(details) or media.director,
        "synopsis": (details.get("overview") or media.synopsis or "")[:2000],
        "categories": tmdb.get_genres(details) or media.categories,
        "tmdb_ok": True,
        "tmdb_id": tmdb_id,
        "release_date": details.get("release_date") or details.get("first_air_date") or media.release_date,
    }
