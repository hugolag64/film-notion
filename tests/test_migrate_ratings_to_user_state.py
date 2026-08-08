import asyncio

from backend.core.store import MediaStore
from backend.scripts.migrate_ratings_to_user_state import migrate_ratings_to_user_state


def _store(tmp_path) -> MediaStore:
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def _create(store, **overrides):
    fields = {
        "title": "Film", "type": "Film", "status": "À regarder", "rating": None,
    }
    fields.update(overrides)
    return asyncio.run(store.create(fields))


def test_dry_run_reports_without_writing(tmp_path):
    store = _store(tmp_path)
    media = _create(store, rating="4.5")

    summary = asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=False))

    assert summary == {"migrated": 1, "watchlisted": 0, "skipped": 0}
    assert asyncio.run(store.get_user_media_state("user-1", media.id)) is None


def test_apply_writes_rating_into_user_media_state(tmp_path):
    store = _store(tmp_path)
    media = _create(store, rating="4.5")

    asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))

    state = asyncio.run(store.get_user_media_state("user-1", media.id))
    assert state.rating == "4.5"


def test_star_rating_string_is_carried_over_unchanged(tmp_path):
    store = _store(tmp_path)
    media = _create(store, rating="⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️")

    asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))

    state = asyncio.run(store.get_user_media_state("user-1", media.id))
    assert state.rating == "⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️"


def test_a_revoir_status_is_migrated_without_a_rating(tmp_path):
    store = _store(tmp_path)
    media = _create(store, status="A revoir", rating=None)

    asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))

    state = asyncio.run(store.get_user_media_state("user-1", media.id))
    assert state.status == "A revoir"


def test_legacy_watchlist_status_sets_is_watchlist(tmp_path):
    store = _store(tmp_path)
    media = _create(store, status="watchlist", rating=None)

    summary = asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))

    state = asyncio.run(store.get_user_media_state("user-1", media.id))
    assert state.is_watchlist is True
    assert summary["watchlisted"] == 1


def test_a_regarder_with_no_rating_is_skipped(tmp_path):
    store = _store(tmp_path)
    media = _create(store, status="À regarder", rating=None)

    summary = asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))

    assert summary == {"migrated": 0, "watchlisted": 0, "skipped": 1}
    assert asyncio.run(store.get_user_media_state("user-1", media.id)) is None


def test_migration_is_idempotent_and_does_not_clobber_favorite(tmp_path):
    store = _store(tmp_path)
    media = _create(store, rating="4")
    asyncio.run(store.upsert_user_media_state("user-1", media.id, {"is_favorite": True}))

    asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))
    asyncio.run(migrate_ratings_to_user_state(store, "user-1", apply=True))

    state = asyncio.run(store.get_user_media_state("user-1", media.id))
    assert state.rating == "4"
    assert state.is_favorite is True
