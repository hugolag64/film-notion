import asyncio

import httpx
from datetime import datetime, timedelta, timezone

import backend.core.media_server as media_server_module
from backend.core.media_server import Availability, MediaServerService
from backend.core.models import Rental
from backend.core.models import Notification
from backend.core.store import MediaStore
from backend.core.scheduler import notify_automatic_events
from backend.config import Config


class FakeRadarr:
    def __init__(self, queue=None):
        self.queue = queue or []

    async def add_movie(self, tmdb_id, quality_profile_id, root_folder):
        return {"id": 42, "tmdbId": tmdb_id}
    async def list_library(self):
        return [{"id": 42, "tmdbId": 438631, "hasFile": True}]

    async def list_queue(self):
        return self.queue


class FakeDiskRadarr(FakeRadarr):
    async def disk_space(self):
        return [
            {"path": "/", "freeSpace": 300 * 1024**3},
            {"path": "/data", "freeSpace": 40 * 1024**3},
        ]


class OptionsRadarr(FakeRadarr):
    async def list_options(self):
        return {
            "quality_profiles": [
                {"id": 4, "name": "720p"},
                {"id": 9, "name": "1080 FR - max 10go"},
            ],
            "root_folders": [{"path": "D:/Films"}, {"path": "E:/Films"}],
        }


class FakeSeerr:
    def __init__(self):
        self.calls = []

    async def request_media(self, **payload):
        self.calls.append(payload)
        return {"id": 77, "status": 2}


class FakeJellyfin:
    async def find_by_tmdb(self, tmdb_id, media_type):
        return {"Id": "jelly-dune"}

    def playback_url(self, item_id):
        return f"https://jellyfin.test/web/index.html#!/details?id={item_id}"

    def playback_manifest_url(self, item_id):
        return f"https://jellyfin.test/Videos/{item_id}/master.m3u8"


class FakePlaybackJellyfin(FakeJellyfin):
    error = None

    async def user_playback(self, user_id):
        if self.error:
            raise self.error
        return [{
            "jellyfin_id": "jelly-dune",
            "tmdb_id": 438631,
            "title": "Dune",
            "item_type": "Movie",
            "series_title": None,
            "series_jellyfin_id": None,
            "season_number": None,
            "episode_number": None,
            "position_ticks": 50 if user_id == "jf-hugo" else 80,
            "runtime_ticks": 100,
            "percent": 50.0 if user_id == "jf-hugo" else 80.0,
            "played": False,
            "last_played_at": None,
        }]


def test_imported_arr_item_becomes_available_when_jellyfin_matches(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({
        "id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631,
        "support": "Streaming",
    }))
    service = MediaServerService(store, radarr=FakeRadarr(), jellyfin=FakeJellyfin())

    availability = asyncio.run(service.sync_media(media.id))

    assert availability.state == "available"
    assert availability.jellyfin_id == "jelly-dune"
    assert asyncio.run(store.fetch_one(media.id)).support == "Serveur"


def test_sync_media_starts_a_rental_when_jellyfin_has_the_film(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_rental(Rental(
        id="rental", media_id=media.id, backstage_user_id="hugo",
        requested_at=now, created_at=now, updated_at=now,
    )))
    service = MediaServerService(store, radarr=FakeRadarr(), jellyfin=FakeJellyfin())

    asyncio.run(service.sync_media(media.id))

    rental = asyncio.run(store.get_rental("rental"))
    assert rental.status == "available"
    assert rental.available_at is not None
    assert rental.expires_at is not None


def test_sync_reclaims_reused_arr_id_from_stale_media_link(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    stale = asyncio.run(store.create({"id": "old", "title": "Old", "type": "Film", "tmdb_id": 1}))
    asyncio.run(store.upsert_availability(Availability(
        media_id=stale.id, provider="radarr", arr_id=42, state="requested",
    )))
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=FakeRadarr(), jellyfin=FakeJellyfin())

    availability = asyncio.run(service.sync_media(media.id))

    assert availability.state == "available"
    assert availability.arr_id == 42
    assert asyncio.run(store.get_availability(stale.id)).arr_id is None


def test_add_film_creates_requested_availability(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=FakeRadarr())

    availability = asyncio.run(service.add(media, 5, "D:/Media/Films", None, "all"))

    assert availability.state == "requested"
    assert availability.arr_id == 42


