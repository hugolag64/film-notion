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

    async def find_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[dict[str, Any]]:
        item_type = "Series" if media_type == "Série" else "Movie"
        kwargs = {"headers": {"X-Emby-Token": self.api_key}, "params": {
            "IncludeItemTypes": item_type,
            "Recursive": "true",
            "Fields": "ProviderIds",
        }}
        client = self.client or http.get_client()
        try:
            response = await client.get(f"{self.base_url}/Items", timeout=10.0, **kwargs)
            response.raise_for_status()
            for item in response.json().get("Items", []):
                if item.get("Type") == item_type and str(item.get("ProviderIds", {}).get("Tmdb")) == str(tmdb_id):
                    return item
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
