import asyncio

import httpx

from backend.core.jellyfin import JellyfinClient


def test_playback_url_points_to_jellyfin_item():
    client = JellyfinClient("https://jellyfin.example.test", "secret", server_id="server-1")
    assert client.playback_url("abc") == "https://jellyfin.example.test/web/index.html#/details?id=abc&serverId=server-1"


def test_playback_manifest_url_requests_browser_compatible_hls_without_api_key():
    client = JellyfinClient("https://jellyfin.example.test", "secret")
    url = client.playback_manifest_url("abc")

    assert url.startswith("https://jellyfin.example.test/Videos/abc/master.m3u8?")
    assert "VideoCodec=h264" in url
    assert "AudioCodec=aac" in url
    assert "TranscodingProtocol=hls" in url
    assert "secret" not in url


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


def test_find_by_tmdb_requests_provider_ids_from_jellyfin():
    async def handler(request):
        assert request.url.params.get("Fields") == "ProviderIds"
        return httpx.Response(200, json={"Items": [
            {"Id": "interstellar", "Type": "Movie", "ProviderIds": {"Tmdb": "157336"}},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            match = await client.find_by_tmdb(157336, "Film")
        assert match["Id"] == "interstellar"

    asyncio.run(run())


def test_list_users_returns_only_safe_fields_and_uses_api_key():
    async def handler(request):
        assert request.url.path == "/Users"
        assert request.headers["X-Emby-Token"] == "secret"
        return httpx.Response(200, json={
            "Users": [
                {
                    "Id": "jf-hugo",
                    "Name": "Hugo",
                    "Policy": {"IsAdministrator": True, "Password": "hidden"},
                    "HashedPassword": "hidden",
                },
                {
                    "Id": "jf-ophelie",
                    "Name": "Ophélie",
                    "Policy": {"IsAdministrator": False},
                },
            ]
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            users = await client.list_users()
        assert users == [
            {"id": "jf-hugo", "name": "Hugo", "is_admin": True},
            {"id": "jf-ophelie", "name": "Ophélie", "is_admin": False},
        ]

    asyncio.run(run())


def test_list_users_rejects_invalid_payload():
    async def handler(request):
        return httpx.Response(200, json={"Users": [{"Name": "Missing id"}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            try:
                await client.list_users()
            except ValueError as error:
                assert str(error) == "invalid Jellyfin users response"
            else:
                raise AssertionError("invalid payload should raise ValueError")

    asyncio.run(run())


def test_list_users_accepts_jellyfin_array_response():
    async def handler(request):
        return httpx.Response(200, json=[
            {"Id": "jf-ophelie", "Name": "Ophélie", "Policy": {"IsAdministrator": False}},
        ])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            assert await client.list_users() == [
                {"id": "jf-ophelie", "name": "Ophélie", "is_admin": False},
            ]

    asyncio.run(run())


def test_list_users_propagates_http_errors():
    async def handler(request):
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            try:
                await client.list_users()
            except httpx.HTTPStatusError as error:
                assert error.response.status_code == 503
            else:
                raise AssertionError("HTTP errors should propagate")

    asyncio.run(run())


def test_user_playback_reads_resumable_and_latest_items_for_the_selected_user():
    async def handler(request):
        assert request.url.path.startswith("/Users/jf-ophelie/Items")
        assert request.headers["X-Emby-Token"] == "secret"
        if request.url.path.endswith("/Latest"):
            return httpx.Response(200, json=[{
                "Id": "jf-dune", "Name": "Dune", "Type": "Movie",
                "RunTimeTicks": 100, "UserData": {"Played": False, "PlaybackPositionTicks": 50},
                "ProviderIds": {"Tmdb": "438631"},
            }])
        return httpx.Response(200, json={"Items": [{
            "Id": "jf-dune", "Name": "Dune", "Type": "Movie",
            "RunTimeTicks": 100, "UserData": {"Played": False, "PlaybackPositionTicks": 50},
            "ProviderIds": {"Tmdb": "438631"},
        }]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = JellyfinClient("http://127.0.0.1:8096", "secret", http_client)
            items = await client.user_playback("jf-ophelie")
        assert items == [{
            "jellyfin_id": "jf-dune", "tmdb_id": 438631, "title": "Dune",
            "item_type": "Movie", "series_title": None, "series_jellyfin_id": None,
            "season_number": None, "episode_number": None,
            "position_ticks": 50, "runtime_ticks": 100, "percent": 50.0,
            "played": False, "last_played_at": None,
        }]

    asyncio.run(run())