def test_admin_defaults_resolve_quality_profile_by_name_and_first_root(tmp_path, monkeypatch):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    monkeypatch.setattr(Config, "RADARR_DEFAULT_QUALITY_PROFILE_NAME", "1080 FR - max 10go")
    monkeypatch.setattr(Config, "RADARR_DEFAULT_ROOT_FOLDER", None)
    service = MediaServerService(store, radarr=OptionsRadarr())

    defaults = asyncio.run(service.acquisition_defaults(media))

    assert defaults == {"quality_profile_id": 9, "root_folder": "D:/Films", "language_profile_id": None, "monitor": "all"}


def test_admin_defaults_reject_unknown_quality_profile(tmp_path, monkeypatch):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    monkeypatch.setattr(Config, "RADARR_DEFAULT_QUALITY_PROFILE_NAME", "4K introuvable")
    service = MediaServerService(store, radarr=OptionsRadarr())

    try:
        asyncio.run(service.acquisition_defaults(media))
    except ValueError as error:
        assert "4K introuvable" in str(error)
    else:
        raise AssertionError("An unknown admin quality profile should fail")


def test_add_film_uses_seerr_when_configured(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    seerr = FakeSeerr()
    service = MediaServerService(store, radarr=FakeRadarr(), seerr=seerr)

    availability = asyncio.run(service.add(media, 5, "D:/Media/Films", None, "all"))

    assert availability.state == "requested"
    assert availability.provider == "radarr"
    assert availability.arr_id is None
    assert seerr.calls == [{
        "tmdb_id": 438631, "media_type": "Film", "quality_profile_id": None,
        "root_folder": None, "language_profile_id": None, "monitor": "all",
    }]


def test_import_existing_library_links_matching_tmdb_media(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=FakeRadarr())

    linked = asyncio.run(service.import_existing_libraries())

    assert linked["linked"] == 1
    assert asyncio.run(store.get_availability(media.id)).arr_id == 42


def test_queue_progress_maps_to_downloading(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=FakeRadarr([{"movieId": 42, "size": 100, "sizeleft": 50}]))

    availability = asyncio.run(service.sync_media("dune"))

    assert availability.state == "downloading"
    assert availability.progress_percent == 50


def test_import_creates_missing_film_from_remote_tmdb_id(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    radarr = FakeRadarr()
    radarr.list_library = lambda: _async_result([{"id": 42, "tmdbId": 438631, "title": "Dune", "hasFile": True}])
    service = MediaServerService(store, radarr=radarr)

    summary = asyncio.run(service.import_existing_libraries())

    medias = asyncio.run(store.fetch_all())
    assert summary["created"] == 1
    assert medias[0].tmdb_id == 438631


def test_import_creates_missing_film_with_tmdb_poster_and_metadata(tmp_path, monkeypatch):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    radarr = FakeRadarr()
    radarr.list_library = lambda: _async_result([{"id": 42, "tmdbId": 438631, "title": "Dune", "hasFile": True}])

    class FakeTMDB:
        async def get_details(self, tmdb_id, is_series=False):
            return {"title": "Dune", "poster_path": "/dune.jpg", "overview": "Une histoire de sable."}

        def get_poster_url(self, details):
            return f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

        def get_backdrop_url(self, details):
            return None

        def get_genres(self, details):
            return ["Science-Fiction"]

        def get_cast(self, details, limit=5):
            return ["Paul"]

        def get_director(self, details):
            return "Denis Villeneuve"

    monkeypatch.setattr(media_server_module, "TMDBClient", FakeTMDB)
    service = MediaServerService(store, radarr=radarr)

    asyncio.run(service.import_existing_libraries())

    imported = asyncio.run(store.fetch_all())[0]
    assert imported.cover_url == "https://image.tmdb.org/t/p/w500/dune.jpg"
    assert imported.synopsis == "Une histoire de sable."


def test_sync_all_imports_remote_library_items_before_syncing(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    service = MediaServerService(store, radarr=FakeRadarr())

    result = asyncio.run(service.sync_all())

    assert result["synced"] == 1
    assert asyncio.run(store.fetch_all())[0].tmdb_id == 438631


async def _async_result(value):
    return value


def test_activity_returns_availability_items_and_disks(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    service = MediaServerService(store, radarr=FakeRadarr())

    activity = asyncio.run(service.activity())

    assert set(activity) == {"items", "disks"}


def test_storage_status_uses_data_disk_and_active_temporary_bytes(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_rental(Rental(
        id="rental", media_id=media.id, backstage_user_id="hugo", status="available",
        size_bytes=2 * 1024**3, requested_at=now, created_at=now, updated_at=now,
    )))
    service = MediaServerService(store, radarr=FakeDiskRadarr())

    status = asyncio.run(service.storage_status())

    assert status["min_free_bytes"] == 40 * 1024**3
    assert status["temporary_bytes"] == 2 * 1024**3
    assert status["low_space"] is False


def test_automatic_notifications_cover_expiration_availability_and_storage(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_rental(Rental(
        id="rental", media_id=media.id, backstage_user_id="user-id", status="available",
        requested_at=now, expires_at=now + timedelta(days=1), created_at=now, updated_at=now,
    )))
    asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", state="available", last_synced_at=now,
    )))

    class NotificationService:
        async def storage_status(self):
            return {"low_space": True, "temporary_quota_reached": False}

        async def activity(self):
            return {"items": [], "disks": []}

    auth_store = type("AuthStoreStub", (), {"list_users": lambda self: [
        {"id": "user-id", "display_name": "Paul", "role": "user"},
        {"id": "admin-id", "display_name": "Hugo", "role": "admin"},
    ]})()
    service = NotificationService()

    asyncio.run(notify_automatic_events(service, store, auth_store, now=now))
    asyncio.run(notify_automatic_events(service, store, auth_store, now=now))

    user_notifications = asyncio.run(store.list_notifications("user-id"))
    admin_notifications = asyncio.run(store.list_notifications("admin-id"))
    assert {item.kind for item in user_notifications} == {"rental_expiring", "media_available"}
    assert [item.kind for item in admin_notifications] == ["storage_alert"]


def test_playback_manifest_returns_available_jellyfin_item(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", jellyfin_id="jelly-dune", state="available",
    )))
    service = MediaServerService(store, jellyfin=FakeJellyfin())

    result = asyncio.run(service.playback_manifest(media.id))

    assert result == {"item_id": "jelly-dune", "url": "https://jellyfin.test/Videos/jelly-dune/master.m3u8"}


