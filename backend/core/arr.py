"""Small server-side clients for Radarr and Sonarr v3 APIs."""
import asyncio
from typing import Any, Optional

import httpx

from backend.core import http


class MediaServerError(RuntimeError):
    """A remote-service error safe to return to Backstage users."""


class ArrClient:
    def __init__(self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        request_kwargs = {"headers": {"X-Api-Key": self.api_key}, **kwargs}
        try:
            if self.client is not None:
                response = await self.client.request(method, f"{self.base_url}{path}", timeout=10.0, **request_kwargs)
            else:
                response = await http.get_client().request(method, f"{self.base_url}{path}", timeout=10.0, **request_kwargs)
            response.raise_for_status()
            if response.status_code == 204 or not response.content.strip():
                return {}  # Radarr répond parfois 200 sans corps (ex. suppression).
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise MediaServerError("Service média inaccessible ou réponse invalide") from error

    async def list_options(self) -> dict[str, list[dict[str, Any]]]:
        quality, root = await self._request("GET", "/api/v3/qualityprofile"), await self._request("GET", "/api/v3/rootfolder")
        return {"quality_profiles": quality, "root_folders": root}

    async def list_library(self) -> list[dict[str, Any]]:
        return await self._request("GET", self.library_path)

    async def list_queue(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v3/queue")
        return data.get("records", []) if isinstance(data, dict) else []

    async def disk_space(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v3/diskspace")
        return data if isinstance(data, list) else []


class RadarrClient(ArrClient):
    library_path = "/api/v3/movie"

    async def add_movie(self, tmdb_id: int, quality_profile_id: int, root_folder: str) -> dict[str, Any]:
        return await self._request("POST", self.library_path, json={
            "tmdbId": tmdb_id, "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder, "monitored": True,
            "addOptions": {"searchForMovie": True},
        })

    async def delete_movie(self, movie_id: int, *, delete_files: bool = True) -> dict[str, Any]:
        """Remove a movie from Radarr and optionally delete its imported files."""
        return await self._request(
            "DELETE", f"{self.library_path}/{movie_id}",
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportExclusion": "false",
            },
        )


class SonarrClient(ArrClient):
    library_path = "/api/v3/series"

    # Sonarr fills a freshly added series' episodes asynchronously.
    episode_poll_attempts = 6
    episode_poll_delay = 2.0

    async def list_options(self) -> dict[str, list[dict[str, Any]]]:
        options = await super().list_options()
        try:
            options["language_profiles"] = await self._request("GET", "/api/v3/languageprofile")
        except MediaServerError:
            options["language_profiles"] = []  # Sonarr v4 dropped language profiles
        return options

    async def find_series(self, tmdb_id: int) -> Optional[dict[str, Any]]:
        """Return the Sonarr series for a TMDB id (v3 only knows TVDB ids)."""
        library = await self.list_library()
        match = next((item for item in library if item.get("tmdbId") == tmdb_id), None)
        if match:
            return match
        lookup = await self._request("GET", "/api/v3/series/lookup", params={"term": f"tmdb:{tmdb_id}"})
        tvdb_id = lookup[0].get("tvdbId") if lookup else None
        if not tvdb_id:
            return None
        return next((item for item in library if item.get("tvdbId") == tvdb_id), None)

    async def ensure_series(
        self, tmdb_id: int, quality_profile_id: int, language_profile_id: Optional[int], root_folder: str,
    ) -> dict[str, Any]:
        """Add the series to Sonarr without searching anything, or return it if present."""
        existing = await self.find_series(tmdb_id)
        if existing:
            return existing
        lookup = await self._request("GET", "/api/v3/series/lookup", params={"term": f"tmdb:{tmdb_id}"})
        if not lookup:
            raise MediaServerError("Série introuvable dans Sonarr")
        series = lookup[0]
        series.update({
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder,
            "monitored": True,
            "seasonFolder": True,
            "monitorNewItems": "none",
            "addOptions": {"monitor": "none", "searchForMissingEpisodes": False},
            "seasons": [{**season, "monitored": False} for season in series.get("seasons") or []],
        })
        if language_profile_id is not None:
            series["languageProfileId"] = language_profile_id
        return await self._request("POST", self.library_path, json=series)

    async def list_episodes(self, series_id: int) -> list[dict[str, Any]]:
        for attempt in range(self.episode_poll_attempts):
            episodes = await self._request("GET", "/api/v3/episode", params={"seriesId": series_id})
            if episodes or attempt == self.episode_poll_attempts - 1:
                return episodes if isinstance(episodes, list) else []
            await asyncio.sleep(self.episode_poll_delay)
        return []

    async def _monitor(self, episode_ids: list[int]) -> None:
        await self._request("PUT", "/api/v3/episode/monitor", json={"episodeIds": episode_ids, "monitored": True})

    async def search_season(self, series: dict[str, Any], season_number: int) -> dict[str, Any]:
        """Monitor a whole season and search it: Sonarr then prefers season packs."""
        episodes = [
            episode for episode in await self.list_episodes(series["id"])
            if episode.get("seasonNumber") == season_number
        ]
        if not episodes:
            raise MediaServerError(f"Saison {season_number} introuvable dans Sonarr")
        await self._monitor([episode["id"] for episode in episodes])
        return await self._request("POST", "/api/v3/command", json={
            "name": "SeasonSearch", "seriesId": series["id"], "seasonNumber": season_number,
        })

    async def search_episodes(self, series: dict[str, Any], refs: list[tuple[int, int]]) -> dict[str, Any]:
        wanted = set(refs)
        episodes = [
            episode for episode in await self.list_episodes(series["id"])
            if (episode.get("seasonNumber"), episode.get("episodeNumber")) in wanted
        ]
        if not episodes:
            raise MediaServerError("Épisode introuvable dans Sonarr")
        ids = [episode["id"] for episode in episodes]
        await self._monitor(ids)
        return await self._request("POST", "/api/v3/command", json={"name": "EpisodeSearch", "episodeIds": ids})

    async def add_series(
        self, tmdb_id: int, quality_profile_id: int, language_profile_id: int,
        root_folder: str, monitor: str,
    ) -> dict[str, Any]:
        if monitor not in {"all", "future"}:
            raise ValueError("monitor doit être 'all' ou 'future'")
        lookup = await self._request("GET", "/api/v3/series/lookup", params={"term": f"tmdb:{tmdb_id}"})
        if not lookup:
            raise MediaServerError("Série introuvable dans Sonarr")
        series = lookup[0]
        series.update({
            "qualityProfileId": quality_profile_id,
            "languageProfileId": language_profile_id,
            "rootFolderPath": root_folder,
            "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True},
            "seasonFolder": True,
            "monitorNewItems": monitor,
        })
        return await self._request("POST", self.library_path, json=series)
