import asyncio
from datetime import datetime, timezone

from backend.core.auth import AuthStore
from backend.core.models import DiaryEntry
from backend.core.recommendations import _rating_value
from backend.core.store import MediaStore
from backend.scripts.backfill_journal import apply_backfill, plan_backfill

PASSWORD = "Correct Horse Battery Staple"


def _stores(tmp_path):
    db = str(tmp_path / "backstage.db")
    media_store, auth_store = MediaStore(db), AuthStore(db)
    media_store.init_schema()
    auth_store.init_schema()
    admin = auth_store.create_admin("Hugo", "hugo@example.com", PASSWORD)
    paul = auth_store.create_user("Paul", "paul@example.com", PASSWORD)
    return media_store, auth_store, admin["id"], paul["id"]


def _film(store, media_id, tmdb_id, **fields):
    asyncio.run(store.create({"id": media_id, "title": media_id, "type": "Film", "tmdb_id": tmdb_id, **fields}))


def test_backfill_reads_user_states_and_owner_fallback(tmp_path):
    store, auth, hugo, paul = _stores(tmp_path)
    _film(store, "dune", 550, rating="4")
    _film(store, "heat", 949)
    _film(store, "sans-tmdb", None, rating="5")
    asyncio.run(store.upsert_user_media_state(paul, "heat", {"status": "A revoir"}))

    entries = asyncio.run(plan_backfill(store, auth))

    pairs = sorted((entry.backstage_user_id == hugo, entry.tmdb_id, entry.rating) for entry in entries)
    assert pairs == [(False, 949, None), (True, 550, 4.0)]
    assert all(entry.watched_on is None and entry.source == "backfill" for entry in entries)


def test_backfill_converts_and_keeps_unreadable_ratings(tmp_path):
    store, auth, hugo, paul = _stores(tmp_path)
    stars = "⭐️" * 7
    _film(store, "a", 1)
    _film(store, "b", 2)
    asyncio.run(store.upsert_user_media_state(paul, "a", {"rating": stars}))
    asyncio.run(store.upsert_user_media_state(paul, "b", {"rating": "top", "review": "Génial"}))

    entries = {entry.tmdb_id: entry for entry in asyncio.run(plan_backfill(store, auth))}

    assert entries[1].rating == round(_rating_value(stars) * 2) / 2 == 3.5
    assert entries[2].rating is None
    assert entries[2].review == "Génial\nNote d'origine : top"


def test_backfill_is_idempotent(tmp_path):
    store, auth, hugo, paul = _stores(tmp_path)
    _film(store, "dune", 550)
    asyncio.run(store.upsert_user_media_state(paul, "dune", {"status": "Terminé", "rating": "4.5"}))

    assert asyncio.run(apply_backfill(store, asyncio.run(plan_backfill(store, auth)))) == 1
    assert asyncio.run(plan_backfill(store, auth)) == []
    assert len(asyncio.run(store.list_diary_entries(paul))) == 1


def test_backfill_skips_films_already_in_journal(tmp_path):
    store, auth, hugo, paul = _stores(tmp_path)
    _film(store, "dune", 550)
    asyncio.run(store.upsert_user_media_state(paul, "dune", {"status": "Terminé"}))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_diary_entry(DiaryEntry(
        id="e", backstage_user_id=paul, tmdb_id=550, created_at=now, updated_at=now,
    )))

    assert asyncio.run(plan_backfill(store, auth)) == []


def test_backfill_second_admin_gets_no_fallback(tmp_path):
    store, auth, hugo, paul = _stores(tmp_path)
    auth.update_user(paul, {"role": "admin"})
    _film(store, "dune", 550, rating="4")

    entries = asyncio.run(plan_backfill(store, auth))

    assert [entry.backstage_user_id for entry in entries] == [hugo]


def test_backfill_caches_movie_from_library(tmp_path):
    store, auth, hugo, paul = _stores(tmp_path)
    _film(store, "dune", 550, rating="4", cover_url="https://img/d.jpg", release_date="2024-02-28",
          categories=["SF"])

    asyncio.run(apply_backfill(store, asyncio.run(plan_backfill(store, auth))))

    movie = asyncio.run(store.get_tmdb_movies([550]))[550]
    assert (movie["title"], movie["year"], movie["poster_url"], movie["genres"]) == (
        "dune", 2024, "https://img/d.jpg", ["SF"],
    )