def test_playback_manifest_returns_none_without_availability(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))
    service = MediaServerService(store, jellyfin=FakeJellyfin())

    assert asyncio.run(service.playback_manifest(media.id)) is None


def test_playback_sync_is_isolated_by_backstage_user(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", jellyfin_id="jelly-dune", state="available",
    )))
    service = MediaServerService(store, jellyfin=FakePlaybackJellyfin())

    asyncio.run(service.sync_playback("hugo", "jf-hugo"))
    asyncio.run(service.sync_playback("ophelie", "jf-ophelie"))

    hugo = asyncio.run(service.playback_summary("hugo"))
    ophelie = asyncio.run(service.playback_summary("ophelie"))
    assert hugo["resume"][0].percent == 50
    assert ophelie["resume"][0].percent == 80


def test_playback_sync_starts_the_seven_day_rental_window(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", jellyfin_id="jelly-dune", state="available",
    )))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_rental(Rental(
        id="rental", media_id=media.id, backstage_user_id="hugo", status="available",
        requested_at=now, available_at=now, expires_at=now + timedelta(days=21),
        created_at=now, updated_at=now,
    )))
    asyncio.run(store.create_rental(Rental(
        id="kept-rental", media_id=media.id, backstage_user_id="ophelie", status="keep_requested",
        requested_at=now, available_at=now, expires_at=now + timedelta(days=21),
        created_at=now, updated_at=now,
    )))
    service = MediaServerService(store, jellyfin=FakePlaybackJellyfin())

    asyncio.run(service.sync_playback("hugo", "jf-hugo"))

    rental = asyncio.run(store.get_rental("rental"))
    assert rental.first_played_at is not None
    assert rental.expires_at < now + timedelta(days=8)
    kept = asyncio.run(store.get_rental("kept-rental"))
    assert kept.status == "keep_requested"
    assert kept.first_played_at is None
    assert kept.expires_at == now + timedelta(days=21)


def test_playback_sync_error_does_not_erase_existing_state(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    asyncio.run(store.upsert_availability(Availability(
        media_id=media.id, provider="radarr", jellyfin_id="jelly-dune", state="available",
    )))
    jellyfin = FakePlaybackJellyfin()
    service = MediaServerService(store, jellyfin=jellyfin)
    asyncio.run(service.sync_playback("hugo", "jf-hugo"))
    jellyfin.error = httpx.HTTPError("offline")

    try:
        asyncio.run(service.sync_playback("hugo", "jf-hugo"))
    except httpx.HTTPError:
        pass
    else:
        raise AssertionError("Jellyfin error should be visible to the API layer")
    assert asyncio.run(service.playback_summary("hugo"))["resume"][0].percent == 50
