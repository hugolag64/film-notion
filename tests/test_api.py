import asyncio

import pytest
from fastapi import HTTPException

from backend.api import (
    UpdateMediaRequest,
    UpdatePersonalMediaRequest,
    health_router,
    update_media,
    update_personal_media,
)
from backend.auth_api import AuthContext
from backend.core.models import Media
from backend.core.store import MediaStore


class FakeStore:
    def __init__(self):
        self.media = Media(id="1", title="Dune", status="Terminé", rating="5")
        self.updates = None

    async def fetch_one(self, media_id):
        return self.media if media_id == self.media.id else None

    async def update(self, media_id, fields):
        self.updates = fields
        self.media = self.media.model_copy(update=fields)
        return True


def test_watching_later_clears_rating():
    store = FakeStore()
    result = asyncio.run(update_media("1", UpdateMediaRequest(status="À regarder"), store))

    assert result.status == "À regarder"
    assert result.rating is None
    assert store.updates == {"status": "À regarder", "rating": None}


def test_personal_rating_marks_media_as_watched(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    current = AuthContext(user={"id": "hugo", "role": "user"}, session_id="session", token="token")

    result = asyncio.run(update_personal_media(
        "dune", UpdatePersonalMediaRequest(rating="4", is_watchlist=True), current, store,
    ))

    assert result.rating == "4"
    assert result.status == "Terminé"
    assert result.is_watchlist is False


def test_personal_watchlist_is_returned_without_marking_media_watched(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    current = AuthContext(user={"id": "hugo", "role": "user"}, session_id="session", token="token")

    result = asyncio.run(update_personal_media(
        "dune", UpdatePersonalMediaRequest(is_watchlist=True), current, store,
    ))

    assert result.status is None
    assert result.rating is None
    assert result.is_watchlist is True
from urllib.parse import parse_qs, urlsplit

import backend.api as api


def test_api_module_has_no_simulated_stream_route():
    paths = {route.path for route in api.router.routes}
    assert "/api/medias/{media_id}/stream" not in paths


def test_hls_manifest_rewrites_resources_without_jellyfin_credentials():
    manifest = """#EXTM3U
#EXTINF:3.0,
hls1/main/0.ts?MediaSourceId=item-1&api_key=secret
"""

    rewritten = api._rewrite_hls_manifest(manifest, "media-1")

    assert "/api/medias/media-1/playback/resource/hls1/main/0.ts" in rewritten
    assert "MediaSourceId=item-1" in rewritten
    assert "api_key" not in rewritten
    assert "jellyfin.test" not in rewritten


def test_hls_playback_routes_are_registered():
    paths = {route.path for route in api.router.routes}

    assert "/api/medias/{media_id}/playback/manifest" in paths
    assert "/api/medias/{media_id}/playback/resource/{resource_path:path}" in paths


def test_health_route_is_registered_without_media_dependencies():
    routes = {route.path for route in health_router.routes}

    assert "/health" in routes


def test_tmdb_movie_preview_route_is_registered():
    paths = {route.path for route in api.router.routes}

    assert "/api/tmdb/movies/{tmdb_id}" in paths


def test_seerr_request_cards_are_hydrated_with_tmdb_metadata(monkeypatch):
    class FakeTMDB:
        async def get_details(self, tmdb_id, is_series=False):
            assert tmdb_id == 693134
            assert is_series is False
            return {"title": "Dune", "poster_path": "/dune.jpg"}

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)
    requests = [{"id": 4, "mediaType": "movie", "media": {"tmdbId": 693134}}]

    hydrated = asyncio.run(api._hydrate_seerr_requests(requests))

    assert hydrated[0]["media"]["title"] == "Dune"
    assert hydrated[0]["media"]["posterPath"] == "/dune.jpg"


def test_available_seerr_requests_are_removed_from_the_active_queue():
    class FakeSeerr:
        def __init__(self):
            self.cancelled = []

        async def cancel_request(self, request_id):
            self.cancelled.append(request_id)

    seerr = FakeSeerr()
    requests = [
        {"id": 8, "media": {"status": 5}},
        {"id": 9, "media": {"status": 3}},
    ]

    active = asyncio.run(api._prune_available_seerr_requests(seerr, requests))

    assert [item["id"] for item in active] == [9]
    assert seerr.cancelled == [8]


def test_tmdb_movie_preview_returns_complete_film_metadata(monkeypatch):
    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            assert tmdb_id == 693134
            return {
                "id": tmdb_id,
                "title": "Dune",
                "original_title": "Dune",
                "overview": "Une histoire de sable.",
                "release_date": "2021-09-15",
                "runtime": 155,
                "vote_average": 8.24,
                "vote_count": 12000,
                "poster_path": "/dune.jpg",
                "backdrop_path": "/dune-backdrop.jpg",
                "genres": [{"name": "Science-Fiction"}],
                "credits": {
                    "crew": [{"job": "Director", "name": "Denis Villeneuve"}],
                    "cast": [{"name": "TimothÃ©e Chalamet"}],
                },
            }

        @staticmethod
        def get_poster_url(details):
            return f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

        @staticmethod
        def get_backdrop_url(details):
            return f"https://image.tmdb.org/t/p/w1280{details['backdrop_path']}"

        @staticmethod
        def get_director(details):
            return details["credits"]["crew"][0]["name"]

        @staticmethod
        def get_genres(details):
            return [genre["name"] for genre in details["genres"]]

        @staticmethod
        def get_cast(details, limit=8):
            return [actor["name"] for actor in details["credits"]["cast"][:limit]]

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    result = asyncio.run(api.get_tmdb_movie_preview(693134))

    assert result["tmdb_id"] == 693134
    assert result["title"] == "Dune"
    assert result["director"] == "Denis Villeneuve"
    assert result["genres"] == ["Science-Fiction"]
    assert result["cast"] == ["TimothÃ©e Chalamet"]
    assert result["vote_average"] == 8.24
    assert result["poster_url"].endswith("/w500/dune.jpg")


def test_tmdb_rating_resolves_an_unlinked_library_media(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=None)

    class FakeTMDB:
        async def search_movie(self, query, year=None):
            assert query == "Dune"
            return [{"id": 693134, "title": "Dune", "release_date": "2021-09-15"}]

        async def get_movie_details(self, tmdb_id):
            assert tmdb_id == 693134
            return {"vote_average": 8.24}

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    result = asyncio.run(api.get_tmdb_rating("1", store))

    assert result == {"rating": 8.24, "tmdb_id": 693134}
    assert store.media.tmdb_id == 693134


def test_tmdb_rating_is_null_when_media_has_no_tmdb_id(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=None)

    class UnexpectedTMDB:
        def __init__(self):
            raise AssertionError("TMDB ne doit pas être appelé sans tmdb_id")

    monkeypatch.setattr(api, "TMDBClient", UnexpectedTMDB)

    result = asyncio.run(api.get_tmdb_rating("1", store))

    assert result == {"rating": None}


def test_tmdb_rating_returns_vote_average(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=693134)

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            assert tmdb_id == 693134
            return {"vote_average": 8.24}

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    result = asyncio.run(api.get_tmdb_rating("1", store))

    assert result == {"rating": 8.24}


def test_tmdb_rating_is_null_when_tmdb_has_no_vote_average(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=693134)

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            return {"vote_average": None}

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    assert asyncio.run(api.get_tmdb_rating("1", store)) == {"rating": None}


def test_tmdb_rating_is_null_when_tmdb_request_fails(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=693134)

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            raise RuntimeError("TMDB indisponible")

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    assert asyncio.run(api.get_tmdb_rating("1", store)) == {"rating": None}


def test_tmdb_rating_returns_404_for_unknown_media():
    class MissingStore:
        async def fetch_one(self, media_id):
            return None

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.get_tmdb_rating("missing", MissingStore()))

    assert error.value.status_code == 404
