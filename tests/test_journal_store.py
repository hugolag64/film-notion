import asyncio
import time
import uuid
from datetime import date, datetime, timezone

from backend.core.models import DiaryEntry
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def _entry(user, tmdb_id, watched_on=None, rating=None, **extra):
    now = datetime.now(timezone.utc)
    return DiaryEntry(
        id=str(uuid.uuid4()),
        backstage_user_id=user,
        tmdb_id=tmdb_id,
        watched_on=watched_on,
        rating=rating,
        review=extra.pop("review", None),
        created_at=extra.pop("created_at", now),
        updated_at=now,
        **extra,
    )


def test_diary_entries_are_per_user_and_ordered(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create_diary_entry(_entry("hugo", 1, None)))
    asyncio.run(store.create_diary_entry(_entry("hugo", 2, date(2026, 11, 14))))
    asyncio.run(store.create_diary_entry(_entry("hugo", 3, date(2026, 11, 22))))
    asyncio.run(store.create_diary_entry(_entry("paul", 9, date(2026, 11, 1))))

    entries = asyncio.run(store.list_diary_entries("hugo"))

    assert [e.watched_on for e in entries] == [date(2026, 11, 22), date(2026, 11, 14), None]
    assert [e.tmdb_id for e in entries] == [3, 2, 1]
    assert asyncio.run(store.list_diary_tmdb_ids("paul")) == {9}


def test_latest_diary_entry_prefers_most_recent_watch(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create_diary_entry(_entry("hugo", 5, date(2026, 11, 1), 4.5)))
    asyncio.run(store.create_diary_entry(_entry("hugo", 5, date(2026, 1, 1), 3.0)))

    latest = asyncio.run(store.latest_diary_entry("hugo", 5))

    assert latest.rating == 4.5
    assert asyncio.run(store.latest_diary_entry("paul", 5)) is None


def test_update_and_delete_diary_entry(tmp_path):
    store = make_store(tmp_path)
    created = asyncio.run(store.create_diary_entry(_entry("hugo", 5, date(2026, 11, 1), 4.0)))
    time.sleep(0.01)

    updated = asyncio.run(store.update_diary_entry(created.id, {"rating": 2.0}))

    assert updated.rating == 2.0
    assert updated.updated_at > created.updated_at
    assert asyncio.run(store.delete_diary_entry(created.id)) is True
    assert asyncio.run(store.get_diary_entry(created.id)) is None
    assert asyncio.run(store.delete_diary_entry(created.id)) is False


def test_tmdb_cache_roundtrip(tmp_path):
    store = make_store(tmp_path)
    movie = {
        "tmdb_id": 550, "title": "Dune 2", "year": 2024, "release_date": "2024-02-28",
        "poster_url": "https://img/d.jpg", "genres": ["SF"],
    }
    asyncio.run(store.upsert_tmdb_movie(movie))

    cached = asyncio.run(store.get_tmdb_movies([550, 999]))

    assert list(cached) == [550]
    assert cached[550]["genres"] == ["SF"]
    assert cached[550]["title"] == "Dune 2"

    asyncio.run(store.upsert_tmdb_movie({**movie, "title": "Dune : Deuxième partie"}))
    assert asyncio.run(store.get_tmdb_movies([550]))[550]["title"] == "Dune : Deuxième partie"


def test_film_list_items_unique_and_cascade(tmp_path):
    store = make_store(tmp_path)
    film_list = asyncio.run(store.create_film_list("Films à voir au ciné", "hugo"))

    assert asyncio.run(store.add_film_list_item(film_list.id, 550, "hugo")) is True
    assert asyncio.run(store.add_film_list_item(film_list.id, 550, "paul")) is False

    lists = asyncio.run(store.list_film_lists())
    assert lists[0]["item_count"] == 1
    assert lists[0]["name"] == "Films à voir au ciné"
    items = asyncio.run(store.list_film_list_items(film_list.id))
    assert [(i.tmdb_id, i.added_by) for i in items] == [(550, "hugo")]

    assert asyncio.run(store.delete_film_list(film_list.id)) is True
    assert asyncio.run(store.get_film_list(film_list.id)) is None
    assert asyncio.run(store.list_film_list_items(film_list.id)) == []


def test_diary_does_not_touch_media_table(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create_diary_entry(_entry("hugo", 5, date(2026, 11, 1), 4.0)))
    film_list = asyncio.run(store.create_film_list("Ciné", "hugo"))
    asyncio.run(store.add_film_list_item(film_list.id, 5, "hugo"))

    assert asyncio.run(store.fetch_all()) == []
