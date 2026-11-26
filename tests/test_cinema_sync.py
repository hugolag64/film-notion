import asyncio
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.core.cinema_site import FilmDetails, GRAND_SUD_PATH, UPCOMING_PATH
from backend.core.cinema_store import CinemaStore
from backend.core.cinema_sync import (
    BOT_ID,
    day_label,
    match_tmdb,
    refresh_cinema,
    refresh_tracked_release_dates,
)
from backend.core.store import MediaStore

FIXTURES = Path(__file__).parent / "fixtures" / "cinema"
NOW = datetime(2026, 11, 26, 9, 0)
CAMEMBERT = 16263


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    def __init__(self):
        self.programme = _read("programmation-grand-sud.html")
        self.fail = False

    async def __call__(self, path):
        if self.fail:
            raise RuntimeError("Site injoignable")
        if path == GRAND_SUD_PATH:
            return self.programme
        if path == UPCOMING_PATH:
            return _read("prochaines-sorties.html")
        if path == "/film/camembert/16263/":
            return _read("film-camembert.html")
        return "<html><body></body></html>"


class FakeTMDB:
    def __init__(self):
        self.searches = []
        self.results = {"Camembert": [{"id": 777, "title": "Camembert", "release_date": "2026-11-18"}]}
        self.details = {
            777: {"id": 777, "title": "Camembert", "release_date": "2026-11-18",
                  "credits": {"crew": [{"job": "Director", "name": "Nicolas Slomka"}]}},
        }

    async def search_movie(self, query, year=None):
        self.searches.append((query, year))
        return list(self.results.get(query, []))

    async def get_movie_details(self, tmdb_id):
        return self.details.get(tmdb_id)

    def get_director(self, details):
        for member in (details or {}).get("credits", {}).get("crew", []):
            if member.get("job") == "Director":
                return member.get("name")
        return None

    @staticmethod
    def poster_url_from_path(poster_path, size="w500"):
        return f"https://img{poster_path}" if poster_path else None

    def get_genres(self, details):
        return [g.get("name") for g in details.get("genres", [])]


@pytest.fixture
def stores(tmp_path):
    store = MediaStore(str(tmp_path / "sync.db"))
    store.init_schema()
    return store, CinemaStore(store.db_path)


def _bot_messages(store):
    return [m for m in asyncio.run(store.list_chat_messages()) if m["author"]["id"] == BOT_ID]


def _track(store, tmdb_id):
    film_list = asyncio.run(store.create_film_list("Ciné", "hugo"))
    asyncio.run(store.add_film_list_item(film_list.id, tmdb_id, "hugo"))


def test_day_label():
    assert day_label(date(2026, 12, 2)) == "mercredi 2/12"
    assert day_label(date(2026, 11, 29)) == "dimanche 29/11"


def test_refresh_stores_films_and_showtimes(stores):
    store, cinema = stores

    result = asyncio.run(refresh_cinema(store, cinema, FakeTMDB(), FakeFetcher(), NOW))

    assert result["ok"] is True and result["films"] >= 20
    assert asyncio.run(cinema.list_showtimes(NOW))
    assert asyncio.run(cinema.get_status())["last_success_at"] == NOW
    films = asyncio.run(cinema.get_site_films())
    assert films[CAMEMBERT]["tmdb_id"] == 777
    assert films[CAMEMBERT]["release_reunion"] == "2026-11-18"
    assert 16238 in films  # prochaines sorties aussi


def test_film_tracked_before_first_run_is_recorded_silently(stores):
    store, cinema = stores
    _track(store, 777)

    result = asyncio.run(refresh_cinema(store, cinema, FakeTMDB(), FakeFetcher(), NOW))

    assert result["posted"] == 0
    assert _bot_messages(store) == []
    assert (CAMEMBERT, "arrivee") in asyncio.run(cinema.sent_reminders())


def test_new_tracked_film_is_announced_after_first_run(stores):
    store, cinema = stores
    fetch, tmdb = FakeFetcher(), FakeTMDB()
    asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, NOW))
    _track(store, 777)

    result = asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, NOW + timedelta(hours=1)))

    assert result["posted"] == 1
    [message] = _bot_messages(store)
    assert message["body"] == "🎬 Camembert arrive au Grand Sud : première séance jeudi 26/11 à 13:30."
    assert message["author"]["display_name"] == "Ciné"
    assert message["payload"] == {
        "type": "cine_films",
        "films": [{"site_id": CAMEMBERT, "title": "Camembert", "tracked": True}],
    }
    asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, NOW + timedelta(hours=2)))
    assert len(_bot_messages(store)) == 1


