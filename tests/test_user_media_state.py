import asyncio

from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def test_user_media_state_isolated_between_users(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create({"id": "dune", "title": "Dune", "type": "Film"}))

    hugo = asyncio.run(store.upsert_user_media_state(
        "hugo", "dune", {"rating": "5", "status": "Terminé", "is_favorite": True},
    ))
    ophelie = asyncio.run(store.upsert_user_media_state(
        "ophelie", "dune", {"rating": "2", "status": "À regarder"},
    ))

    assert hugo.rating == "5"
    assert hugo.is_favorite is True
    assert ophelie.rating == "2"
    assert ophelie.is_favorite is False
    assert asyncio.run(store.get_user_media_state("missing", "dune")) is None


def test_user_media_state_tracks_watchlist_time(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create({"id": "film", "title": "Film", "type": "Film"}))

    state = asyncio.run(store.upsert_user_media_state("hugo", "film", {"status": "À regarder"}))

    assert state.added_to_watchlist_at is not None
    assert state.last_interacted_at is not None


def test_user_media_state_persists_watchlist_independently_from_status(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create({"id": "film", "title": "Film", "type": "Film"}))

    state = asyncio.run(store.upsert_user_media_state(
        "hugo", "film", {"status": "À regarder", "is_watchlist": True},
    ))

    assert state.status == "À regarder"
    assert state.is_watchlist is True
