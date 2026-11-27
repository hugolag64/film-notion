import asyncio

import httpx

from backend import api
from backend.auth_api import AuthContext
from backend.core.recommendations import RecommendationCandidate
from backend.core.store import MediaStore


def current_user(user_id="hugo"):
    return AuthContext(user={"id": user_id, "role": "user"}, session_id="session", token="token")


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "dashboard.db"))
    store.init_schema()
    return store


def test_dashboard_route_returns_user_scoped_content_and_recommendations(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    media = asyncio.run(store.create({"id": "m1", "title": "Dune", "type": "Film"}))
    asyncio.run(store.upsert_user_media_state("hugo", media.id, {"is_watchlist": True}))
    asyncio.run(store.upsert_user_media_state("other", media.id, {"is_favorite": True}))
    candidate = RecommendationCandidate(tmdb_id=42, title="Arrival", score=.9)
    async def pool(_current, _store, _preferences):
        return [candidate]
    monkeypatch.setattr(api, "_recommendation_pool", pool)

    payload = asyncio.run(api.dashboard_home(current_user(), store))

    assert payload["recommendations"] == [candidate.model_dump(mode="json")]
    assert any(
        item["kind"] == "media_interacted" and item["media_id"] == "m1"
        for item in payload["activity"]
    )


def test_dashboard_route_survives_optional_recommendation_network_failure(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    async def failing_pool(_current, _store, _preferences):
        raise httpx.HTTPError("TMDB offline")
    monkeypatch.setattr(api, "_recommendation_pool", failing_pool)

    payload = asyncio.run(api.dashboard_home(current_user(), store))

    assert payload["recommendations"] == []
    assert "continue_watching" in payload
    assert "availability" in payload


def test_dashboard_route_does_not_import_media_library_on_every_load(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    class FailingMediaService:
        radarr = object()
        sonarr = None
        seerr = None

        async def import_existing_libraries(self):
            raise AssertionError("The dashboard must not import the media library")

    monkeypatch.setattr(api, "get_media_server_service", lambda _store: FailingMediaService())

    payload = asyncio.run(api.dashboard_home(current_user(), store))

    assert "continue_watching" in payload


def test_admin_dashboard_loads_the_full_active_seerr_queue(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    captured = {}

    class FakeSeerr:
        async def list_requests(self, **kwargs):
            captured.update(kwargs)
            return [{"id": 12, "media": {"status": 2, "title": "L'Odyssée"}}]

        async def cancel_request(self, _request_id):
            raise AssertionError("La demande encore en attente ne doit pas être supprimée")

    class FakeMediaService:
        radarr = None
        sonarr = None
        seerr = FakeSeerr()

    async def empty_recommendation_pool(_current, _store, _preferences):
        return []

    monkeypatch.setattr(api, "get_media_server_service", lambda _store: FakeMediaService())
    monkeypatch.setattr(api, "_recommendation_pool", empty_recommendation_pool)

    admin = AuthContext(user={"id": "hugo", "role": "admin"}, session_id="session", token="token")
    payload = asyncio.run(api.dashboard_home(admin, store))

    assert captured["take"] == 100
    assert payload["requests"][0]["title"] == "L'Odyssée"


def test_dashboard_recommendation_can_be_added_to_current_users_watchlist(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create({"id": "m1", "title": "Arrival", "type": "Film", "tmdb_id": 42}))

    payload = asyncio.run(api.add_recommendation_to_watchlist(
        api.RecommendationWatchlistRequest(tmdb_id=42), current_user(), store,
    ))

    assert payload.id == "m1"
    assert payload.is_watchlist is True
    state = asyncio.run(store.get_user_media_state("hugo", "m1"))
    assert state.is_watchlist is True


def test_dashboard_never_deletes_completed_seerr_requests(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    deleted = []

    class Seerr:
        async def list_requests(self, **kwargs):
            return [{"id": 12, "media": {"status": 5, "title": "Completed"}}]

        async def cancel_request(self, request_id):
            deleted.append(request_id)

    class Service:
        seerr = Seerr()

    async def pool(*args):
        return []

    monkeypatch.setattr(api, "get_media_server_service", lambda _: Service())
    monkeypatch.setattr(api, "_recommendation_pool", pool)
    admin = AuthContext(user={"id": "hugo", "role": "admin"}, session_id="s", token="t")
    payload = asyncio.run(api.dashboard_home(admin, store))
    assert deleted == [], "Reading the dashboard must never delete Seerr requests"
    assert payload["requests"] == []


def test_dashboard_requests_match_what_radarr_really_does(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    class Seerr:
        async def list_requests(self, **kwargs):
            return [
                {"id": 1, "status": 2, "type": "movie", "media": {"tmdbId": 581, "status": 3, "title": "Danse avec les loups"}},
                {"id": 2, "status": 5, "type": "tv", "media": {"tmdbId": 456, "status": 4, "title": "Les Simpson"}},
                {"id": 3, "status": 2, "type": "movie", "media": {"tmdbId": 1300968, "status": 3, "title": "Hunger Games"}},
                {"id": 4, "status": 2, "type": "movie", "media": {"tmdbId": 1653288, "status": 3, "title": "Mister Jack"}},
                {"id": 5, "status": 1, "type": "movie", "media": {"tmdbId": 77, "status": 2, "title": "Pas encore approuvé"}},
                {"id": 6, "status": 2, "type": "movie", "media": {"tmdbId": 88, "status": 3, "title": "Déjà importé"}},
            ]

        async def cancel_request(self, request_id):
            raise AssertionError("Reading the dashboard must never delete Seerr requests")

    class Radarr:
        async def list_library(self):
            return [
                {"id": 22, "tmdbId": 581, "hasFile": False, "status": "released"},
                {"id": 23, "tmdbId": 1300968, "hasFile": False, "status": "inCinemas"},
                {"id": 24, "tmdbId": 88, "hasFile": True, "status": "released"},
            ]

        async def list_queue(self):
            return [{"movieId": 22, "status": "completed", "trackedDownloadState": "importBlocked"}]

    class Service:
        radarr = Radarr()
        seerr = Seerr()

    async def pool(*args):
        return []

    monkeypatch.setattr(api, "get_media_server_service", lambda _: Service())
    monkeypatch.setattr(api, "_recommendation_pool", pool)
    monkeypatch.setattr(api, "_hydrate_seerr_requests", lambda requests: asyncio.sleep(0, requests))
    admin = AuthContext(user={"id": "hugo", "role": "admin"}, session_id="s", token="t")
    payload = asyncio.run(api.dashboard_home(admin, store))

    labels = {item["title"]: item["status_label"] for item in payload["requests"]}
    assert labels == {
        "Danse avec les loups": "Import bloqué",
        "Hunger Games": "En attente de sortie",
        "Pas encore approuvé": "En attente",
    }
