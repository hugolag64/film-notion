import asyncio

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
