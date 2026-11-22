import asyncio
from unittest.mock import ANY

import pytest
from fastapi import HTTPException

from backend.api import UpdateEpisodeRequest, get_series_episodes, update_episode
from backend.auth_api import AuthContext
from backend.core.store import MediaStore
from backend.core.media_server import Availability


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
    series = asyncio.run(store.create({"title": "Severance", "type": "SÃ©rie"}))
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

    assert initial["episodes"] == [{**episode, "available": False, "upcoming": False, "percent": 0}]
    assert initial["next_episode"]["mode"] == "start"
    assert initial["progress"]["status"] == "À regarder"
    assert updated["episode"]["watched"] is True
    assert updated["episode"]["synopsis"] == "Episode synopsis"
    assert updated["progress"]["status"] == "Terminée"


def test_episode_progress_is_scoped_per_user(tmp_path):
    store = _store(tmp_path)
    series = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    episode = asyncio.run(store.create_episodes(series.id, [
        {"season_number": 1, "episode_number": 1, "title": "Good News"},
    ]))[0]
    user_a = AuthContext(user={"id": "user-a", "role": "user"}, session_id="s-a", token="t-a")
    user_b = AuthContext(user={"id": "user-b", "role": "user"}, session_id="s-b", token="t-b")

    updated = asyncio.run(update_episode(
        episode["id"], UpdateEpisodeRequest(watched=True), store, user_a,
    ))
    other_user = asyncio.run(get_series_episodes(series.id, store, user_b))

    assert updated["episode"]["watched"] is True
    assert updated["progress"]["percentage"] == 100.0
    assert other_user["episodes"][0]["watched"] is False
    assert other_user["progress"]["percentage"] == 0
    assert asyncio.run(store.list_episodes(series.id))[0]["watched"] is False


