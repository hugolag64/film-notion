import asyncio

from backend.core.media_server import Availability, MediaServerService
from backend.core.store import MediaStore


class FakeRadarr:
    async def add_movie(self, tmdb_id, quality_profile_id, root_folder):
        return {"id": 42, "tmdbId": tmdb_id}
    async def list_library(self):
        return [{"id": 42, "tmdbId": 438631, "hasFile": True}]

    async def list_queue(self):
        return []


class FakeJellyfin:
    async def find_by_tmdb(self, tmdb_id, media_type):
        return {"Id": "jelly-dune"}

    def playback_url(self, item_id):
        return f"https://jellyfin.test/web/index.html#!/details?id={item_id}"


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
