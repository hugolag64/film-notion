import asyncio
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import health_router, router as media_router
from backend.auth_api import auth_router
from backend.cinema_api import calendar_events, calendar_feed_router, cinema_router
from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.cinema_site import FilmDetails
from backend.core.cinema_store import CinemaStore
from backend.core.store import MediaStore
from tests.test_auth_api import _setup

TODAY = date(2026, 11, 26)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "backstage.db"
    MediaStore(str(db)).init_schema()
    AuthStore(str(db)).init_schema()
    monkeypatch.setattr(Config, "DB_PATH", str(db))
    monkeypatch.setattr(Config, "BACKSTAGE_PUBLIC_URL", "https://backstage.test/")
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(media_router)
    app.include_router(cinema_router)
    app.include_router(calendar_feed_router)
    test_client = TestClient(app)
    _setup(test_client)
    return test_client


def _stores():
    store = MediaStore(Config.DB_PATH)
    return store, CinemaStore(Config.DB_PATH)


def _track(store, tmdb_id, title, fr_release_date):
    asyncio.run(store.upsert_tmdb_movie({
        "tmdb_id": tmdb_id, "title": title, "genres": [], "fr_release_date": fr_release_date,
    }))
    film_list = asyncio.run(store.create_film_list(f"Liste {tmdb_id}", "hugo"))
    asyncio.run(store.add_film_list_item(film_list.id, tmdb_id, "hugo"))


def _link_site_film(cinema, site_id, tmdb_id, reunion):
    asyncio.run(cinema.upsert_site_film(site_id, "Dune", f"/film/dune/{site_id}/", None))
    asyncio.run(cinema.set_film_details(site_id, FilmDetails("Dune", (), None, reunion), datetime(2026, 11, 26)))
    asyncio.run(cinema.set_tmdb_match(site_id, tmdb_id, datetime(2026, 11, 26)))


def test_feed_uses_reunion_date_then_french_date(client):
    store, cinema = _stores()
    _track(store, 550, "Dune 3", "2026-12-20")

    events = asyncio.run(calendar_events(store, cinema, TODAY))
    assert [(e.day, e.description) for e in events] == [(date(2026, 12, 20), "Date France, à confirmer pour La Réunion")]
    assert events[0].uid == "backstage-cinema-550@backstage"
    assert events[0].summary == "🎬 Dune 3 — sortie au cinéma"

    _link_site_film(cinema, 1, 550, date(2026, 12, 16))
    events = asyncio.run(calendar_events(store, cinema, TODAY))
    assert [(e.day, e.description) for e in events] == [(date(2026, 12, 16), "Au Grand Sud")]


def test_feed_skips_films_without_date_or_older_than_a_year(client):
    store, cinema = _stores()
    _track(store, 550, "Sans date", None)
    _track(store, 551, "Ancien", "2025-11-01")
    _track(store, 552, "Récent", "2025-12-01")
    _track(store, 553, "À venir", "2027-01-15")
    asyncio.run(store.upsert_tmdb_movie({"tmdb_id": 554, "title": "Pas suivi", "genres": [], "fr_release_date": "2026-12-01"}))

    events = asyncio.run(calendar_events(store, cinema, TODAY))

    assert [e.uid for e in events] == ["backstage-cinema-552@backstage", "backstage-cinema-553@backstage"]


def test_calendar_url_is_stable_until_regenerated(client):
    first = client.get("/api/cinema/calendar").json()["url"]
    assert first.startswith("https://backstage.test/api/cinema/agenda.ics?token=")
    assert client.get("/api/cinema/calendar").json()["url"] == first

    second = client.post("/api/cinema/calendar/regenerate").json()["url"]

    assert second != first
    anonymous = TestClient(client.app)
    assert anonymous.get(first.replace("https://backstage.test", "")).status_code == 404
    assert anonymous.get(second.replace("https://backstage.test", "")).status_code == 200


def test_feed_rejects_unknown_or_missing_token(client):
    anonymous = TestClient(client.app)

    unknown = anonymous.get("/api/cinema/agenda.ics?token=nimporte")
    missing = anonymous.get("/api/cinema/agenda.ics")

    assert unknown.status_code == 404 and missing.status_code == 404
    assert unknown.json() == {"detail": "Not Found"} and missing.json() == {"detail": "Not Found"}


def test_feed_works_without_session(client):
    store, _ = _stores()
    _track(store, 553, "À venir", "2027-01-15")
    url = client.get("/api/cinema/calendar").json()["url"].replace("https://backstage.test", "")
    anonymous = TestClient(client.app)

    response = anonymous.get(url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert "DTSTART;VALUE=DATE:20270115" in response.text
    assert response.text.endswith("END:VCALENDAR\r\n")


def test_calendar_url_requires_a_session(client):
    anonymous = TestClient(client.app)

    assert anonymous.get("/api/cinema/calendar").status_code == 401
