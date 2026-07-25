"""Small server-side clients for Radarr and Sonarr v3 APIs."""
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


class RadarrClient(ArrClient):
    library_path = "/api/v3/movie"

    async def add_movie(self, tmdb_id: int, quality_profile_id: int, root_folder: str) -> dict[str, Any]:
        return await self._request("POST", self.library_path, json={
            "tmdbId": tmdb_id, "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder, "monitored": True,
            "addOptions": {"searchForMovie": True},
        })


class SonarrClient(ArrClient):
    library_path = "/api/v3/series"

    async def list_options(self) -> dict[str, list[dict[str, Any]]]:
        options = await super().list_options()
        options["language_profiles"] = await self._request("GET", "/api/v3/languageprofile")
        return options

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
