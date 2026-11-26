"""Films candidats d'une soirée et choix des 3 propositions."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

import httpx

from backend.core.cinema_store import CinemaStore
from backend.core.gemini_recommendations import GeminiGroupPick
from backend.core.guided_recommendations import MOOD_GENRES
from backend.core.recommendations import GENRE_IDS, TasteProfile, score_recommendation_candidate
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient

logger = logging.getLogger(__name__)

TOP_N = 15
RECENT_ERA_YEARS = 6
CLASSIC_ERA_END = "2005-12-31"
_TMDB_ERRORS = (ValueError, httpx.HTTPError)
DETAILS_TIMEOUT_SEC = 8.0


async def _details(tmdb, tmdb_id: int, title: str) -> dict:
    """Détails TMDB d'un film, bornés dans le temps : un TMDB lent ne bloque pas la soirée."""
    try:
        return await asyncio.wait_for(tmdb.get_movie_details(tmdb_id), DETAILS_TIMEOUT_SEC) or {}
    except (asyncio.TimeoutError, *_TMDB_ERRORS) as error:
        logger.warning("[soirée] Détails TMDB indisponibles pour %s : %r", title, error)
        return {}


def _score(candidate: dict, profile: TasteProfile, combined: dict, now: datetime) -> float:
    preferences = {"mood": combined["mood"]} if combined.get("mood") not in (None, "any") else {}
    return score_recommendation_candidate(candidate, profile, preferences, None, now).score


async def cinema_candidates(
    cinema: CinemaStore, tmdb, profile: TasteProfile, combined: dict, now: datetime,
) -> list[dict]:
    """Films du Grand Sud qui ont encore une séance ce soir (now est l'heure de La Réunion)."""
    midnight = datetime.combine(now.date() + timedelta(days=1), time())
    films = await cinema.get_site_films()
    next_show: dict[int, dict] = {}
    for show in await cinema.list_showtimes(now, midnight):
        if show["site_id"] in films:
            next_show.setdefault(show["site_id"], show)
    with_tmdb = [films[site_id] for site_id in next_show if films[site_id]["tmdb_id"]]
    fetched = await asyncio.gather(*(_details(tmdb, film["tmdb_id"], film["title"]) for film in with_tmdb))
    details_by_site = {film["site_id"]: details for film, details in zip(with_tmdb, fetched)}
    found = []
    for site_id, show in next_show.items():
        film = films[site_id]
        candidate: dict[str, Any] = {
            "tmdb_id": film["tmdb_id"], "title": film["title"], "poster_url": film["poster_url"],
            "source": "cinema", "site_id": site_id, "genre_ids": [], "overview": "", "score": 0.0,
            "showtime": {"time": f"{show['starts_at']:%H:%M}", "version": show["version"], "booking_url": show["booking_url"]},
        }
        if film["tmdb_id"]:
            details = details_by_site.get(site_id, {})
            runtime = details.get("runtime")
            if runtime and combined.get("runtime_max") and runtime > combined["runtime_max"]:
                continue
            candidate["genre_ids"] = [genre["id"] for genre in details.get("genres") or [] if "id" in genre]
            candidate["overview"] = details.get("overview") or ""
            candidate["score"] = _score(candidate, profile, combined, now)
        found.append(candidate)
    found.sort(key=lambda c: -c["score"])
    return found


def _discover_params(combined: dict, today: date) -> dict:
    params: dict[str, Any] = {"page": 1, "min_vote_count": 50, "release_date_lte": today.isoformat()}
    mood = combined.get("mood")
    if mood in MOOD_GENRES:
        params["with_genres"] = [GENRE_IDS[name] for name in MOOD_GENRES[mood] if name in GENRE_IDS]
    if combined.get("runtime_max"):
        params["runtime_max"] = combined["runtime_max"]
    if combined.get("era") == "recent":
        params["release_date_gte"] = f"{today.year - RECENT_ERA_YEARS}-01-01"
    elif combined.get("era") == "classic":
        params["release_date_lte"] = CLASSIC_ERA_END
    return params


async def coloc_candidates(
    store: MediaStore, tmdb, profile: TasteProfile, combined: dict, seen_tmdb_ids: set[int], now: datetime,
) -> list[dict]:
    """Films TMDB et films de la bibliothèque, sans ceux qu'un partant a déjà vus."""
    by_id: dict[int, dict] = {}
    try:
        for item in await tmdb.discover_movies(**_discover_params(combined, now.date())):
            by_id[int(item["tmdb_id"])] = {
                "tmdb_id": int(item["tmdb_id"]), "title": item.get("title") or "Sans titre",
                "poster_url": TMDBClient.poster_url_from_path(item.get("poster_path")),
                "source": "tmdb", "site_id": None, "showtime": None,
                "genre_ids": item.get("genre_ids") or [], "overview": item.get("overview") or "",
                "release_date": item.get("release_date"), "vote_average": item.get("vote_average") or 0,
            }
    except _TMDB_ERRORS as error:
        logger.warning("[soirée] Découverte TMDB indisponible : %s", error)
    for media in await store.fetch_all():
        if media.type != "Film" or not media.tmdb_id:
            continue
        by_id[media.tmdb_id] = {
            "tmdb_id": media.tmdb_id, "title": media.title, "poster_url": media.cover_url,
            "source": "server", "site_id": None, "showtime": None,
            "genre_ids": [GENRE_IDS[name] for name in media.categories if name in GENRE_IDS],
            "overview": media.synopsis or "",
            "release_date": media.release_date.isoformat() if media.release_date else None,
        }
    found = [c for tmdb_id, c in by_id.items() if tmdb_id not in seen_tmdb_ids]
    for candidate in found:
        candidate["score"] = _score(candidate, profile, combined, now)
    found.sort(key=lambda c: -c["score"])
    if combined.get("runtime_max"):
        found = await _within_runtime(found, tmdb, combined["runtime_max"])
    return found


async def _within_runtime(candidates: list[dict], tmdb, runtime_max: int) -> list[dict]:
    """La bibliothèque ne connaît pas la durée : on la demande à TMDB, seulement pour
    les films du serveur assez bien classés pour être proposés."""
    checked = [c for c in candidates[: TOP_N * 2] if c["source"] == "server"]
    fetched = await asyncio.gather(*(_details(tmdb, c["tmdb_id"], c["title"]) for c in checked))
    too_long = {
        c["tmdb_id"] for c, details in zip(checked, fetched)
        if details.get("runtime") and details["runtime"] > runtime_max
    }
    return [c for c in candidates if c["tmdb_id"] not in too_long]


def pick_three(candidates: list[dict], pick: Optional[GeminiGroupPick]) -> list[dict]:
    top = candidates[:TOP_N]
    by_id = {c["tmdb_id"]: c for c in top if c.get("tmdb_id")}
    chosen: list[dict] = []
    if pick and len(pick.picks) == 3 and all(p["tmdb_id"] in by_id for p in pick.picks):
        chosen = [{**by_id[p["tmdb_id"]], "reason": p.get("reason") or ""} for p in pick.picks]
    else:
        chosen = [{**c, "reason": ""} for c in top[:3]]
    if len(chosen) == 3 and not any(c["source"] == "server" for c in chosen):
        server = next((c for c in top if c["source"] == "server"), None)
        if server is not None:
            chosen[2] = {**server, "reason": ""}
    return [{**c, "rank": rank} for rank, c in enumerate(chosen, start=1)]
