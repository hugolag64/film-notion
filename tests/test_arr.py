import asyncio
import json

import httpx

from backend.core.arr import RadarrClient, SonarrClient
from backend.core.arr import MediaServerError
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


def test_radarr_delete_movie_removes_files_without_import_exclusion():
    captured = {}

    async def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(204)

    async def run():
        async with _client(handler) as client:
            result = await RadarrClient("http://127.0.0.1:7878", "secret", client).delete_movie(42)
        assert result == {}

    asyncio.run(run())
    assert captured == {
        "method": "DELETE",
        "path": "/api/v3/movie/42",
        "query": {"deleteFiles": "true", "addImportExclusion": "false"},
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


def test_seerr_can_request_with_its_own_defaults():
    captured = {}

    async def handler(request):
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 8})

    async def run():
        async with _client(handler) as client:
            await SeerrClient("http://seerr:5055", "secret", client).request_media(
                tmdb_id=27205, media_type="Film", quality_profile_id=None,
                root_folder=None, language_profile_id=None, monitor="all",
            )

    asyncio.run(run())
    assert captured["json"] == {
        "mediaType": "movie", "mediaId": 27205, "is4k": False, "ignoreQuota": False,
    }


def test_seerr_http_error_preserves_remote_reason():
    async def handler(request):
        return httpx.Response(400, json={"message": "No default Radarr server"})

    async def run():
        async with _client(handler) as client:
            try:
                await SeerrClient("http://seerr:5055", "secret", client).request_media(
                    tmdb_id=27205, media_type="Film", quality_profile_id=None,
                    root_folder=None, language_profile_id=None, monitor="all",
                )
            except MediaServerError as error:
                assert "HTTP 400" in str(error)
                assert "No default Radarr server" in str(error)
            else:
                raise AssertionError("Expected Seerr request failure")

    asyncio.run(run())


def test_seerr_lists_recent_requests_with_filters():
    captured = {}

    async def handler(request):
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"results": [{"id": 9, "status": 1}]})

    async def run():
        async with _client(handler) as client:
            result = await SeerrClient("http://seerr:5055", "secret", client).list_requests(
                take=6, skip=2, request_filter="all", sort="modified", sort_direction="desc",
            )
        assert result == [{"id": 9, "status": 1}]

    asyncio.run(run())
    assert captured["path"] == "/api/v1/request"
    assert captured["query"] == {
        "take": "6", "skip": "2", "filter": "all", "sort": "modified", "sortDirection": "desc",
    }


def test_seerr_cancel_request_accepts_empty_delete_response():
    captured = {}

    async def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(204)

    async def run():
        async with _client(handler) as client:
            result = await SeerrClient("http://seerr:5055", "secret", client).cancel_request(14)
        assert result == {}

    asyncio.run(run())
    assert captured == {"method": "DELETE", "path": "/api/v1/request/14"}


def test_seerr_409_is_reported_as_a_duplicate_request():
    from backend.core.seerr import SeerrDuplicateRequest

    async def handler(request):
        return httpx.Response(409, json={"message": "Request for this media already exists."})

    async def run():
        async with _client(handler) as client:
            await SeerrClient("http://seerr:5055", "secret", client).request_media(
                tmdb_id=27205, media_type="Film", quality_profile_id=None,
                root_folder=None, language_profile_id=None, monitor="all",
            )

    try:
        asyncio.run(run())
    except SeerrDuplicateRequest as error:
        assert isinstance(error, MediaServerError)
    else:
        raise AssertionError("Expected a duplicate-request error")


def test_api_is_wired_to_seerr_when_its_key_is_set(monkeypatch):
    from backend import api
    from backend.config import Config

    monkeypatch.setattr(Config, "SEERR_URL", "http://host.docker.internal:5055")
    monkeypatch.setattr(Config, "SEERR_API_KEY", "seerr-secret")
    service = api.get_media_server_service(store=object())
    assert service.seerr.base_url == "http://host.docker.internal:5055"

    monkeypatch.setattr(Config, "SEERR_API_KEY", None)
    assert api.get_media_server_service(store=object()).seerr is None