def test_failed_programme_keeps_previous_showtimes(stores):
    store, cinema = stores
    fetch = FakeFetcher()
    asyncio.run(refresh_cinema(store, cinema, FakeTMDB(), fetch, NOW))
    before = asyncio.run(cinema.list_showtimes(NOW))

    fetch.fail = True
    failed = asyncio.run(refresh_cinema(store, cinema, FakeTMDB(), fetch, NOW + timedelta(days=1)))
    fetch.fail = False
    fetch.programme = "<html></html>"
    empty = asyncio.run(refresh_cinema(store, cinema, FakeTMDB(), fetch, NOW + timedelta(days=2)))

    assert failed["ok"] is False and empty["ok"] is False
    assert asyncio.run(cinema.list_showtimes(NOW)) == before
    status = asyncio.run(cinema.get_status())
    assert status["last_success_at"] == NOW
    assert status["last_error"]
    assert status["last_error_at"] == NOW + timedelta(days=2)


def test_unmatched_film_is_retried_after_a_week(stores):
    store, cinema = stores
    tmdb, fetch = FakeTMDB(), FakeFetcher()
    tmdb.results = {}
    asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, NOW))
    assert asyncio.run(cinema.get_site_films())[CAMEMBERT]["tmdb_id"] is None
    camembert_searches = lambda: [s for s in tmdb.searches if s[0] == "Camembert"]
    count = len(camembert_searches())
    assert count >= 1

    asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, NOW + timedelta(days=1)))
    assert len(camembert_searches()) == count

    asyncio.run(refresh_cinema(store, cinema, tmdb, fetch, NOW + timedelta(days=8)))
    assert len(camembert_searches()) > count


def test_match_prefers_matching_director():
    tmdb = FakeTMDB()
    tmdb.results = {"Camembert": [
        {"id": 1, "title": "Camembert", "release_date": "2026-03-01"},
        {"id": 2, "title": "Camembert", "release_date": "2026-11-18"},
    ]}
    tmdb.details = {
        1: {"credits": {"crew": [{"job": "Director", "name": "Quelqu'un"}]}},
        2: {"credits": {"crew": [{"job": "Director", "name": "Nicolas Slomka"}]}},
    }
    details = FilmDetails("Camembert", ("Matthieu Rumani", "Nicolas Slomka"), date(2026, 11, 18), None)

    assert asyncio.run(match_tmdb(tmdb, "Camembert", details)) == 2


def test_match_falls_back_to_first_result_of_the_right_year():
    tmdb = FakeTMDB()
    tmdb.results = {"Camembert": [
        {"id": 1, "title": "Camembert", "release_date": "1990-03-01"},
        {"id": 2, "title": "Camembert", "release_date": "2027-01-10"},
    ]}
    tmdb.details = {}
    details = FilmDetails(None, (), date(2026, 11, 18), None)

    assert asyncio.run(match_tmdb(tmdb, "Camembert", details)) == 2
    tmdb.results = {"Camembert": [{"id": 1, "title": "Camembert", "release_date": "1990-03-01"}]}
    assert asyncio.run(match_tmdb(tmdb, "Camembert", details)) is None


def test_tracked_release_dates_are_refreshed(stores):
    store, cinema = stores
    asyncio.run(store.upsert_tmdb_movie({"tmdb_id": 777, "title": "Camembert", "genres": []}))
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE tmdb_movie_cache SET fetched_at = ? WHERE tmdb_id = 777", (old,))
    _track(store, 777)
    tmdb = FakeTMDB()
    tmdb.details[777]["release_dates"] = {"results": [
        {"iso_3166_1": "FR", "release_dates": [{"type": 3, "release_date": "2026-11-18T00:00:00.000Z"}]},
    ]}

    refreshed = asyncio.run(refresh_tracked_release_dates(store, cinema, tmdb, date(2026, 11, 26)))

    assert refreshed == 1
    assert asyncio.run(store.get_tmdb_movies([777]))[777]["fr_release_date"] == "2026-11-18"
    assert asyncio.run(refresh_tracked_release_dates(store, cinema, tmdb, date(2026, 11, 26))) == 0
