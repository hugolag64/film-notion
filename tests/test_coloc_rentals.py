"""Multi-user rental rules: expiry, shared kept films and no bypass of the rental flow."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import backend.api as api_module
from backend.api import _ensure_playback_access
from backend.auth_api import AuthContext
from backend.config import Config
from backend.core.media_server import Availability
from backend.core.models import RecommendationEvent, RecommendationSession, Rental
from backend.core.store import MediaStore
from tests.test_auth_api import _client, _setup


NOW = datetime.now(timezone.utc)


def _rental(rental_id, media_id, user_id, **fields):
    return Rental(
        id=rental_id, media_id=media_id, backstage_user_id=user_id,
        requested_at=NOW, created_at=NOW, updated_at=NOW, **fields,
    )


def _login_as_new_user(client, name="Paul"):
    email = f"{name.lower()}@example.com"
    client.post("/api/auth/users", json={"display_name": name, "email": email, "password": "12345678"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": email, "password": "12345678", "remember_device": False})
    return client.get("/api/auth/me").json()["user"]["id"]


class RecordingService:
    """Fake media service: records add() calls, never touches Seerr directly."""

    def __init__(self, store, state="requested"):
        self.store = store
        self.state = state
        self.calls = []
        self.seerr = self

    async def acquisition_defaults(self, media):
        return {"quality_profile_id": 5, "root_folder": "/media/movies", "language_profile_id": None, "monitor": "all"}

    async def add(self, media, quality_profile_id, root_folder, language_profile_id, monitor):
        self.calls.append((media.id, quality_profile_id, root_folder))
        return await self.store.upsert_availability(Availability(media_id=media.id, provider="radarr", state=self.state))

    async def add_with_defaults(self, media):
        return await self.add(media, **(await self.acquisition_defaults(media)))

    async def request_media(self, **kwargs):
        raise AssertionError("a non-admin request must not reach Seerr directly")

    async def cancel_request(self, request_id):
        raise AssertionError("a non-admin must not cancel Seerr requests")


# --- 1. Expiry -------------------------------------------------------------

def test_expire_rentals_only_expires_overdue_temporary_rentals(tmp_path):
    store = MediaStore(str(tmp_path / "b.db"))
    store.init_schema()
    for media_id in ("a", "b", "c", "d"):
        asyncio.run(store.create({"id": media_id, "title": media_id, "type": "Film"}))
    past, future = NOW - timedelta(days=1), NOW + timedelta(days=3)
    asyncio.run(store.create_rental(_rental("overdue", "a", "u", status="available", expires_at=past)))
    asyncio.run(store.create_rental(_rental("pending", "b", "u", status="keep_requested", expires_at=past)))
    asyncio.run(store.create_rental(_rental("kept", "c", "u", status="kept", storage_policy="permanent")))
    asyncio.run(store.create_rental(_rental("running", "d", "u", status="available", expires_at=future)))

    assert asyncio.run(store.expire_rentals(NOW)) == 1

    assert asyncio.run(store.get_rental("overdue")).status == "expired"
    assert asyncio.run(store.get_rental("pending")).status == "keep_requested"
    assert asyncio.run(store.get_rental("kept")).status == "kept"
    assert asyncio.run(store.get_rental("running")).status == "available"
    assert asyncio.run(store.count_active_rentals("u")) == 2
    context = asyncio.run(store.storage_context(NOW - timedelta(days=30)))
    assert "a" not in context["rental_media_ids"]


def test_overdue_rentals_no_longer_block_a_new_rental(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    for index in range(5):
        asyncio.run(store.create({"id": f"old-{index}", "title": f"Old {index}", "type": "Film", "tmdb_id": index + 1}))
        asyncio.run(store.create_rental(_rental(
            f"r-{index}", f"old-{index}", user_id, status="available", expires_at=NOW - timedelta(days=1),
        )))
    asyncio.run(store.create({"id": "new", "title": "New", "type": "Film", "tmdb_id": 99}))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/medias/new/acquisition", json={})

    assert response.status_code == 200
    assert response.json()["rental"]["status"] == "requested"


# --- 2. Kept films are shared ----------------------------------------------

def test_a_kept_film_is_playable_by_every_flatmate(tmp_path):
    store = MediaStore(str(tmp_path / "b.db"))
    store.init_schema()
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    asyncio.run(store.create_rental(_rental("r", media.id, "user-a", status="kept", storage_policy="permanent")))
    other = AuthContext(user={"id": "user-b", "role": "user"}, session_id="s", token="t")

    assert asyncio.run(_ensure_playback_access(other, media.id, store)) is None


def test_renting_a_film_already_in_the_library_creates_no_rental(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", state="available")))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/medias/dune/acquisition", json={})

    assert response.status_code == 200
    assert "rental" not in response.json()
    assert service.calls == []
    assert asyncio.run(store.list_rentals_for_media("dune")) == []


def test_renting_a_film_another_flatmate_rented_reuses_the_file(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", state="available")))
    asyncio.run(store.create_rental(_rental(
        "claire", "dune", "claire-id", status="available", expires_at=NOW + timedelta(days=5),
    )))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/medias/dune/acquisition", json={})

    assert response.status_code == 200
    rental = response.json()["rental"]
    assert rental["status"] == "available"
    assert rental["expires_at"] is not None
    assert service.calls == []


def test_non_admin_cannot_choose_the_radarr_root_folder(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    client.post("/api/medias/dune/acquisition", json={"root_folder": "/media/permanent"})

    assert service.calls == [("dune", 5, "/media/movies")]


# --- 3. Seerr goes through the rental flow --------------------------------

def test_non_admin_seerr_request_becomes_a_rental(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/seerr/requests", json={"tmdb_id": 438631, "media_type": "movie"})

    assert response.status_code == 200
    assert response.json()["rental"]["backstage_user_id"] == user_id
    assert service.calls == [("dune", 5, "/media/movies")]


def test_non_admin_seerr_request_creates_the_missing_film(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            return {"title": "Arrival", "release_date": "2016-11-09", "overview": "Aliens."}

        def get_director(self, details): return None
        def get_genres(self, details): return []
        def get_poster_url(self, details): return None
        def get_backdrop_url(self, details): return None
        def get_cast(self, details, limit=5): return []

    monkeypatch.setattr(api_module, "TMDBClient", FakeTMDB)

    response = client.post("/api/seerr/requests", json={"tmdb_id": 329865, "media_type": "movie"})

    assert response.status_code == 200
    assert [media.title for media in asyncio.run(store.fetch_all())] == ["Arrival"]
    assert response.json()["rental"]["status"] == "requested"


def test_non_admin_cannot_request_series_or_cancel_on_seerr(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    service = RecordingService(MediaStore(Config.DB_PATH))
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    assert client.post("/api/seerr/requests", json={"tmdb_id": 1, "media_type": "tv"}).status_code == 403
    assert client.delete("/api/seerr/requests/12").status_code == 403


def test_non_admin_dashboard_hides_the_global_seerr_queue(tmp_path, monkeypatch):
    store = MediaStore(str(tmp_path / "b.db"))
    store.init_schema()

    class FakeSeerr:
        async def list_requests(self, **kwargs):
            raise AssertionError("the Seerr queue is admin-only")

    class FakeService:
        radarr = sonarr = None
        seerr = FakeSeerr()

    async def empty_pool(*_args):
        return []

    monkeypatch.setattr(api_module, "get_media_server_service", lambda _store: FakeService())
    monkeypatch.setattr(api_module, "_recommendation_pool", empty_pool)
    user = AuthContext(user={"id": "paul", "role": "user"}, session_id="s", token="t")

    payload = asyncio.run(api_module.dashboard_home(user, store))

    assert payload["requests"] == []


# --- 4. Recommendation download goes through the rental flow --------------

def test_non_admin_recommendation_download_creates_a_rental(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.create_recommendation_session(RecommendationSession(
        id="session", backstage_user_id=user_id, created_at=NOW,
    )))
    asyncio.run(store.record_recommendation_event(RecommendationEvent(
        id="event", backstage_user_id=user_id, session_id="session",
        event_type="session_completed", value="438631", created_at=NOW,
    )))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/recommendations/sessions/session/confirm", json={"tmdb_id": 438631, "download": True})

    assert response.status_code == 200
    assert response.json()["download_error"] is None
    assert [rental.backstage_user_id for rental in asyncio.run(store.list_rentals_for_media("dune"))] == [user_id]