def _sonarr_handler(calls, library=None, episodes=None):
    library = library if library is not None else []
    episodes = episodes if episodes is not None else []

    async def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, dict(request.url.params), body))
        path = request.url.path
        if path == "/api/v3/series" and request.method == "GET":
            return httpx.Response(200, json=library)
        if path == "/api/v3/series/lookup":
            return httpx.Response(200, json=[{"title": "POI", "tvdbId": 248742, "seasons": [
                {"seasonNumber": 1, "monitored": True}, {"seasonNumber": 2, "monitored": True}]}])
        if path == "/api/v3/series" and request.method == "POST":
            return httpx.Response(201, json={**body, "id": 9})
        if path == "/api/v3/episode":
            return httpx.Response(200, json=episodes)
        return httpx.Response(200, json={"id": 1})
    return handler


def test_sonarr_ensure_series_adds_it_without_monitoring_or_searching():
    calls = []

    async def run():
        async with _client(_sonarr_handler(calls)) as client:
            return await SonarrClient("http://sonarr", "k", client).ensure_series(1411, 4, None, "/tv")

    series = asyncio.run(run())

    post = next(call for call in calls if call[0] == "POST")
    assert series["id"] == 9
    assert post[3]["addOptions"] == {"monitor": "none", "searchForMissingEpisodes": False}
    assert all(season["monitored"] is False for season in post[3]["seasons"])
    assert "languageProfileId" not in post[3]


def test_sonarr_finds_existing_series_by_tvdb_id():
    calls = []
    library = [{"id": 3, "title": "POI", "tvdbId": 248742}]

    async def run():
        async with _client(_sonarr_handler(calls, library=library)) as client:
            return await SonarrClient("http://sonarr", "k", client).ensure_series(1411, 4, None, "/tv")

    assert asyncio.run(run())["id"] == 3
    assert not any(call[0] == "POST" for call in calls)


def test_sonarr_search_season_monitors_its_episodes_then_runs_season_search():
    calls = []
    episodes = [
        {"id": 11, "seasonNumber": 2, "episodeNumber": 1},
        {"id": 12, "seasonNumber": 2, "episodeNumber": 2},
        {"id": 21, "seasonNumber": 3, "episodeNumber": 1},
    ]

    async def run():
        async with _client(_sonarr_handler(calls, episodes=episodes)) as client:
            await SonarrClient("http://sonarr", "k", client).search_season({"id": 9}, 2)

    asyncio.run(run())

    monitor = next(call for call in calls if call[1] == "/api/v3/episode/monitor")
    command = next(call for call in calls if call[1] == "/api/v3/command")
    assert monitor[3] == {"episodeIds": [11, 12], "monitored": True}
    assert command[3] == {"name": "SeasonSearch", "seriesId": 9, "seasonNumber": 2}


def test_sonarr_search_episodes_targets_only_the_chosen_ones():
    calls = []
    episodes = [{"id": 11, "seasonNumber": 2, "episodeNumber": 1}, {"id": 12, "seasonNumber": 2, "episodeNumber": 2}]

    async def run():
        async with _client(_sonarr_handler(calls, episodes=episodes)) as client:
            await SonarrClient("http://sonarr", "k", client).search_episodes({"id": 9}, [(2, 2)])

    asyncio.run(run())

    command = next(call for call in calls if call[1] == "/api/v3/command")
    assert command[3] == {"name": "EpisodeSearch", "episodeIds": [12]}


def test_seerr_series_request_sends_chosen_seasons_or_all():
    captured = []

    async def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(201, json={"id": 1})

    async def run():
        async with _client(handler) as client:
            seerr = SeerrClient("http://seerr", "k", client)
            await seerr.request_media(tmdb_id=1411, media_type="Série", quality_profile_id=None,
                                      root_folder=None, language_profile_id=None, monitor="all", seasons=[3, 1])
            await seerr.request_media(tmdb_id=1411, media_type="Série", quality_profile_id=None,
                                      root_folder=None, language_profile_id=None, monitor="future")

    asyncio.run(run())

    assert captured[0]["seasons"] == [1, 3]
    assert captured[1]["seasons"] == "all"
