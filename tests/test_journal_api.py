import asyncio
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.journal_api as journal_api
from backend.api import health_router, router as media_router
from backend.auth_api import auth_router
from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.store import MediaStore
from backend.journal_api import journal_router
from tests.test_auth_api import _setup
from tests.test_coloc_rentals import _login_as_new_user


class FakeTMDB:
    calls = 0
    down = False

    def __init__(self, *args, **kwargs):
        pass

    async def get_movie_details(self, tmdb_id):
        FakeTMDB.calls += 1
        if FakeTMDB.down:
            return None
        return {
            "id": tmdb_id, "title": "Dune 2", "release_date": "2024-02-28",
            "poster_path": "/d.jpg", "genres": [{"id": 1, "name": "SF"}],
            "release_dates": {"results": [
                {"iso_3166_1": "FR", "release_dates": [{"type": 3, "release_date": "2024-02-28T00:00:00.000Z"}]},
            ]},
        }

    @staticmethod
    def poster_url_from_path(poster_path, size="w500"):
        return f"https://img{poster_path}" if poster_path else None

    def get_genres(self, details):
        return [g.get("name") for g in details.get("genres", [])]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "backstage.db"
    MediaStore(str(db)).init_schema()
    AuthStore(str(db)).init_schema()
    monkeypatch.setattr(Config, "DB_PATH", str(db))
    FakeTMDB.calls = 0
    FakeTMDB.down = False
    monkeypatch.setattr(journal_api, "TMDBClient", FakeTMDB)
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(media_router)
    app.include_router(journal_router)
    test_client = TestClient(app)
    _setup(test_client)
    return test_client


def _store():
    return MediaStore(Config.DB_PATH)


def test_add_entry_outside_library_creates_no_media(client):
    response = client.post("/api/journal", json={
        "tmdb_id": 550, "watched_on": "2026-11-22", "rating": 4.5, "in_cinema": True,
    })

    assert response.status_code == 201
    body = response.json()
    assert body["movie"]["title"] == "Dune 2"
    assert body["movie"]["year"] == 2024
    assert body["media_id"] is None
    assert body["in_cinema"] is True
    assert asyncio.run(_store().fetch_all()) == []


def test_watched_on_defaults_to_today_and_future_is_rejected(client):
    response = client.post("/api/journal", json={"tmdb_id": 550})
    assert response.status_code == 201
    assert response.json()["watched_on"] == date.today().isoformat()

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.post("/api/journal", json={"tmdb_id": 550, "watched_on": tomorrow}).status_code == 422
    assert client.post("/api/journal", json={"tmdb_id": 550, "rating": 4.2}).status_code == 422

    unknown = client.post("/api/journal", json={"tmdb_id": 550, "watched_on": None})
    assert unknown.status_code == 201
    assert unknown.json()["watched_on"] is None


def test_cached_movie_skips_tmdb(client):
    client.post("/api/journal", json={"tmdb_id": 550})
    client.post("/api/journal", json={"tmdb_id": 550})

    assert FakeTMDB.calls == 1


def test_tmdb_down_creates_nothing(client):
    FakeTMDB.down = True

    response = client.post("/api/journal", json={"tmdb_id": 550})

    assert response.status_code == 502
    assert response.json()["detail"] == "TMDB est injoignable, réessaie plus tard."
    assert client.get("/api/journal").json() == {"entries": []}


def test_journal_is_private(client):
    entry = client.post("/api/journal", json={"tmdb_id": 550, "rating": 4}).json()

    _login_as_new_user(client)

    assert client.get("/api/journal").json() == {"entries": []}
    assert client.patch(f"/api/journal/{entry['id']}", json={"rating": 1}).status_code == 404
    assert client.delete(f"/api/journal/{entry['id']}").status_code == 404
    stored = asyncio.run(_store().get_diary_entry(entry["id"]))
    assert stored.rating == 4


