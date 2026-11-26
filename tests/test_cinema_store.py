import asyncio
from datetime import date, datetime

import pytest

from backend.core.cinema_site import FilmDetails, Showtime
from backend.core.cinema_store import CinemaStore
from backend.core.store import MediaStore


@pytest.fixture
def media_store(tmp_path):
    store = MediaStore(str(tmp_path / "cinema.db"))
    store.init_schema()
    return store


@pytest.fixture
def cinema(media_store):
    return CinemaStore(media_store.db_path)


def _show(day, hour, version="VF"):
    return Showtime(datetime(2026, 11, day, hour, 0), version, f"https://example.test/{day}-{hour}")


def test_replace_showtimes_swaps_the_whole_set(cinema):
    asyncio.run(cinema.replace_showtimes({1: [_show(26, 20), _show(27, 20)]}))
    asyncio.run(cinema.replace_showtimes({2: [_show(28, 18, "VOST")]}))

    listed = asyncio.run(cinema.list_showtimes(datetime(2026, 1, 1)))

    assert listed == [{
        "site_id": 2,
        "starts_at": datetime(2026, 11, 28, 18, 0),
        "version": "VOST",
        "booking_url": "https://example.test/28-18",
    }]


def test_list_showtimes_filters_by_window(cinema):
    asyncio.run(cinema.replace_showtimes({
        1: [_show(28, 20), _show(26, 20)],
        2: [_show(27, 14), _show(29, 10)],
    }))

    listed = asyncio.run(cinema.list_showtimes(datetime(2026, 11, 26, 20), datetime(2026, 11, 29, 10)))

    assert [(s["site_id"], s["starts_at"]) for s in listed] == [
        (1, datetime(2026, 11, 26, 20)),
        (2, datetime(2026, 11, 27, 14)),
        (1, datetime(2026, 11, 28, 20)),
    ]


def test_upsert_site_film_keeps_details_and_match(cinema):
    now = datetime(2026, 11, 26, 9, 0)
    asyncio.run(cinema.upsert_site_film(1, "Camembert", "/film/camembert/1/", "/images/c.jpg"))
    details = FilmDetails("Camembert", ("Matthieu Rumani", "Nicolas Slomka"), date(2026, 11, 18), date(2026, 11, 18))
    asyncio.run(cinema.set_film_details(1, details, now))
    asyncio.run(cinema.set_tmdb_match(1, 777, now))

    asyncio.run(cinema.upsert_site_film(1, "Camembert (VF)", "/film/camembert/1/", None))

    film = asyncio.run(cinema.get_site_films())[1]
    assert film["title"] == "Camembert (VF)"
    assert film["original_title"] == "Camembert"
    assert film["directors"] == ["Matthieu Rumani", "Nicolas Slomka"]
    assert film["release_national"] == "2026-11-18"
    assert film["release_reunion"] == "2026-11-18"
    assert film["tmdb_id"] == 777
    assert film["match_attempted_at"] == now
    assert film["details_fetched_at"] == now


def test_unmatched_film_keeps_its_attempt_date(cinema):
    now = datetime(2026, 11, 26, 9, 0)
    asyncio.run(cinema.upsert_site_film(2, "Inconnu", "/film/inconnu/2/", None))
    asyncio.run(cinema.set_tmdb_match(2, None, now))

    film = asyncio.run(cinema.get_site_films())[2]
    assert film["tmdb_id"] is None
    assert film["match_attempted_at"] == now
    assert film["details_fetched_at"] is None
    assert film["directors"] == []


def test_reminders_are_recorded_once(cinema):
    now = datetime(2026, 11, 26, 9, 0)
    asyncio.run(cinema.record_reminder(1, "arrivee", now))
    asyncio.run(cinema.record_reminder(1, "arrivee", now))

    assert asyncio.run(cinema.sent_reminders()) == {(1, "arrivee")}


def test_status_tracks_success_and_failure(cinema):
    assert asyncio.run(cinema.get_status()) == {"last_success_at": None, "last_error": None, "last_error_at": None}
    ok = datetime(2026, 11, 26, 9, 0)
    asyncio.run(cinema.record_success(ok))
    failed = datetime(2026, 11, 27, 9, 0)
    asyncio.run(cinema.record_failure(failed, "Site injoignable"))

    assert asyncio.run(cinema.get_status()) == {
        "last_success_at": ok,
        "last_error": "Site injoignable",
        "last_error_at": failed,
    }


def test_tracked_ids_come_from_shared_lists(cinema, media_store):
    first = asyncio.run(media_store.create_film_list("Ciné", "hugo"))
    second = asyncio.run(media_store.create_film_list("Plus tard", "lea"))
    asyncio.run(media_store.add_film_list_item(first.id, 550, "hugo"))
    asyncio.run(media_store.add_film_list_item(second.id, 550, "lea"))
    asyncio.run(media_store.add_film_list_item(second.id, 551, "lea"))

    assert asyncio.run(cinema.tracked_tmdb_ids()) == {550, 551}


def test_calendar_token_roundtrip_and_regeneration(cinema):
    asyncio.run(cinema.set_calendar_token("hugo", "a"))
    assert asyncio.run(cinema.calendar_token_for("hugo")) == "a"
    assert asyncio.run(cinema.user_for_calendar_token("a")) == "hugo"

    asyncio.run(cinema.set_calendar_token("hugo", "b"))

    assert asyncio.run(cinema.user_for_calendar_token("a")) is None
    assert asyncio.run(cinema.user_for_calendar_token("b")) == "hugo"
    assert asyncio.run(cinema.calendar_token_for("lea")) is None