def test_episode_api_marks_only_jellyfin_present_episodes_as_playable(tmp_path):
    store = _store(tmp_path)
    series = asyncio.run(store.create({"id": "simpsons", "title": "The Simpsons", "type": "Série"}))
    episodes = asyncio.run(store.create_episodes(series.id, [
        {"season_number": 1, "episode_number": 1, "title": "Noël mortel"},
        {"season_number": 1, "episode_number": 2, "title": "Bart le génie"},
    ]))
    asyncio.run(store.upsert_availability(Availability(
        media_id=series.id, provider="sonarr", jellyfin_id="jelly-simpsons", state="available",
    )))

    class FakeJellyfin:
        async def list_series_episodes(self, series_id):
            assert series_id == "jelly-simpsons"
            return [{"ParentIndexNumber": 1, "IndexNumber": 2, "Id": "jf-episode-2"}]

    result = asyncio.run(get_series_episodes(series.id, store, jellyfin=FakeJellyfin()))

    assert [episode["available"] for episode in result["episodes"]] == [False, True]


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
            "air_date": None,
            "runtime": None,
            "still_url": None,
        },
        {
            "id": ANY,
            "media_id": created.id,
            "season_number": 1,
            "episode_number": 2,
            "title": "Half Loop",
            "watched": False,
            "air_date": None,
            "runtime": None,
            "still_url": None,
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


class _EpisodeTMDB:
    """TMDB double that knows one series with a single regular season."""

    def __init__(self):
        self.detail_calls = 0

    async def get_tv_details(self, tmdb_id):
        self.detail_calls += 1
        assert tmdb_id == 1411
        return {"seasons": [{"season_number": 0}, {"season_number": 1}]}

    async def get_tv_season_details(self, tmdb_id, season_number):
        assert season_number == 1
        return {"episodes": [
            {"episode_number": 1, "name": "Pilote", "overview": "La Machine."},
            {"episode_number": 2, "name": "Ghosts"},
        ]}


def test_episode_api_loads_missing_episodes_for_synced_series(tmp_path, monkeypatch):
    import backend.api as api_module

    store = _store(tmp_path)
    series = asyncio.run(store.create({
        "id": "poi", "title": "Person of Interest", "type": "Série", "tmdb_id": 1411,
    }))
    tmdb = _EpisodeTMDB()
    monkeypatch.setattr(api_module, "_optional_tmdb_client", lambda: tmdb)

    result = asyncio.run(get_series_episodes(series.id, store))
    again = asyncio.run(get_series_episodes(series.id, store))

    assert [(e["season_number"], e["episode_number"]) for e in result["episodes"]] == [(1, 1), (1, 2)]
    assert result["progress"]["total"] == 2
    assert len(again["episodes"]) == 2
    assert tmdb.detail_calls == 1


def test_episode_api_without_tmdb_returns_empty_list(tmp_path, monkeypatch):
    import backend.api as api_module

    store = _store(tmp_path)
    series = asyncio.run(store.create({"id": "poi", "title": "POI", "type": "Série", "tmdb_id": 1411}))
    monkeypatch.setattr(api_module, "_optional_tmdb_client", lambda: None)

    assert asyncio.run(get_series_episodes(series.id, store))["episodes"] == []


def _view_episode(number, watched=False, available=True, air_date="2020-01-01", runtime=40, season=1):
    return {
        "id": f"s{season}e{number}", "media_id": "m", "season_number": season, "episode_number": number,
        "title": f"Épisode {number}", "watched": watched, "available": available,
        "air_date": air_date, "runtime": runtime, "still_url": None,
    }


def test_series_view_points_to_the_episode_after_the_last_watched():
    from backend.core.series_episodes import build_series_view

    episodes = [_view_episode(1, watched=True), _view_episode(2), _view_episode(3, watched=True), _view_episode(4)]
    view = build_series_view(episodes, {"seasons": [], "info": None}, {}, has_server=True, today="2026-11-22")

    assert view["next_episode"]["episode_number"] == 4
    assert view["next_episode"]["mode"] == "next"
    assert view["stats"]["watched"] == 2
    assert view["stats"]["remaining_minutes"] == 80


def test_series_view_resumes_a_started_episode_first():
    from backend.core.series_episodes import build_series_view

    episodes = [_view_episode(1, watched=True), _view_episode(2), _view_episode(3)]
    playback = {(1, 3): {"percent": 42.0, "played": 0, "last_played_at": "2026-11-20T20:00:00+00:00"}}
    view = build_series_view(episodes, {"seasons": [], "info": None}, playback, has_server=True, today="2026-11-22")

    assert view["next_episode"]["episode_number"] == 3
    assert view["next_episode"]["mode"] == "resume"
    assert view["next_episode"]["percent"] == 42.0


def test_series_view_summarises_season_availability_and_upcoming_episodes():
    from backend.core.series_episodes import build_series_view

    episodes = [
        _view_episode(1, season=1), _view_episode(2, season=1),
        _view_episode(1, season=2), _view_episode(2, season=2, available=False),
        _view_episode(3, season=2, available=False, air_date="2027-01-01"),
        _view_episode(1, season=3, available=False),
    ]
    metadata = {"seasons": [{"season_number": 2, "name": "Saison deux", "poster_url": "p.jpg"}], "info": None}
    view = build_series_view(episodes, metadata, {}, has_server=True, today="2026-11-22")

    seasons = {season["season_number"]: season for season in view["seasons"]}
    assert seasons[1]["availability"] == "complete"
    assert seasons[2]["availability"] == "partial"
    assert seasons[2]["name"] == "Saison deux"
    assert seasons[2]["aired"] == 2
    assert seasons[3]["availability"] == "missing"
    assert view["stats"]["upcoming"] == 1
    assert view["stats"]["available"] == 3
    assert [e["upcoming"] for e in view["episodes"] if e["season_number"] == 2] == [False, False, True]


def test_series_view_without_server_hides_availability():
    from backend.core.series_episodes import build_series_view

    view = build_series_view([_view_episode(1, available=False)], {"seasons": [], "info": None}, {},
                             has_server=False, today="2026-11-22")

    assert view["seasons"][0]["availability"] is None
    assert view["stats"]["available"] is None


def test_season_watched_endpoint_marks_every_episode_for_the_user(tmp_path):
    from backend.api import UpdateSeasonRequest, update_season_watched

    store = _store(tmp_path)
    series = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    asyncio.run(store.create_episodes(series.id, [
        {"season_number": 1, "episode_number": 1, "title": "A"},
        {"season_number": 1, "episode_number": 2, "title": "B"},
        {"season_number": 2, "episode_number": 1, "title": "C"},
    ]))
    user = AuthContext(user={"id": "user-a", "role": "user"}, session_id="s", token="t")

    result = asyncio.run(update_season_watched(series.id, 1, UpdateSeasonRequest(watched=True), store, user, None))

    assert [e["watched"] for e in result["episodes"]] == [True, True, False]
    assert result["next_episode"]["season_number"] == 2


def test_tmdb_series_loader_keeps_air_dates_runtimes_and_season_facts():
    from backend.core.series_episodes import fetch_tmdb_series

    class TMDB:
        async def get_tv_details(self, tmdb_id):
            return {"status": "Returning Series", "vote_average": 8.4, "first_air_date": "2022-02-18",
                    "next_episode_to_air": {"air_date": "2027-01-10", "season_number": 3, "episode_number": 1},
                    "seasons": [{"season_number": 0}, {"season_number": 1, "name": "Saison 1"}]}

        async def get_tv_season_details(self, tmdb_id, season_number):
            return {"name": "Saison 1", "poster_path": "/s1.jpg", "air_date": "2022-02-18", "episodes": [
                {"episode_number": 1, "name": "Pilote", "air_date": "2022-02-18", "runtime": 57, "still_path": "/e1.jpg"},
            ]}

    series = asyncio.run(fetch_tmdb_series(TMDB(), 95396))

    assert series["episodes"][0]["runtime"] == 57
    assert series["episodes"][0]["still_url"] == "https://image.tmdb.org/t/p/w300/e1.jpg"
    assert series["seasons"] == [{"season_number": 1, "name": "Saison 1", "overview": None,
                                  "poster_url": "https://image.tmdb.org/t/p/w342/s1.jpg", "air_date": "2022-02-18"}]
    assert series["info"]["tmdb_status"] == "Returning Series"
    assert series["info"]["next_air_date"] == "2027-01-10"


class _RentService:
    """Media server double recording granular series requests."""

    def __init__(self, store, on_server=frozenset()):
        self.store, self.on_server, self.calls = store, set(on_server), []

    async def add(self, media, quality, root, language, monitor, seasons=None, episodes=None):
        self.calls.append({"seasons": seasons, "episodes": episodes})
        return await self.store.upsert_availability(Availability(media_id=media.id, provider="sonarr", state="requested"))

    async def seasons_on_server(self, media, jellyfin_id):
        return self.on_server

    async def storage_status(self):
        return {}


def _poi(store):
    return asyncio.run(store.create({"id": "poi", "title": "POI", "type": "Série", "tmdb_id": 1411}))


def test_flatmate_rents_one_season(tmp_path):
    from backend.api import AcquisitionRequest, _acquire_media

    store = _store(tmp_path)
    media = _poi(store)
    service = _RentService(store)
    user = AuthContext(user={"id": "paul", "role": "user"}, session_id="s", token="t")

    result = asyncio.run(_acquire_media(media, AcquisitionRequest(seasons=[2]), user, service))
    again = asyncio.run(_acquire_media(media, AcquisitionRequest(seasons=[2]), user, service))

    assert service.calls == [{"seasons": [2], "episodes": None}]
    assert result["rental"]["rental_scope"] == "season"
    assert result["rental"]["season_number"] == 2
    assert again["rental"]["id"] == result["rental"]["id"]


def test_flatmate_cannot_rent_several_seasons_or_episodes(tmp_path):
    from backend.api import AcquisitionRequest, EpisodeRef, _acquire_media

    store = _store(tmp_path)
    media = _poi(store)
    user = AuthContext(user={"id": "paul", "role": "user"}, session_id="s", token="t")

    for payload in (AcquisitionRequest(seasons=[1, 2]),
                    AcquisitionRequest(episodes=[EpisodeRef(season_number=1, episode_number=1)]),
                    AcquisitionRequest()):
        with pytest.raises(HTTPException) as error:
            asyncio.run(_acquire_media(media, payload, user, _RentService(store)))
        assert error.value.status_code == 403


def test_flatmate_gets_no_rental_for_a_season_already_on_the_server(tmp_path):
    from backend.api import AcquisitionRequest, _acquire_media

    store = _store(tmp_path)
    media = _poi(store)
    asyncio.run(store.upsert_availability(Availability(media_id="poi", provider="sonarr", jellyfin_id="jf", state="available")))
    service = _RentService(store, on_server={1})
    user = AuthContext(user={"id": "paul", "role": "user"}, session_id="s", token="t")

    result = asyncio.run(_acquire_media(media, AcquisitionRequest(seasons=[1]), user, service))

    assert result["season_available"] is True
    assert service.calls == []


def test_admin_downloads_an_episode_without_rental(tmp_path):
    from backend.api import AcquisitionRequest, EpisodeRef, _acquire_media

    store = _store(tmp_path)
    media = _poi(store)
    service = _RentService(store)
    admin = AuthContext(user={"id": "admin", "role": "admin"}, session_id="s", token="t")

    result = asyncio.run(_acquire_media(
        media, AcquisitionRequest(episodes=[EpisodeRef(season_number=3, episode_number=7)]), admin, service,
    ))

    assert service.calls == [{"seasons": None, "episodes": [(3, 7)]}]
    assert "rental" not in result
