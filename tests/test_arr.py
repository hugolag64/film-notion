import asyncio
import json

import httpx

from backend.core.arr import RadarrClient, SonarrClient
from backend.core.seerr import SeerrClient


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_radarr_add_movie_posts_tmdb_profile_and_root():
    captured = {}

    async def handler(request):
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 42, "tmdbId": 438631})

    async def run():
        async with _client(handler) as client:
            result = await RadarrClient("http://127.0.0.1:7878", "secret", client).add_movie(
                438631, 5, "D:/Media/Films"
            )
        assert result["id"] == 42

    asyncio.run(run())
    assert captured["path"] == "/api/v3/movie"
    assert captured["json"] == {
        "tmdbId": 438631, "qualityProfileId": 5, "rootFolderPath": "D:/Media/Films",
        "monitored": True, "addOptions": {"searchForMovie": True},
    }


def test_sonarr_rejects_unknown_monitor_value():
    async def run():
        async with _client(lambda request: httpx.Response(200, json={})) as client:
            try:
                await SonarrClient("http://127.0.0.1:8989", "secret", client).add_series(
                    1, 2, 3, "D:/Media/Series", "invalid"
                )
            except ValueError as error:
                assert "monitor" in str(error)
            else:
                raise AssertionError("Expected monitor validation")

    asyncio.run(run())


def test_seerr_requests_a_movie_with_api_key_and_backstage_options():
    captured = {}

    async def handler(request):
        captured["path"] = request.url.path
        captured["key"] = request.headers["X-Api-Key"]
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 7, "status": 2})

    async def run():
        async with _client(handler) as client:
            result = await SeerrClient("http://seerr:5055", "seerr-secret", client).request_media(
                tmdb_id=438631, media_type="Film", quality_profile_id=5,
                root_folder="/media/movies", language_profile_id=None, monitor="all",
            )
        assert result["id"] == 7

    asyncio.run(run())
    assert captured["path"] == "/api/v1/request"
    assert captured["key"] == "seerr-secret"
    assert captured["json"] == {
        "mediaType": "movie", "mediaId": 438631, "is4k": False,
        "profileId": 5, "rootFolder": "/media/movies", "ignoreQuota": False,
    }
