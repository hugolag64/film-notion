import asyncio

import httpx

from backend.core.media_server import Availability, MediaServerService
from backend.core.store import MediaStore


class FakeRadarr:
    def __init__(self, queue=None):
        self.queue = queue or []

    async def add_movie(self, tmdb_id, quality_profile_id, root_folder):
        return {"id": 42, "tmdbId": tmdb_id}
    async def list_library(self):
        return [{"id": 42, "tmdbId": 438631, "hasFile": True}]

    async def list_queue(self):
        return self.queue


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
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=FakeRadarr(), jellyfin=FakeJellyfin())

    availability = asyncio.run(service.sync_media(media.id))

    assert availability.state == "available"
    assert availability.jellyfin_id == "jelly-dune"


def test_add_film_creates_requested_availability(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    media = asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    service = MediaServerService(store, radarr=FakeRadarr())

    availability = asyncio.run(service.add(media, 5, "D:/Media/Films", None, "all"))

    assert availability.state == "requested"
    assert availability.arr_id == 42


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
        "tmdb_id": 438631, "media_type": "Film", "quality_profile_id": 5,
        "root_folder": "D:/Media/Films", "language_profile_id": None, "monitor": "all",
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


async def _async_result(value):
    return value


def test_activity_returns_availability_items_and_disks(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    service = MediaServerService(store, radarr=FakeRadarr())

    activity = asyncio.run(service.activity())

    assert set(activity) == {"items", "disks"}


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
