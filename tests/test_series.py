import asyncio
from unittest.mock import ANY

import pytest
from fastapi import HTTPException

from backend.api import UpdateEpisodeRequest, get_series_episodes, update_episode
from backend.core.store import MediaStore


def _store(tmp_path) -> MediaStore:
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    return store


@pytest.fixture
def store(tmp_path) -> MediaStore:
    return _store(tmp_path)


@pytest.fixture
def fake_tmdb():
    class FakeTMDB:
        async def search_tv(self, query):
            assert query == "Severance"
            return [{
                "id": 1,
                "title": "Severance",
                "release_date": "2022-02-18",
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
                "overview": "Des employés séparent leurs souvenirs professionnels et personnels.",
            }]

        async def get_tv_details(self, tmdb_id):
            assert tmdb_id == 1
            return {
                "name": "Severance",
                "original_name": "Severance",
                "first_air_date": "2022-02-18",
                "created_by": [{"name": "Dan Erickson"}],
                "genres": [{"name": "Drame"}, {"name": "Mystère"}],
                "overview": "Des employés séparent leurs souvenirs professionnels et personnels.",
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
                "credits": {"cast": [{"name": "Adam Scott"}]},
                "seasons": [
                    {"season_number": 0, "name": "Spéciales"},
                    {"season_number": 1, "name": "Saison 1"},
                ],
            }

        async def get_tv_season_details(self, tmdb_id, season_number):
            assert (tmdb_id, season_number) == (1, 1)
            return {
                "episodes": [
                    {"episode_number": 1, "name": "Good News About Hell"},
                    {"episode_number": 2, "name": "Half Loop"},
                ],
            }

        def get_director(self, details):
            return details["created_by"][0]["name"]

        def get_genres(self, details):
            return [genre["name"] for genre in details["genres"]]

        def get_poster_url(self, details):
            return f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

        def get_backdrop_url(self, details):
            return f"https://image.tmdb.org/t/p/w1280{details['backdrop_path']}"

        def get_cast(self, details, limit=5):
            return [member["name"] for member in details["credits"]["cast"][:limit]]

    return FakeTMDB()


def test_series_progress_is_computed_by_season(tmp_path):
    store = _store(tmp_path)
    series = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    asyncio.run(store.create_episodes(series.id, [{"season_number": 1, "episode_number": 1, "title": "Good News"}]))

    assert asyncio.run(store.series_progress(series.id))["status"] == "À regarder"


def test_episode_updates_recalculate_parent_status_and_season_counts(tmp_path):
    store = _store(tmp_path)
    series = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    episodes = asyncio.run(store.create_episodes(series.id, [
        {"season_number": 1, "episode_number": 1, "title": "Good News"},
        {"season_number": 1, "episode_number": 2, "title": "Half Loop"},
        {"season_number": 2, "episode_number": 1, "title": "Hello, Ms. Cobel"},
    ]))

    asyncio.run(store.set_episode_watched(episodes[0]["id"], True))

    progress = asyncio.run(store.series_progress(series.id))
    assert progress == {
        "media_id": series.id,
        "status": "En cours",
        "watched": 1,
        "total": 3,
        "percentage": 33.33,
        "seasons": [
            {"season_number": 1, "watched": 1, "total": 2, "percentage": 50.0},
            {"season_number": 2, "watched": 0, "total": 1, "percentage": 0.0},
        ],
    }
    assert asyncio.run(store.fetch_one(series.id)).status == "En cours"

    asyncio.run(store.set_episode_watched(episodes[1]["id"], True))
    asyncio.run(store.set_episode_watched(episodes[2]["id"], True))
    assert asyncio.run(store.series_progress(series.id))["status"] == "Terminée"
    assert asyncio.run(store.fetch_one(series.id)).status == "Terminée"


def test_episode_api_reads_progress_and_updates_episode(tmp_path):
    store = _store(tmp_path)
    series = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    episode = asyncio.run(store.create_episodes(series.id, [
        {"season_number": 1, "episode_number": 1, "title": "Good News", "synopsis": "Episode synopsis"},
    ]))[0]

    initial = asyncio.run(get_series_episodes(series.id, store))
    updated = asyncio.run(update_episode(episode["id"], UpdateEpisodeRequest(watched=True), store))

    assert initial["episodes"] == [episode]
    assert initial["progress"]["status"] == "À regarder"
    assert updated["episode"]["watched"] is True
    assert updated["episode"]["synopsis"] == "Episode synopsis"
    assert updated["progress"]["status"] == "Terminée"


