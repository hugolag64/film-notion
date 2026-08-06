import asyncio

import pytest
from fastapi import HTTPException

from backend import api
from backend.auth_api import AuthContext
from backend.core.media_server import Availability
from backend.core.models import RecommendationEvent, RecommendationSession
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def current_user():
    return AuthContext(user={"id": "hugo", "role": "user"}, session_id="auth", token="token")


def completed_session(store):
    session = RecommendationSession(
        id="recommendation-1", backstage_user_id="hugo", status="completed",
        session_preferences={}, created_at=api.datetime.now(api.timezone.utc),
    )
    asyncio.run(store.create_recommendation_session(session))
    asyncio.run(store.record_recommendation_event(RecommendationEvent(
        id="completed", backstage_user_id="hugo", session_id=session.id,
        event_type="session_completed", value="42", created_at=api.datetime.now(api.timezone.utc),
    )))
    return session


class FakeTMDB:
    async def get_movie_details(self, tmdb_id):
        return {"id": tmdb_id, "title": "Film choisi", "original_title": "Chosen Film", "release_date": "2024-01-01", "overview": "Synopsis"}

    def get_director(self, details):
        return "Réalisateur"

    def get_genres(self, details):
        return ["Drame"]

    def get_poster_url(self, details):
        return "/poster.jpg"

    def get_backdrop_url(self, details):
        return "/backdrop.jpg"

    def get_cast(self, details, limit=5):
        return ["Acteur"]


class FakeAcquisition:
    def __init__(self, store, fail=False):
        self.store = store
        self.fail = fail
        self.calls = 0

    async def add_with_defaults(self, media):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Radarr indisponible")
        availability = Availability(media_id=media.id, provider="radarr", state="requested")
        return await self.store.upsert_availability(availability)


def test_confirm_recommendation_creates_media_and_requests_download(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    session = completed_session(store)
    acquisition = FakeAcquisition(store)
    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    response = asyncio.run(api.confirm_recommendation(
        session.id, api.RecommendationConfirmRequest(tmdb_id=42), current_user(), store, acquisition,
    ))

    assert response["media"]["tmdb_id"] == 42
    assert response["media"]["rating"] is None
    assert response["media"]["status"] == "À regarder"
    assert response["availability"]["state"] == "requested"
    assert acquisition.calls == 1


def test_confirm_recommendation_is_idempotent(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    session = completed_session(store)
    acquisition = FakeAcquisition(store)
    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    asyncio.run(api.confirm_recommendation(session.id, api.RecommendationConfirmRequest(tmdb_id=42), current_user(), store, acquisition))
    response = asyncio.run(api.confirm_recommendation(session.id, api.RecommendationConfirmRequest(tmdb_id=42), current_user(), store, acquisition))

    assert response["media"]["tmdb_id"] == 42
    assert acquisition.calls == 1
    assert len(asyncio.run(store.fetch_all())) == 1


def test_confirm_recommendation_rejects_a_film_not_selected_by_session(tmp_path):
    store = make_store(tmp_path)
    session = completed_session(store)

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.confirm_recommendation(
            session.id, api.RecommendationConfirmRequest(tmdb_id=99), current_user(), store, FakeAcquisition(store),
        ))

    assert error.value.status_code == 403


def test_confirm_recommendation_keeps_library_item_when_download_fails(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    session = completed_session(store)
    acquisition = FakeAcquisition(store, fail=True)
    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    response = asyncio.run(api.confirm_recommendation(
        session.id, api.RecommendationConfirmRequest(tmdb_id=42), current_user(), store, acquisition,
    ))

    assert response["media"]["tmdb_id"] == 42
    assert response["availability"] is None
    assert response["download_error"] == "Radarr indisponible"
    assert len(asyncio.run(store.fetch_all())) == 1
