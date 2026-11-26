import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.core.cinema_bot as cinema_bot
from backend.api import health_router, router as media_router
from backend.auth_api import auth_router
from backend.cinema_api import cinema_router
from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.cinema_bot import build_reply, film_showtimes, handle_chat_message, parse_command
from backend.core.cinema_site import Showtime
from backend.core.cinema_store import CinemaStore
from backend.core.cinema_sync import reunion_now
from backend.core.store import MediaStore
from tests.test_auth_api import _setup

NOW = datetime(2026, 11, 26, 18, 0)


@pytest.mark.parametrize("body,expected", [
    ("@ciné films", "films"), ("@CINE  films ", "films"), ("@ciné ce soir", "ce soir"),
    ("@cine soir", "ce soir"), ("@ciné demain", "demain"), ("@ciné", "aide"),
    ("@ciné n'importe quoi", "aide"), ("@Ciné Aide", "aide"),
    ("salut @ciné films", None), ("@cinéma", None), ("bonjour", None),
])
def test_parse_command(body, expected):
    assert parse_command(body) == expected


@pytest.fixture
def stores(tmp_path):
    store = MediaStore(str(tmp_path / "bot.db"))
    store.init_schema()
    return store, CinemaStore(store.db_path)


def _show(day, hour, minute=0, version="VF"):
    return Showtime(datetime(2026, 11, day, hour, minute), version, f"https://tickets.test/{day}-{hour}{minute}")


def _programme(store, cinema, *, success_at=NOW):
    asyncio.run(cinema.upsert_site_film(1, "Dune", "/film/dune/1/", None))
    asyncio.run(cinema.upsert_site_film(2, "Camembert", "/film/camembert/2/", None))
    asyncio.run(cinema.upsert_site_film(3, "Ancien", "/film/ancien/3/", None))
    asyncio.run(cinema.set_tmdb_match(1, 550, NOW))
    asyncio.run(cinema.replace_showtimes({
        1: [_show(26, 17, 20), _show(26, 20, 0, "VOST"), _show(27, 14)],
        2: [_show(27, 20, 30)],
        3: [_show(25, 20)],
    }))
    if success_at is not None:
        asyncio.run(cinema.record_success(success_at))
    film_list = asyncio.run(store.create_film_list("Ciné", "hugo"))
    asyncio.run(store.add_film_list_item(film_list.id, 550, "hugo"))


def test_films_reply_lists_upcoming_films_with_tracked_flag(stores):
    store, cinema = stores
    _programme(store, cinema)

    body, payload = asyncio.run(build_reply("films", cinema, NOW))

    assert body == "À l'affiche au Grand Sud :"
    assert payload == {"type": "cine_films", "films": [
        {"site_id": 2, "title": "Camembert", "tracked": False},
        {"site_id": 1, "title": "Dune", "tracked": True},
    ]}


def test_tonight_skips_showtimes_already_started(stores):
    store, cinema = stores
    _programme(store, cinema)

    body, payload = asyncio.run(build_reply("ce soir", cinema, NOW))

    assert body == "Ce soir au Grand Sud :\n• Dune : 20:00 VOST"
    assert [f["site_id"] for f in payload["films"]] == [1]


def test_tomorrow_lists_each_film_once(stores):
    store, cinema = stores
    _programme(store, cinema)

    body, _ = asyncio.run(build_reply("demain", cinema, NOW))

    assert body == "Demain (vendredi 27/11) au Grand Sud :\n• Dune : 14:00 VF\n• Camembert : 20:30 VF"


def test_nothing_left_tonight(stores):
    store, cinema = stores
    _programme(store, cinema)

    body, payload = asyncio.run(build_reply("ce soir", cinema, NOW.replace(hour=22)))

    assert body == "Plus de séance ce soir au Grand Sud."
    assert payload is None


def test_stale_data_is_announced_instead_of_showtimes(stores):
    store, cinema = stores
    _programme(store, cinema, success_at=datetime(2026, 11, 23, 9, 0))

    assert asyncio.run(build_reply("films", cinema, NOW)) == ("Horaires indisponibles depuis le 23/11.", None)


