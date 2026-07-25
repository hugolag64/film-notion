import asyncio

import httpx

from backend.core.jellyfin import JellyfinClient


def test_playback_url_points_to_jellyfin_item():
    client = JellyfinClient("https://jellyfin.example.test", "secret")
    assert client.playback_url("abc") == "https://jellyfin.example.test/web/index.html#!/details?id=abc"


def test_find_by_tmdb_filters_item_type():
    async def handler(request):
        return httpx.Response(200, json={"Items": [
            {"Id": "wrong", "Type": "Series", "ProviderIds": {"Tmdb": "438631"}},
            {"Id": "right", "Type": "Movie", "ProviderIds": {"Tmdb": "438631"}},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            match = await client.find_by_tmdb(438631, "Film")
        assert match["Id"] == "right"

    asyncio.run(run())
