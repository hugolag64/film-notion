"""Load a series' episodes, seasons and TMDB facts into the local store."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# A returning series gets new air dates: refresh its TMDB facts weekly.
SERIES_METADATA_MAX_AGE = timedelta(days=7)
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def _image(path: Optional[str], size: str) -> Optional[str]:
    return f"{TMDB_IMAGE_BASE}/{size}{path}" if path else None


async def fetch_tmdb_series(
    tmdb, tmdb_id: int, details: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return ``{"episodes", "seasons", "info"}`` for a TMDB series, or None on failure.

    Specials (season 0) are skipped, like everywhere else in Backstage.
    """
    if details is None:
        details = await tmdb.get_tv_details(tmdb_id)
        if not details:
            return None
    episodes: List[Dict[str, Any]] = []
    seasons: List[Dict[str, Any]] = []
    for season in details.get("seasons") or []:
        season_number = season.get("season_number")
        if not isinstance(season_number, int) or season_number <= 0:
            continue
        season_details = await tmdb.get_tv_season_details(tmdb_id, season_number)
        if season_details is None:
            return None
        seasons.append({
            "season_number": season_number,
            "name": season_details.get("name") or season.get("name") or f"Saison {season_number}",
            "overview": (season_details.get("overview") or season.get("overview") or "")[:2000] or None,
            "poster_url": _image(season_details.get("poster_path") or season.get("poster_path"), "w342"),
            "air_date": season_details.get("air_date") or season.get("air_date") or None,
        })
        for episode in season_details.get("episodes") or []:
            episode_number = episode.get("episode_number")
            if not isinstance(episode_number, int):
                continue
            runtime = episode.get("runtime")
            episodes.append({
                "season_number": season_number,
                "episode_number": episode_number,
                "title": episode.get("name") or "Sans titre",
                "synopsis": (episode.get("overview") or "")[:2000],
                "watched": False,
                "air_date": episode.get("air_date") or None,
                "runtime": runtime if isinstance(runtime, int) and runtime > 0 else None,
                "still_url": _image(episode.get("still_path"), "w300"),
            })
    next_episode = details.get("next_episode_to_air") or {}
    vote = details.get("vote_average")
    info = {
        "tmdb_status": details.get("status") or None,
        "first_air_date": details.get("first_air_date") or None,
        "last_air_date": details.get("last_air_date") or None,
        "number_of_seasons": len(seasons) or details.get("number_of_seasons"),
        "vote_average": float(vote) if isinstance(vote, (int, float)) and vote > 0 else None,
        "next_air_date": next_episode.get("air_date") or None,
        "next_season_number": next_episode.get("season_number"),
        "next_episode_number": next_episode.get("episode_number"),
        "next_episode_name": next_episode.get("name") or None,
    }
    return {"episodes": episodes, "seasons": seasons, "info": info}