def test_no_data_yet(stores):
    store, cinema = stores
    _programme(store, cinema, success_at=None)

    assert asyncio.run(build_reply("demain", cinema, NOW)) == ("Horaires pas encore disponibles.", None)


def test_help_answers_even_when_stale(stores):
    store, cinema = stores

    body, payload = asyncio.run(build_reply("aide", cinema, NOW))

    assert body == "Commandes du bot Ciné :"
    assert payload["type"] == "cine_help"
    assert [c["command"] for c in payload["commands"]] == ["@ciné films", "@ciné ce soir", "@ciné demain", "@ciné aide"]


def test_film_without_tmdb_match_still_listed(stores):
    store, cinema = stores
    _programme(store, cinema)

    _, payload = asyncio.run(build_reply("films", cinema, NOW))
    detail = asyncio.run(film_showtimes(cinema, 2, NOW))

    assert any(f["site_id"] == 2 for f in payload["films"])
    assert detail["days"][0]["showtimes"] == [{"time": "20:30", "version": "VF", "booking_url": "https://tickets.test/27-2030"}]


def test_film_showtimes_groups_by_day_and_hides_past(stores):
    store, cinema = stores
    _programme(store, cinema)

    detail = asyncio.run(film_showtimes(cinema, 1, NOW))

    assert detail["title"] == "Dune" and detail["stale"] is False
    assert [(d["date"], d["label"], [s["time"] for s in d["showtimes"]]) for d in detail["days"]] == [
        ("2026-11-26", "jeudi 26/11", ["20:00"]),
        ("2026-11-27", "vendredi 27/11", ["14:00"]),
    ]
    assert asyncio.run(film_showtimes(cinema, 99, NOW)) is None


def test_ordinary_message_gets_no_reply(stores):
    store, _ = stores

    assert asyncio.run(handle_chat_message("bonjour", store, NOW)) is None
    assert asyncio.run(store.list_chat_messages()) == []


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "backstage.db"
    MediaStore(str(db)).init_schema()
    AuthStore(str(db)).init_schema()
    monkeypatch.setattr(Config, "DB_PATH", str(db))
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(media_router)
    app.include_router(cinema_router)
    test_client = TestClient(app)
    _setup(test_client)
    return test_client


def test_posting_a_command_adds_a_bot_reply(client):
    response = client.post("/api/chat/messages", json={"body": "@ciné aide"})

    assert response.status_code == 200
    assert response.json()["body"] == "@ciné aide"
    messages = client.get("/api/chat/messages").json()["messages"]
    assert len(messages) == 2
    assert messages[1]["author"]["id"] == "bot:cine"
    assert messages[1]["payload"]["type"] == "cine_help"


def test_bot_failure_does_not_lose_the_message(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("base verrouillée")

    monkeypatch.setattr(cinema_bot, "build_reply", broken)

    response = client.post("/api/chat/messages", json={"body": "@ciné films"})

    assert response.status_code == 200
    assert response.json()["body"] == "@ciné films"
    assert len(client.get("/api/chat/messages").json()["messages"]) == 1


def test_film_showtimes_route(client):
    cinema = CinemaStore(Config.DB_PATH)
    now = reunion_now()
    asyncio.run(cinema.upsert_site_film(1, "Dune", "/film/dune/1/", None))
    asyncio.run(cinema.replace_showtimes({1: [
        Showtime(now - timedelta(days=1), "VF", None),
        Showtime(now + timedelta(days=1), "VOST", None),
    ]}))
    asyncio.run(cinema.record_success(now))

    response = client.get("/api/cinema/films/1/showtimes")

    assert response.status_code == 200
    days = response.json()["days"]
    assert [s["version"] for d in days for s in d["showtimes"]] == ["VOST"]
    missing = client.get("/api/cinema/films/99/showtimes")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Film inconnu"
