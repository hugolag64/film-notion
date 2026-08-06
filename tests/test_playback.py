import asyncio

from backend.core.playback import PlaybackProgress
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def test_playback_is_persisted_separately_for_each_backstage_user(tmp_path):
    store = make_store(tmp_path)
    progress = PlaybackProgress(
        backstage_user_id="hugo",
        jellyfin_id="jf-dune",
        media_id="dune",
        title="Dune",
        position_ticks=50,
        runtime_ticks=100,
        percent=50,
    )

    asyncio.run(store.upsert_playback(progress))
    asyncio.run(store.upsert_playback(progress.model_copy(update={"backstage_user_id": "ophelie"})))

    assert len(asyncio.run(store.list_resume_progress("hugo"))) == 1
    assert len(asyncio.run(store.list_resume_progress("ophelie"))) == 1
    assert asyncio.run(store.list_resume_progress("missing")) == []


def test_completed_playback_is_not_resume_and_is_recently_completed(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.upsert_playback(PlaybackProgress(
        backstage_user_id="hugo", jellyfin_id="jf-dune", media_id="dune",
        title="Dune", percent=95, played=False,
    )))

    assert asyncio.run(store.list_resume_progress("hugo")) == []
    assert [item.title for item in asyncio.run(store.list_recently_completed("hugo"))] == ["Dune"]


def test_next_episode_uses_first_local_episode_not_completed(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create({"id": "series", "title": "Severance", "type": "Série"}))
    asyncio.run(store.create_episodes("series", [
        {"id": "ep-1", "season_number": 1, "episode_number": 1, "title": "Good News"},
        {"id": "ep-2", "season_number": 1, "episode_number": 2, "title": "Half Loop"},
    ]))
    asyncio.run(store.upsert_playback(PlaybackProgress(
        backstage_user_id="hugo", jellyfin_id="jf-ep-1", media_id="series", episode_id="ep-1",
        title="Good News", series_title="Severance", season_number=1, episode_number=1,
        percent=100, played=True,
    )))

    next_items = asyncio.run(store.list_next_episodes("hugo"))

    assert next_items[0]["episode_id"] == "ep-2"
    assert next_items[0]["episode_number"] == 2
