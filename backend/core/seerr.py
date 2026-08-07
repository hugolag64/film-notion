"""Small client for the Seerr media-request API."""
from typing import Any, Optional

import httpx

from backend.core import http
from backend.core.arr import MediaServerError


class SeerrClient:
    def __init__(self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = {"X-Api-Key": self.api_key, **kwargs.pop("headers", {})}
        try:
            if self.client is not None:
                response = await self.client.request(method, f"{self.base_url}{path}", headers=headers, timeout=10.0, **kwargs)
            else:
                response = await http.get_client().request(method, f"{self.base_url}{path}", headers=headers, timeout=10.0, **kwargs)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except httpx.HTTPStatusError as error:
            response = error.response
            try:
                body = response.json()
                reason = body.get("message") if isinstance(body, dict) else str(body)
            except ValueError:
                reason = response.text
            reason = (reason or response.reason_phrase or "réponse invalide").strip()[:300]
            raise MediaServerError(f"Seerr HTTP {response.status_code}: {reason}") from error
        except (httpx.HTTPError, ValueError) as error:
            raise MediaServerError("Seerr inaccessible ou réponse invalide") from error

    async def request_media(
        self, *, tmdb_id: int, media_type: str, quality_profile_id: Optional[int],
        root_folder: Optional[str], language_profile_id: Optional[int], monitor: str,
    ) -> dict[str, Any]:
        if media_type not in {"Film", "Série"}:
            raise ValueError("Type de média non pris en charge")
        if monitor not in {"all", "future"}:
            raise ValueError("monitor doit être 'all' ou 'future'")
        payload: dict[str, Any] = {
            "mediaType": "movie" if media_type == "Film" else "tv",
            "mediaId": tmdb_id,
            "is4k": False,
            "ignoreQuota": False,
        }
        if quality_profile_id is not None:
            payload["profileId"] = quality_profile_id
        if root_folder:
            payload["rootFolder"] = root_folder
        if media_type == "Série":
            payload["seasons"] = "all" if monitor == "all" else []
            if language_profile_id is not None:
                payload["languageProfileId"] = language_profile_id
        return await self._request("POST", "/api/v1/request", json=payload)

    async def list_requests(
        self, *, take: int = 8, skip: int = 0, request_filter: str = "all",
        sort: str = "modified", sort_direction: str = "desc",
    ) -> list[dict[str, Any]]:
        """Return recent Seerr requests across supported response shapes."""
        payload = await self._request(
            "GET", "/api/v1/request",
            params={
                "take": take, "skip": skip, "filter": request_filter,
                "sort": sort, "sortDirection": sort_direction,
            },
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "requests"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    async def cancel_request(self, request_id: int | str) -> dict[str, Any]:
        """Cancel a Seerr request; Seerr returns an empty 204 on success."""
        result = await self._request("DELETE", f"/api/v1/request/{request_id}")
        return result if isinstance(result, dict) else {}