async def fetch_tmdb_episodes(
    tmdb, tmdb_id: int, details: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Return every non-special TMDB episode, or None when TMDB fails."""
    series = await fetch_tmdb_series(tmdb, tmdb_id, details)
    return series["episodes"] if series else None


async def save_tmdb_series(store, media_id: str, series: Dict[str, Any]) -> None:
    """Store episodes (keeping watch history) plus season and series facts."""
    if series["episodes"]:
        await store.upsert_episodes(media_id, series["episodes"])
    await store.save_series_metadata(media_id, series["seasons"], series["info"])


async def _load(store, tmdb, media) -> bool:
    try:
        series = await fetch_tmdb_series(tmdb, media.tmdb_id)
    except Exception:
        logger.exception("[series-episodes] TMDB import failed for %s", media.id)
        return False
    if not series:
        return False
    await save_tmdb_series(store, media.id, series)
    return True


def _is_linked_series(tmdb, media) -> bool:
    return tmdb is not None and bool(media) and media.type == "Série" and bool(media.tmdb_id)


async def ensure_series_episodes(store, tmdb, media) -> bool:
    """Fill the episode list of a TMDB-linked series that has none yet.

    Series created by the Sonarr/Jellyfin sync arrive without episodes, which
    made their fiche show an empty list. Returns True when TMDB was loaded.
    """
    if not _is_linked_series(tmdb, media):
        return False
    if await store.list_episodes(media.id):
        return False
    return await _load(store, tmdb, media)


async def ensure_series_metadata(store, tmdb, media) -> bool:
    """Load episodes and TMDB facts when missing or older than a week."""
    if not _is_linked_series(tmdb, media):
        return False
    metadata = await store.get_series_metadata(media.id)
    info = metadata.get("info")
    if info and await store.list_episodes(media.id):
        updated_at = datetime.fromisoformat(info["updated_at"])
        if datetime.now(timezone.utc) - updated_at < SERIES_METADATA_MAX_AGE:
            return False
    return await _load(store, tmdb, media)


def _is_aired(episode: Dict[str, Any], today: str) -> bool:
    air_date = episode.get("air_date")
    return not air_date or air_date <= today


def build_series_view(
    episodes: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    playback: Dict[tuple, Dict[str, Any]],
    *,
    has_server: bool,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute what the series fiche shows: per-season summary, stats, next episode.

    ``episodes`` are ordered and already carry ``watched`` and ``available``.
    """
    today = today or datetime.now(timezone.utc).date().isoformat()
    enriched: List[Dict[str, Any]] = []
    for episode in episodes:
        progress = playback.get((episode["season_number"], episode["episode_number"])) or {}
        percent = float(progress.get("percent") or 0)
        enriched.append({
            **episode,
            "upcoming": not _is_aired(episode, today),
            "percent": 0 if progress.get("played") or percent >= 95 else round(percent, 1),
        })

    aired = [episode for episode in enriched if not episode["upcoming"]]
    season_meta = {season["season_number"]: season for season in metadata.get("seasons") or []}
    seasons: Dict[int, Dict[str, Any]] = {}
    for episode in enriched:
        number = episode["season_number"]
        meta = season_meta.get(number, {})
        season = seasons.setdefault(number, {
            "season_number": number,
            "name": meta.get("name") or f"Saison {number}",
            "overview": meta.get("overview"),
            "poster_url": meta.get("poster_url"),
            "air_date": meta.get("air_date"),
            "total": 0, "aired": 0, "watched": 0, "available": 0,
        })
        season["total"] += 1
        if not episode["upcoming"]:
            season["aired"] += 1
        if episode["watched"]:
            season["watched"] += 1
        if episode.get("available"):
            season["available"] += 1
    for season in seasons.values():
        if not has_server or season["aired"] == 0:
            season["availability"] = None
        elif season["available"] >= season["aired"]:
            season["availability"] = "complete"
        elif season["available"]:
            season["availability"] = "partial"
        else:
            season["availability"] = "missing"

    runtimes = [episode["runtime"] for episode in aired if not episode["watched"] and episode.get("runtime")]
    stats = {
        "total": len(enriched),
        "aired": len(aired),
        "upcoming": len(enriched) - len(aired),
        "watched": sum(1 for episode in enriched if episode["watched"]),
        "available": sum(1 for episode in enriched if episode.get("available")) if has_server else None,
        "remaining_minutes": sum(runtimes) if runtimes else None,
    }

    return {
        "episodes": enriched,
        "seasons": [seasons[number] for number in sorted(seasons)],
        "stats": stats,
        "info": metadata.get("info"),
        "next_episode": _next_episode(aired, playback),
    }


def _next_episode(aired: List[Dict[str, Any]], playback: Dict[tuple, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Netflix-like pick: resume a started episode, else the one after the last watched."""
    def summary(episode, mode):
        return {
            "id": episode["id"], "season_number": episode["season_number"],
            "episode_number": episode["episode_number"], "title": episode["title"],
            "percent": episode["percent"], "available": bool(episode.get("available")), "mode": mode,
        }

    started = [
        episode for episode in aired
        if not episode["watched"] and 0 < episode["percent"] < 95
    ]
    if started:
        def last_played(episode):
            row = playback.get((episode["season_number"], episode["episode_number"])) or {}
            return row.get("last_played_at") or ""
        return summary(max(started, key=last_played), "resume")
    if not aired:
        return None
    watched_positions = [index for index, episode in enumerate(aired) if episode["watched"]]
    if not watched_positions:
        return summary(aired[0], "start")
    after = next((episode for episode in aired[watched_positions[-1] + 1:] if not episode["watched"]), None)
    if after:
        return summary(after, "next")
    before = next((episode for episode in aired if not episode["watched"]), None)
    return summary(before, "next") if before else None
