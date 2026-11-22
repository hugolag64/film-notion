"""Load a series' episode list from TMDB into the local store."""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def fetch_tmdb_episodes(
    tmdb, tmdb_id: int, details: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Return every non-special TMDB episode, or None when TMDB fails."""
    if details is None:
        details = await tmdb.get_tv_details(tmdb_id)
        if not details:
            return None
    episodes: List[Dict[str, Any]] = []
    for season in details.get("seasons") or []:
        season_number = season.get("season_number")
        if not isinstance(season_number, int) or season_number <= 0:
            continue
        season_details = await tmdb.get_tv_season_details(tmdb_id, season_number)
        if season_details is None:
            return None
        for episode in season_details.get("episodes") or []:
            episode_number = episode.get("episode_number")
            if not isinstance(episode_number, int):
                continue
            episodes.append({
                "season_number": season_number,
                "episode_number": episode_number,
                "title": episode.get("name") or "Sans titre",
                "synopsis": (episode.get("overview") or "")[:2000],
                "watched": False,
            })
    return episodes


async def ensure_series_episodes(store, tmdb, media) -> bool:
    """Fill the episode list of a TMDB-linked series that has none yet.

    Series created by the Sonarr/Jellyfin sync arrive without episodes, which
    made their fiche show an empty list. Returns True when episodes were added.
    """
    if tmdb is None or not media or media.type != "Série" or not media.tmdb_id:
        return False
    if await store.list_episodes(media.id):
        return False
    try:
        episodes = await fetch_tmdb_episodes(tmdb, media.tmdb_id)
    except Exception:
        logger.exception("[series-episodes] TMDB episode import failed for %s", media.id)
        return False
    if not episodes:
        return False
    await store.upsert_episodes(media.id, episodes)
    return True
