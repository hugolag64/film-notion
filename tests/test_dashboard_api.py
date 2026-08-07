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


def test_dashboard_route_survives_media_library_import_failure(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    class FailingMediaService:
        radarr = object()
        sonarr = None
        seerr = None

        async def import_existing_libraries(self):
            raise Exception("Radarr returned an unexpected response")

    monkeypatch.setattr(api, "get_media_server_service", lambda _store: FailingMediaService())

    payload = asyncio.run(api.dashboard_home(current_user(), store))

    assert "continue_watching" in payload


def test_dashboard_loads_the_full_active_seerr_queue(tmp_path, monkeypatch):
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

    payload = asyncio.run(api.dashboard_home(current_user(), store))

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
