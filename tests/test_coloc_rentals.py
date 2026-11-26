"""Multi-user rental rules: expiry, shared kept films and no bypass of the rental flow."""
import asyncio
import json
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
    # Accounts created by the admin must pick their own password before using the API.
    client.post("/api/auth/change-initial-password", json={
        "new_password": "87654321", "password_confirmation": "87654321",
    })
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


# --- 5. Rental status and limit exposed to the flatmate UI ----------------

@pytest.mark.parametrize("download_state, rental_status", [
    ("searching", "requested"), ("imported", "downloading"), ("downloading", "downloading"),
])
def test_rental_status_follows_radarr_vocabulary(tmp_path, monkeypatch, download_state, rental_status):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = RecordingService(store, state=download_state)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/medias/dune/acquisition", json={})

    assert response.status_code == 200
    assert response.json()["rental"]["status"] == rental_status


def test_rentals_endpoint_exposes_the_active_rental_limit(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)

    payload = client.get("/api/rentals").json()

    assert payload == {
        "rentals": [],
        "max_active_rentals": api_module.MAX_ACTIVE_RENTALS,
        "max_queued_rentals": api_module.MAX_QUEUED_RENTALS,
    }


# --- 6. Series, decisions, availability and expired cleanup --------------

def test_non_admin_cannot_rent_a_series(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "lost", "title": "Lost", "type": "Série", "tmdb_id": 4607}))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/medias/lost/acquisition", json={})

    assert response.status_code == 403
    assert service.calls == []


def test_keep_decision_notification_names_the_film(tmp_path):
    store = MediaStore(str(tmp_path / "b.db"))
    store.init_schema()
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    asyncio.run(store.create_rental(_rental(
        "r", "dune", "paul", status="keep_requested", expires_at=NOW + timedelta(days=4),
    )))
    admin = AuthContext(user={"id": "admin", "role": "admin"}, session_id="s", token="t")

    asyncio.run(api_module.refuse_keep_request("r", admin, store))

    [notification] = asyncio.run(store.list_notifications("paul"))
    assert notification.kind == "retention_refused"
    assert "« Dune » ne sera pas conservé" in notification.message


