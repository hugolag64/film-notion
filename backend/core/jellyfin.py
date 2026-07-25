"""Server-side Jellyfin lookup; no API key reaches the browser."""
from typing import Any, Optional
from urllib.parse import quote

import httpx

from backend.core import http


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client

    async def find_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[dict[str, Any]]:
        item_type = "Series" if media_type == "Série" else "Movie"
        kwargs = {"headers": {"X-Emby-Token": self.api_key}, "params": {"IncludeItemTypes": item_type, "Recursive": "true"}}
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
        return f"{self.base_url}/web/index.html#!/details?id={quote(item_id, safe='')}"
