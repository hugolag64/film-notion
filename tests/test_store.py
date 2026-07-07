import asyncio
from datetime import date

from backend.core.store import MediaStore


def _store(tmp_path) -> MediaStore:
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    return store


def test_create_generates_id_when_absent(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))
    assert media.title == "Dune"
    assert media.id  # uuid4 généré
    assert media.type is None
    assert media.categories == []
    assert media.tmdb_ok is False


def test_create_preserves_supplied_id(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"id": "notion-page-123", "title": "Arrival"}))
    assert media.id == "notion-page-123"


def test_create_persists_all_fields(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({
        "title": "Dune",
        "type": "Film",
        "status": "À regarder",
        "support": "Cinéma",
        "rating": "8",
        "release_date": date(2021, 10, 22),
        "director": "Denis Villeneuve",
        "categories": ["SF", "Aventure"],
        "synopsis": "Un noble héritier...",
        "tags": ["😌 Détente"],
        "review": "Excellent",
        "tmdb_ok": True,
        "cover_url": "http://example.com/dune.jpg",
    }))

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.title == "Dune"
    assert fetched.type == "Film"
    assert fetched.release_date == date(2021, 10, 22)
    assert fetched.categories == ["SF", "Aventure"]
    assert fetched.tags == ["😌 Détente"]
    assert fetched.tmdb_ok is True
    assert fetched.cover_url == "http://example.com/dune.jpg"


def test_fetch_all_returns_created_medias(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.create({"title": "Dune"}))
    asyncio.run(store.create({"title": "Arrival"}))

    all_medias = asyncio.run(store.fetch_all())
    assert {m.title for m in all_medias} == {"Dune", "Arrival"}


def test_fetch_one_returns_none_when_missing(tmp_path):
    store = _store(tmp_path)
    assert asyncio.run(store.fetch_one("unknown")) is None


def test_update_changes_only_given_fields(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "director": None}))

    ok = asyncio.run(store.update(media.id, {"director": "Denis Villeneuve", "tmdb_ok": True}))
    assert ok is True

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.director == "Denis Villeneuve"
    assert fetched.tmdb_ok is True
    assert fetched.title == "Dune"  # inchangé


def test_update_returns_false_for_unknown_id(tmp_path):
    store = _store(tmp_path)
    ok = asyncio.run(store.update("unknown", {"director": "X"}))
    assert ok is False


def test_delete_removes_media(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))

    ok = asyncio.run(store.delete(media.id))
    assert ok is True
    assert asyncio.run(store.fetch_one(media.id)) is None


def test_delete_returns_false_for_unknown_id(tmp_path):
    store = _store(tmp_path)
    ok = asyncio.run(store.delete("unknown"))
    assert ok is False


def test_update_silently_ignores_unknown_field_keys(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))

    # Update with unknown field keys mixed with valid ones
    ok = asyncio.run(store.update(media.id, {
        "not_a_real_column": "x",
        "title": "Dune Remastered",
        "also_invalid": 123,
        "director": "Denis Villeneuve"
    }))
    assert ok is True

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.title == "Dune Remastered"
    assert fetched.director == "Denis Villeneuve"
    # Unknown keys did not cause an error, they were silently ignored