def _library_film(client):
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))
    entry = client.post("/api/journal", json={"tmdb_id": 550, "rating": 4}).json()
    film = next(m for m in client.get("/api/medias").json() if m["id"] == "dune")
    return entry, film


def test_entry_on_library_film_marks_it_seen(client):
    entry, film = _library_film(client)

    assert film["status"] == "Terminé"
    assert film["rating"] == "4"
    assert entry["media_id"] == "dune"
    assert client.get("/api/journal").json()["entries"][0]["media_id"] == "dune"


def test_patch_entry_updates_fields(client):
    entry = client.post("/api/journal", json={"tmdb_id": 550, "rating": 4}).json()

    response = client.patch(f"/api/journal/{entry['id']}", json={"rating": 3.5, "review": "Long"})

    assert response.status_code == 200
    assert response.json()["rating"] == 3.5
    assert response.json()["review"] == "Long"
    assert client.patch(f"/api/journal/{entry['id']}", json={"rating": 6}).status_code == 422


def test_delete_keeps_library_state(client):
    entry, _ = _library_film(client)

    assert client.delete(f"/api/journal/{entry['id']}").status_code == 204

    film = next(m for m in client.get("/api/medias").json() if m["id"] == "dune")
    assert film["status"] == "Terminé"


def test_library_rating_writes_one_journal_entry(client):
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))

    assert client.patch("/api/medias/dune/personal", json={"rating": "4"}).status_code == 200
    assert client.patch("/api/medias/dune/personal", json={"rating": "4.5"}).status_code == 200

    entries = client.get("/api/journal").json()["entries"]
    assert len(entries) == 1
    assert entries[0]["rating"] == 4.5
    assert entries[0]["source"] == "library"
    assert entries[0]["watched_on"] == date.today().isoformat()


def test_library_rating_survives_tmdb_down(client):
    FakeTMDB.down = True
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))

    response = client.patch("/api/medias/dune/personal", json={"rating": "4"})

    assert response.status_code == 200
    assert response.json()["rating"] == "4"
    assert client.get("/api/journal").json() == {"entries": []}


def test_journal_film_arriving_later_shows_as_seen(client):
    client.post("/api/journal", json={"tmdb_id": 550})
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))

    film = next(m for m in client.get("/api/medias").json() if m["id"] == "dune")

    assert film["status"] == "Terminé"
    assert client.get("/api/medias/dune").json()["status"] == "Terminé"


def test_journal_feeds_recommendation_seen_set(tmp_path, monkeypatch):
    from backend import api
    from backend.auth_api import AuthContext
    from backend.core.models import DiaryEntry
    from tests.test_recommendation_pool import FakeCompareTMDB
    from datetime import datetime, timezone

    store = MediaStore(str(tmp_path / "pool.db"))
    store.init_schema()
    current = AuthContext(user={"id": "hugo", "role": "admin"}, session_id="auth", token="token")
    monkeypatch.setattr(api, "TMDBClient", FakeCompareTMDB)
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_diary_entry(DiaryEntry(
        id="e1", backstage_user_id="hugo", tmdb_id=2, created_at=now, updated_at=now,
    )))

    pool = asyncio.run(api._recommendation_pool(current, store, {}))

    score = {candidate.tmdb_id: candidate.score for candidate in pool}
    # Seen films stay in the pool but are pushed below zero, out of reach.
    assert score[2] < 0
    assert score[4] >= 0


def test_already_seen_answer_creates_dateless_entry(client):
    for _ in range(2):
        response = client.post("/api/recommendations/events", json={"event_type": "already_seen", "value": "550"})
        assert response.status_code == 200

    entries = client.get("/api/journal").json()["entries"]
    assert len(entries) == 1
    assert entries[0]["watched_on"] is None
    assert entries[0]["source"] == "recommendation"
    assert entries[0]["rating"] is None


# --- Final review fixes -------------------------------------------------------