def test_episode_operations_reject_films_without_changing_their_status(tmp_path):
    store = _store(tmp_path)
    film = asyncio.run(store.create({"title": "Dune", "type": "Film", "status": "Terminée"}))

    created = asyncio.run(store.create_episodes(film.id, [
        {"season_number": 1, "episode_number": 1, "title": "Part One"},
    ]))

    assert created == []
    assert asyncio.run(store.list_episodes(film.id)) == []
    assert asyncio.run(store.series_progress(film.id)) is None
    assert asyncio.run(store.fetch_one(film.id)).status == "Terminée"


def test_create_series_imports_unwatched_non_special_episodes(fake_tmdb, store):
    from backend.api import CreateFromTMDBRequest, create_series_from_tmdb

    created = asyncio.run(create_series_from_tmdb(
        CreateFromTMDBRequest(tmdb_id=1), store, fake_tmdb,
    ))

    assert created.type == "Série"
    assert created.title == "Severance"
    assert created.status == "À regarder"
    assert created.director == "Dan Erickson"
    assert created.categories == ["Drame", "Mystère"]
    assert asyncio.run(store.list_episodes(created.id)) == [
        {
            "id": ANY,
            "media_id": created.id,
            "season_number": 1,
            "episode_number": 1,
            "title": "Good News About Hell",
            "watched": False,
        },
        {
            "id": ANY,
            "media_id": created.id,
            "season_number": 1,
            "episode_number": 2,
            "title": "Half Loop",
            "watched": False,
        },
    ]


def test_search_series_uses_tv_results(fake_tmdb):
    from backend.api import search_tmdb_tv

    assert asyncio.run(search_tmdb_tv(" Severance ", fake_tmdb)) == [{
        "tmdb_id": 1,
        "title": "Severance",
        "release_date": "2022-02-18",
        "poster_url": "https://image.tmdb.org/t/p/w500/poster.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w1280/backdrop.jpg",
        "overview": "Des employés séparent leurs souvenirs professionnels et personnels.",
    }]


def test_create_series_aborts_without_persisting_when_a_season_is_unavailable(fake_tmdb, store):
    from backend.api import CreateFromTMDBRequest, create_series_from_tmdb

    async def missing_season_details(tmdb_id, season_number):
        assert (tmdb_id, season_number) == (1, 1)
        return None

    fake_tmdb.get_tv_season_details = missing_season_details

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_series_from_tmdb(
            CreateFromTMDBRequest(tmdb_id=1), store, fake_tmdb,
        ))

    assert exc_info.value.status_code == 502
    assert asyncio.run(store.fetch_all()) == []


def test_refresh_series_updates_tmdb_metadata_and_preserves_watched_episodes(fake_tmdb, store):
    from backend.api import CreateFromTMDBRequest, create_series_from_tmdb, refresh_series_from_tmdb

    created = asyncio.run(create_series_from_tmdb(
        CreateFromTMDBRequest(tmdb_id=1), store, fake_tmdb,
    ))
    first_episode = asyncio.run(store.list_episodes(created.id))[0]
    asyncio.run(store.set_episode_watched(first_episode["id"], True))

    async def refreshed_season(tmdb_id, season_number):
        return {"episodes": [
            {"episode_number": 1, "name": "Good News (updated)", "overview": "A refreshed synopsis."},
            {"episode_number": 2, "name": "Half Loop", "overview": "Episode two synopsis."},
            {"episode_number": 3, "name": "New episode", "overview": "A new episode."},
        ]}

    fake_tmdb.get_tv_season_details = refreshed_season
    refreshed = asyncio.run(refresh_series_from_tmdb(created.id, store, fake_tmdb))

    assert refreshed.original_title == "Severance"
    assert refreshed.tmdb_id == 1
    episodes = asyncio.run(store.list_episodes(created.id))
    assert [(episode["episode_number"], episode["watched"], episode.get("synopsis")) for episode in episodes] == [
        (1, True, "A refreshed synopsis."),
        (2, False, "Episode two synopsis."),
        (3, False, "A new episode."),
    ]


def test_refresh_series_links_legacy_series_and_adds_episode_synopses(fake_tmdb, store):
    from backend.api import refresh_series_from_tmdb

    legacy = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    asyncio.run(store.create_episodes(legacy.id, [
        {"season_number": 1, "episode_number": 1, "title": "Ancien titre"},
    ]))

    async def season_with_synopsis(tmdb_id, season_number):
        return {"episodes": [
            {"episode_number": 1, "name": "Nouveau titre", "overview": "Synopsis TMDB de l'épisode."},
        ]}

    fake_tmdb.get_tv_season_details = season_with_synopsis

    refreshed = asyncio.run(refresh_series_from_tmdb(legacy.id, store, fake_tmdb))

    assert refreshed.tmdb_id == 1
    assert asyncio.run(store.list_episodes(legacy.id))[0]["synopsis"] == "Synopsis TMDB de l'épisode."
