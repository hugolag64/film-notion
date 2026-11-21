import asyncio
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import api
from backend.core.media_server import Availability
from backend.core.store import MediaStore


def _store(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631}))
    return store


def _count(store, table, media_id="dune"):
    with sqlite3.connect(store.db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE media_id = ?", (media_id,)).fetchone()[0]


class FakeRadarr:
    def __init__(self, error=None):
        self.deleted = []
        self.error = error

    async def delete_movie(self, movie_id, *, delete_files=True):
        if self.error:
            raise self.error
        self.deleted.append((movie_id, delete_files))
        return {}


def test_store_delete_removes_dependent_rows(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", arr_id=7, state="available")))
    asyncio.run(store.set_storage_protection("dune", True))

    assert asyncio.run(store.delete("dune")) is True

    assert asyncio.run(store.fetch_one("dune")) is None
    assert _count(store, "media_availability") == 0
    assert _count(store, "media_storage_protection") == 0


def test_delete_media_keeps_files_by_default(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", arr_id=7, state="available")))
    radarr = FakeRadarr()
    service = SimpleNamespace(store=store, radarr=radarr)

    result = asyncio.run(api.delete_media("dune", False, service))

    assert result == {"deleted": True, "media_id": "dune", "title": "Dune", "files_deleted": False}
    assert radarr.deleted == []
    assert asyncio.run(store.fetch_one("dune")) is None


def test_delete_media_with_files_removes_movie_from_radarr(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", arr_id=7, state="available")))
    radarr = FakeRadarr()
    service = SimpleNamespace(store=store, radarr=radarr)

    result = asyncio.run(api.delete_media("dune", True, service))

    assert result["files_deleted"] is True
    assert radarr.deleted == [(7, True)]
    assert asyncio.run(store.fetch_one("dune")) is None


def test_delete_media_keeps_fiche_when_radarr_fails(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.upsert_availability(Availability(media_id="dune", provider="radarr", arr_id=7, state="available")))
    service = SimpleNamespace(store=store, radarr=FakeRadarr(error=RuntimeError("Radarr down")))

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.delete_media("dune", True, service))

    assert error.value.status_code == 502
    assert asyncio.run(store.fetch_one("dune")) is not None


def test_delete_media_returns_404_for_unknown_media(tmp_path):
    service = SimpleNamespace(store=_store(tmp_path), radarr=None)

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.delete_media("missing", False, service))

    assert error.value.status_code == 404


def test_delete_media_route_is_admin_only():
    route = next(r for r in api.router.routes if r.path == "/api/medias/{media_id}" and "DELETE" in r.methods)
    assert any(dep.call is api.require_admin for dep in route.dependant.dependencies)