def test_today_follows_app_timezone(client, monkeypatch):
    from datetime import datetime, timezone
    # 23:30 UTC on 26/11 is already 27/11 in Paris: a late screening logged
    # after midnight must not be rejected as "in the future".
    monkeypatch.setattr(journal_api, "_utcnow", lambda: datetime(2026, 11, 26, 23, 30, tzinfo=timezone.utc))

    assert journal_api.local_today() == date(2026, 11, 27)
    response = client.post("/api/journal", json={"tmdb_id": 550, "watched_on": "2026-11-27"})
    assert response.status_code == 201
    assert client.post("/api/journal", json={"tmdb_id": 550}).json()["watched_on"] == "2026-11-27"
    assert client.post("/api/journal", json={"tmdb_id": 550, "watched_on": "2026-11-28"}).status_code == 422


def test_library_status_change_wins_over_journal(client):
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))
    client.post("/api/journal", json={"tmdb_id": 550, "rating": 4})

    client.patch("/api/medias/dune/personal", json={"status": "watchlist"})

    film = next(m for m in client.get("/api/medias").json() if m["id"] == "dune")
    assert film["status"] == "À regarder"
    assert client.get("/api/medias/dune").json()["status"] == "À regarder"


def test_journal_film_does_not_mark_a_series_with_the_same_id(client):
    asyncio.run(_store().create({"id": "show", "title": "Une série", "type": "Série", "tmdb_id": 550}))
    client.post("/api/journal", json={"tmdb_id": 550})

    series = next(m for m in client.get("/api/medias").json() if m["id"] == "show")

    assert series["status"] != "Terminé"


def test_editing_an_entry_keeps_the_library_choice(client):
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))
    entry = client.post("/api/journal", json={"tmdb_id": 550, "rating": 4}).json()
    client.patch("/api/medias/dune/personal", json={"status": "watchlist", "is_watchlist": True})

    client.patch(f"/api/journal/{entry['id']}", json={"review": "Revu avec plaisir"})

    film = client.get("/api/medias/dune").json()
    assert film["status"] == "À regarder"
    assert film["is_watchlist"] is True


def test_cached_movie_keeps_french_release_date(client):
    client.post("/api/journal", json={"tmdb_id": 550})
    assert asyncio.run(_store().get_tmdb_movies([550]))[550]["fr_release_date"] == "2024-02-28"


# --- Journal ↔ bibliothèque ---------------------------------------------------

def test_journal_rating_and_review_follow_a_film_added_later(client):
    client.post("/api/journal", json={"tmdb_id": 550, "rating": 4.5, "review": "Sublime."})
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))

    film = next(m for m in client.get("/api/medias").json() if m["id"] == "dune")

    assert film["status"] == "Terminé"
    assert film["rating"] == "4.5"
    assert film["review"] == "Sublime."
    single = client.get("/api/medias/dune").json()
    assert (single["rating"], single["review"]) == ("4.5", "Sublime.")


def test_rewatch_without_note_keeps_the_previous_journal_note(client):
    client.post("/api/journal", json={"tmdb_id": 550, "watched_on": "2026-01-01", "rating": 3, "review": "Bien."})
    client.post("/api/journal", json={"tmdb_id": 550, "watched_on": "2026-02-01"})
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))

    film = client.get("/api/medias/dune").json()

    assert (film["rating"], film["review"]) == ("3", "Bien.")


def test_library_rating_wins_over_the_journal_note(client):
    client.post("/api/journal", json={"tmdb_id": 550, "rating": 2})
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))

    client.patch("/api/medias/dune/personal", json={"rating": "5"})

    assert client.get("/api/medias/dune").json()["rating"] == "5"


def test_watchlisted_film_does_not_show_the_old_journal_note(client):
    asyncio.run(_store().create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))
    client.post("/api/journal", json={"tmdb_id": 550, "rating": 4})
    client.patch("/api/medias/dune/personal", json={"status": "watchlist"})

    film = client.get("/api/medias/dune").json()

    assert film["status"] == "À regarder"
    assert film["rating"] is None