def test_library_available_lists_only_media_ready_on_jellyfin(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    for media_id in ("ready", "pending"):
        asyncio.run(store.create({"id": media_id, "title": media_id, "type": "Film"}))
    asyncio.run(store.upsert_availability(Availability(
        media_id="ready", provider="radarr", state="available", jellyfin_id="jf-1",
    )))
    asyncio.run(store.upsert_availability(Availability(media_id="pending", provider="radarr", state="downloading")))

    assert client.get("/api/library/available").json()["media_ids"] == ["ready"]


def test_library_available_shares_download_states_with_flatmates(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    for media_id in ("ready", "pending"):
        asyncio.run(store.create({"id": media_id, "title": media_id, "type": "Film"}))
    asyncio.run(store.upsert_availability(Availability(
        media_id="ready", provider="radarr", state="available", jellyfin_id="jf-1",
    )))
    asyncio.run(store.upsert_availability(Availability(
        media_id="pending", provider="radarr", state="downloading", progress_percent=42, last_error="boom",
    )))

    body = client.get("/api/library/available").json()
    assert body["media_ids"] == ["ready"]
    assert body["states"] == {
        "ready": {"state": "available", "progress_percent": None, "ready": True},
        "pending": {"state": "downloading", "progress_percent": 42, "ready": False},
    }
    assert "boom" not in json.dumps(body)


class ExpiredRadarr:
    def __init__(self, library):
        self.library = library
        self.deleted = []

    async def list_library(self):
        return [item for item in self.library if item["id"] not in {deleted for deleted, _ in self.deleted}]

    async def delete_movie(self, movie_id, delete_files=False):
        self.deleted.append((movie_id, delete_files))


def test_delete_expired_rentals_only_removes_films_nobody_rents_anymore(tmp_path):
    from backend.core.media_server import MediaServerService

    store = MediaStore(str(tmp_path / "b.db"))
    store.init_schema()
    old = NOW - timedelta(days=60)
    for media_id, tmdb_id in (("gone", 1), ("shared", 2), ("admin", 3)):
        asyncio.run(store.create({"id": media_id, "title": media_id, "type": "Film", "tmdb_id": tmdb_id, "created_at": old}))
    asyncio.run(store.create_rental(_rental("r1", "gone", "paul", status="expired")))
    asyncio.run(store.create_rental(_rental("r2", "shared", "paul", status="expired")))
    asyncio.run(store.create_rental(_rental("r3", "shared", "claire", status="available", expires_at=NOW + timedelta(days=3))))
    radarr = ExpiredRadarr([
        {"id": tmdb_id * 10, "tmdbId": tmdb_id, "hasFile": True, "sizeOnDisk": 1024**3, "added": old.isoformat()}
        for tmdb_id in (1, 2, 3)
    ])
    service = MediaServerService(store, radarr=radarr)

    candidates = {item.media_id: item for item in asyncio.run(service.storage_candidates())}
    assert [candidates[key].rental_expired for key in ("gone", "shared", "admin")] == [True, False, False]

    result = asyncio.run(service.delete_expired_rentals("admin-id"))

    assert result["deleted"] == [{"media_id": "gone", "title": "gone"}]
    assert result["failed"] == []
    assert radarr.deleted == [(10, True)]


# --- 7. Waiting queue -------------------------------------------------------

def _seed_rentals(store, user_id, count, status, prefix):
    for index in range(count):
        asyncio.run(store.create({"id": f"{prefix}-{index}", "title": f"{prefix} {index}", "type": "Film", "tmdb_id": 1000 + index}))
        asyncio.run(store.create_rental(_rental(
            f"{prefix}-r{index}", f"{prefix}-{index}", user_id, status=status,
            expires_at=NOW + timedelta(days=5) if status == "available" else None,
        )))


def test_waiting_requests_do_not_use_the_five_rental_slots(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    _seed_rentals(store, user_id, 5, "requested", "waiting")
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", state="available")))
    asyncio.run(store.create_rental(_rental("claire", "dune", "claire-id", status="available", expires_at=NOW + timedelta(days=5))))
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: RecordingService(store)

    response = client.post("/api/medias/dune/acquisition", json={})

    assert response.status_code == 200
    assert asyncio.run(store.count_rental_slots(user_id)) == {"in_use": 1, "queued": 5}


def test_instant_rental_is_refused_when_five_rentals_are_in_use(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    _seed_rentals(store, user_id, 5, "available", "watching")
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", state="available")))
    asyncio.run(store.create_rental(_rental("claire", "dune", "claire-id", status="available", expires_at=NOW + timedelta(days=5))))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/medias/dune/acquisition", json={})

    assert response.status_code == 409
    assert "locations en cours" in response.json()["detail"]


def test_a_downloading_request_counts_as_in_use(tmp_path):
    store = MediaStore(str(tmp_path / "b.db"))
    store.init_schema()
    _seed_rentals(store, "paul", 2, "requested", "req")
    asyncio.run(store.upsert_availability(Availability(media_id="req-0", provider="radarr", state="downloading")))

    assert asyncio.run(store.count_rental_slots("paul")) == {"in_use": 1, "queued": 1}


class CancelRadarr:
    def __init__(self):
        self.deleted = []

    async def delete_movie(self, movie_id, delete_files=False):
        self.deleted.append(movie_id)


class CancelService(RecordingService):
    def __init__(self, store):
        super().__init__(store)
        self.radarr = CancelRadarr()


def _waiting_rental(client, store, user_id, *, state="requested"):
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", arr_id=42, state=state)))
    asyncio.run(store.create_rental(_rental("mine", "dune", user_id, status="requested")))
    service = CancelService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service
    return service


def test_flatmate_cancels_a_waiting_request_and_radarr_forgets_it(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    service = _waiting_rental(client, store, user_id)

    response = client.post("/api/rentals/mine/cancel")

    assert response.status_code == 200
    assert response.json()["rental"]["status"] == "cancelled"
    assert service.radarr.deleted == [42]
    assert asyncio.run(store.get_availability("dune")).state == "error"


def test_cancel_keeps_radarr_when_another_flatmate_waits_for_the_film(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    service = _waiting_rental(client, store, user_id)
    asyncio.run(store.create_rental(_rental("claire", "dune", "claire-id", status="requested")))

    assert client.post("/api/rentals/mine/cancel").status_code == 200
    assert service.radarr.deleted == []


def test_cancel_is_refused_once_the_download_started(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    service = _waiting_rental(client, store, user_id, state="downloading")

    assert client.post("/api/rentals/mine/cancel").status_code == 409
    assert service.radarr.deleted == []


def test_rentals_expose_the_download_state(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    user_id = _login_as_new_user(client)
    store = MediaStore(Config.DB_PATH)
    _waiting_rental(client, store, user_id)

    [rental] = client.get("/api/rentals").json()["rentals"]

    assert rental["download_state"] == "requested"


def test_a_film_already_downloading_is_not_requested_twice(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", state="downloading")))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    admin = client.post("/api/seerr/requests", json={"tmdb_id": 438631, "media_type": "movie"})
    _login_as_new_user(client)
    flatmate = client.post("/api/medias/dune/acquisition", json={})

    assert admin.status_code == 200 and admin.json()["already_requested"] is True
    assert admin.json()["availability"]["state"] == "downloading"
    assert flatmate.status_code == 200 and flatmate.json()["already_requested"] is True
    assert flatmate.json()["rental"]["status"] == "downloading"
    assert service.calls == []


def test_admin_film_request_goes_through_the_catalogue(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    store = MediaStore(Config.DB_PATH)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = RecordingService(store)
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service

    response = client.post("/api/seerr/requests", json={"tmdb_id": 438631, "media_type": "movie"})

    assert response.status_code == 200
    assert response.json()["availability"]["state"] == "requested"
    assert "rental" not in response.json()
    assert [call[0] for call in service.calls] == ["dune"]


def test_seerr_duplicate_still_records_the_pending_request(tmp_path):
    from backend.core.media_server import MediaServerService
    from backend.core.models import Media
    from backend.core.seerr import SeerrDuplicateRequest

    class DuplicateSeerr:
        async def request_media(self, **kwargs):
            raise SeerrDuplicateRequest("Seerr HTTP 409: Request for this media already exists")

    store = MediaStore(str(tmp_path / "db.sqlite"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, seerr=DuplicateSeerr())

    availability = asyncio.run(service.add(media, None, None, None, "all"))

    assert isinstance(media, Media)
    assert availability.state == "requested"
