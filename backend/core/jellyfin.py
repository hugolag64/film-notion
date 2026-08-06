"""Server-side Jellyfin lookup; no API key reaches the browser."""
from typing import Any, Optional
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

import httpx

from backend.core import http


class JellyfinClient:
    def __init__(
        self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None,
        *, server_id: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client
        self.server_id = server_id

    async def list_users(self) -> list[dict[str, Any]]:
        client = self.client or http.get_client()
        response = await client.get(
            f"{self.base_url}/Users",
            headers={"X-Emby-Token": self.api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            raise ValueError("invalid Jellyfin users response") from error
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("Users"), list):
            items = payload["Users"]
        else:
            raise ValueError("invalid Jellyfin users response")

        users = []
        for item in items:
            if not isinstance(item, dict) or not item.get("Id"):
                raise ValueError("invalid Jellyfin users response")
            policy = item.get("Policy") or {}
            if not isinstance(policy, dict):
                raise ValueError("invalid Jellyfin users response")
            users.append({
                "id": str(item["Id"]),
                "name": str(item.get("Name") or item["Id"]),
                "is_admin": bool(policy.get("IsAdministrator", False)),
            })
        return users

    @staticmethod
    def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("Items"), list):
            items = payload["Items"]
        else:
            raise ValueError("invalid Jellyfin playback response")
        return [item for item in items if isinstance(item, dict) and item.get("Id")]

    async def user_playback(self, user_id: str) -> list[dict[str, Any]]:
        client = self.client or http.get_client()
        fields = "ProviderIds,UserData,SeriesName,SeriesId,IndexNumber,ParentIndexNumber"
        requests = (
            (f"{self.base_url}/Users/{quote(user_id, safe='')}/Items", {
                "Recursive": "true", "IsResumable": "true", "Fields": fields,
            }),
            (f"{self.base_url}/Users/{quote(user_id, safe='')}/Items/Latest", {
                "Fields": fields, "Limit": "50",
            }),
        )
        normalized: dict[str, dict[str, Any]] = {}
        for url, params in requests:
            response = await client.get(
                url,
                headers={"X-Emby-Token": self.api_key},
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            items = self._items_from_payload(response.json())
            for item in items:
                user_data = item.get("UserData") or {}
                runtime = int(item.get("RunTimeTicks") or 0)
                position = int(user_data.get("PlaybackPositionTicks") or 0)
                percent = round(position * 100 / runtime, 2) if runtime else 0
                provider_ids = item.get("ProviderIds") or {}
                normalized[str(item["Id"])] = {
                    "jellyfin_id": str(item["Id"]),
                    "tmdb_id": int(provider_ids["Tmdb"]) if str(provider_ids.get("Tmdb", "")).isdigit() else None,
                    "title": str(item.get("Name") or item["Id"]),
                    "item_type": item.get("Type"),
                    "series_title": item.get("SeriesName"),
                    "series_jellyfin_id": item.get("SeriesId"),
                    "season_number": item.get("ParentIndexNumber"),
                    "episode_number": item.get("IndexNumber"),
                    "position_ticks": position,
                    "runtime_ticks": runtime,
                    "percent": percent,
                    "played": bool(user_data.get("Played")),
                    "last_played_at": user_data.get("LastPlayedDate"),
                }
        return list(normalized.values())

    async def find_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[dict[str, Any]]:
        item_type = "Series" if media_type == "Série" else "Movie"
        client = self.client or http.get_client()
        limit = 1000
        start_index = 0
        try:
            while True:
                response = await client.get(
                    f"{self.base_url}/Items",
                    headers={"X-Emby-Token": self.api_key},
                    params={
                        "IncludeItemTypes": item_type,
                        "Recursive": "true",
                        "Fields": "ProviderIds",
                        "Limit": limit,
                        "StartIndex": start_index,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                items = response.json().get("Items", [])
                for item in items:
                    if item.get("Type") == item_type and str(item.get("ProviderIds", {}).get("Tmdb")) == str(tmdb_id):
                        return item
                if len(items) < limit:
                    break
                start_index += len(items)
        except (httpx.HTTPError, ValueError):
            return None
        return None

    def playback_url(self, item_id: str) -> str:
        # Jellyfin's web client only initializes its player from the item details
        # page; opening the /video route directly has no active player and falls
        # back to the home page.
        url = f"{self.base_url}/web/index.html#/details?id={quote(item_id, safe='')}"
        if self.server_id:
            url += f"&serverId={quote(self.server_id, safe='')}"
        return url

    def playback_manifest_url(self, item_id: str) -> str:
        params = urlencode({
            "VideoCodec": "h264",
            "AudioCodec": "aac",
            "Container": "ts",
            "TranscodingContainer": "ts",
            "TranscodingProtocol": "hls",
            "MaxWidth": "1920",
            "MaxHeight": "1080",
        })
        return f"{self.base_url}/Videos/{quote(item_id, safe='')}/master.m3u8?{params}&MediaSourceId={quote(item_id, safe='')}"

    async def fetch_playback_resource(
        self, item_id: str, resource_path: str, query: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        normalized = PurePosixPath(resource_path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("Chemin de lecture invalide")
        url = f"{self.base_url}/Videos/{quote(item_id, safe='')}/{quote(str(normalized), safe='/')}"
        client = self.client or http.get_client()
        response = await client.get(
            url, headers={"X-Emby-Token": self.api_key}, params=query or {}, timeout=60.0,
        )
        response.raise_for_status()
        return response
