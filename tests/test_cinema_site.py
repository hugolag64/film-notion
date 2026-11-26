from datetime import date, datetime
from pathlib import Path

from backend.core.cinema_site import (
    FilmDetails,
    UpcomingFilm,
    parse_film_page,
    parse_french_date,
    parse_programme,
    parse_upcoming,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cinema"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_french_date():
    assert parse_french_date("mercredi 18 novembre 2026") == date(2026, 11, 18)
    assert parse_french_date("Mardi 1 décembre 2026") == date(2026, 12, 1)
    assert parse_french_date("1er août 2027") == date(2027, 8, 1)
    assert parse_french_date("bientôt") is None


def test_programme_lists_every_film_block():
    films = parse_programme(_read("programmation-grand-sud.html"))
    assert len(films) == 20
    camembert = next(f for f in films if f.site_id == 16263)
    assert camembert.title == "Camembert"
    assert camembert.url == "/film/camembert/16263/"
    assert camembert.showtimes


def test_programme_title_comes_from_poster_alt_without_format_suffix():
    films = parse_programme(_read("programmation-grand-sud.html"))
    avengers = next(f for f in films if f.site_id == 16259)
    assert avengers.title == "Avengers : Doomsday"


def test_programme_showtimes_have_time_version_and_booking_link():
    films = parse_programme(_read("programmation-grand-sud.html"))
    avengers = next(f for f in films if f.site_id == 16259)
    first = avengers.showtimes[0]
    assert first.starts_at == datetime(2026, 12, 16, 10, 0)
    assert first.version == "VF"
    assert first.booking_url.startswith("https://www.ticketingcine.com/EMS1278/")
    versions = {s.version for f in films for s in f.showtimes}
    assert "VOST" in versions


def test_programme_of_unrelated_html_is_empty():
    assert parse_programme("<html><body><p>Maintenance</p></body></html>") == []


def test_film_page_details():
    details = parse_film_page(_read("film-camembert.html"))
    assert details == FilmDetails(
        original_title="Camembert",
        directors=("Matthieu Rumani", "Nicolas Slomka"),
        release_national=date(2026, 11, 18),
        release_reunion=date(2026, 11, 18),
    )


def test_upcoming_films():
    films = parse_upcoming(_read("prochaines-sorties.html"))
    assert len(films) == 15
    assert UpcomingFilm(
        16238,
        "Astérix - Le Royaume de Nubie",
        "/film/asterix-le-royaume-de-nubie/16238/",
        "/images/movie/asterix-le-royaume-de-nubie-allocine-313265.jpg",
    ) in films
