import asyncio
from datetime import datetime

import httpx

from backend.core.cinema_site import Showtime
from backend.core.cinema_store import CinemaStore
from backend.core.gemini_recommendations import GeminiGroupPick
from backend.core.party_candidates import cinema_candidates, coloc_candidates, pick_three
from backend.core.recommendations import TasteProfile
from backend.core.store import MediaStore

NOW = datetime(2026, 11, 26, 17, 0)
ANY = {"mood": "any", "runtime_max": None, "era": "any"}


def run(coro):
    return asyncio.run(coro)


class FakeTMDB:
    def __init__(self, discovered=None, details=None, discover_error=None):
        self.discovered = discovered or []
        self.details = details or {}
        self.discover_error = discover_error
        self.discover_calls = []

    async def discover_movies(self, **kwargs):
        self.discover_calls.append(kwargs)
        if self.discover_error:
            raise self.discover_error
        return list(self.discovered)

    async def get_movie_details(self, tmdb_id):
        detail = self.details.get(tmdb_id)
        if isinstance(detail, Exception):
            raise detail
        return detail


def _stores(tmp_path):
    store = MediaStore(str(tmp_path / "c.db"))
    store.init_schema()
    return store, CinemaStore(store.db_path)


def _film(cinema, site_id, title, tmdb_id=None):
    run(cinema.upsert_site_film(site_id, title, f"https://cine/{site_id}", None))
    if tmdb_id:
        run(cinema.set_tmdb_match(site_id, tmdb_id, NOW))


def test_cinema_keeps_only_tonight_after_now(tmp_path):
    _, cinema = _stores(tmp_path)
    _film(cinema, 1, "Dune", tmdb_id=11)
    run(cinema.replace_showtimes({1: [
        Showtime(datetime(2026, 11, 26, 14, 0), "VF", "https://b/1"),
        Showtime(datetime(2026, 11, 26, 20, 15), "VF", "https://b/2"),
        Showtime(datetime(2026, 11, 27, 18, 0), "VF", "https://b/3"),
    ]}))
    tmdb = FakeTMDB(details={11: {"runtime": 120, "genres": [{"id": 878}], "overview": "Sable"}})

    found = run(cinema_candidates(cinema, tmdb, TasteProfile(), ANY, NOW))

    assert [(c["title"], c["source"], c["site_id"]) for c in found] == [("Dune", "cinema", 1)]
    assert found[0]["showtime"] == {"time": "20:15", "version": "VF", "booking_url": "https://b/2"}
    assert found[0]["tmdb_id"] == 11


def test_cinema_drops_film_longer_than_runtime_max(tmp_path):
    _, cinema = _stores(tmp_path)
    _film(cinema, 1, "Long", tmdb_id=11)
    _film(cinema, 2, "Inconnu", tmdb_id=12)
    _film(cinema, 3, "Sans TMDB")
    tonight = datetime(2026, 11, 26, 20, 0)
    run(cinema.replace_showtimes({sid: [Showtime(tonight, "", None)] for sid in (1, 2, 3)}))
    tmdb = FakeTMDB(details={11: {"runtime": 150, "genres": []}, 12: httpx.ConnectError("down")})

    found = run(cinema_candidates(cinema, tmdb, TasteProfile(), {**ANY, "runtime_max": 135}, NOW))

    assert sorted(c["title"] for c in found) == ["Inconnu", "Sans TMDB"]


def _library_film(store, tmdb_id, title, categories=()):
    run(store.create({"title": title, "type": "Film", "tmdb_id": tmdb_id, "categories": list(categories)}))


def test_coloc_excludes_seen_and_marks_server_films(tmp_path):
    store, _ = _stores(tmp_path)
    _library_film(store, 1, "Sur le serveur", ["Comédie"])
    tmdb = FakeTMDB(discovered=[
        {"tmdb_id": 1, "title": "Doublon TMDB", "genre_ids": [35]},
        {"tmdb_id": 2, "title": "Déjà vu", "genre_ids": [35]},
        {"tmdb_id": 3, "title": "Nouveau", "genre_ids": [18], "poster_path": "/p.jpg"},
    ])

    found = run(coloc_candidates(store, tmdb, TasteProfile(), ANY, {2}, NOW))

    by_id = {c["tmdb_id"]: c for c in found}
    assert set(by_id) == {1, 3}
    assert by_id[1]["source"] == "server" and by_id[1]["title"] == "Sur le serveur"
    assert by_id[3]["source"] == "tmdb"
    assert by_id[3]["poster_url"] == "https://image.tmdb.org/t/p/w500/p.jpg"


def test_coloc_passes_mood_and_era_to_discover(tmp_path):
    store, _ = _stores(tmp_path)
    tmdb = FakeTMDB()

    run(coloc_candidates(store, tmdb, TasteProfile(), {"mood": "light", "runtime_max": 105, "era": "classic"}, set(), NOW))

    call = tmdb.discover_calls[0]
    assert 35 in call["with_genres"]
    assert call["release_date_lte"] == "2005-12-31"
    assert call["runtime_max"] == 105


def test_coloc_recent_era_starts_six_years_back(tmp_path):
    store, _ = _stores(tmp_path)
    tmdb = FakeTMDB()

    run(coloc_candidates(store, tmdb, TasteProfile(), {**ANY, "era": "recent"}, set(), NOW))

    call = tmdb.discover_calls[0]
    assert call["release_date_gte"] == "2020-01-01"
    assert call["release_date_lte"] == "2026-11-26"
    assert "with_genres" not in call or not call["with_genres"]


def test_coloc_survives_tmdb_failure(tmp_path):
    store, _ = _stores(tmp_path)
    _library_film(store, 1, "Sur le serveur")
    tmdb = FakeTMDB(discover_error=httpx.ConnectError("down"))

    found = run(coloc_candidates(store, tmdb, TasteProfile(), ANY, set(), NOW))

    assert [c["tmdb_id"] for c in found] == [1]


def _candidates(*sources):
    return [
        {"tmdb_id": index + 1, "title": f"F{index + 1}", "source": source, "score": 1 - index / 100}
        for index, source in enumerate(sources)
    ]


def test_pick_three_follows_gemini_order():
    pick = GeminiGroupPick(picks=[
        {"tmdb_id": 4, "reason": "a"}, {"tmdb_id": 2, "reason": "b"}, {"tmdb_id": 1, "reason": "c"},
    ])

    chosen = pick_three(_candidates("tmdb", "tmdb", "tmdb", "tmdb"), pick)

    assert [(c["rank"], c["tmdb_id"], c["reason"]) for c in chosen] == [(1, 4, "a"), (2, 2, "b"), (3, 1, "c")]


def test_pick_three_without_gemini_takes_top_three():
    chosen = pick_three(_candidates("tmdb", "tmdb", "tmdb", "tmdb"), None)

    assert [(c["rank"], c["tmdb_id"], c["reason"]) for c in chosen] == [(1, 1, ""), (2, 2, ""), (3, 3, "")]
    assert [c["tmdb_id"] for c in pick_three(_candidates("cinema"), None)] == [1]


def test_pick_three_keeps_one_server_film():
    chosen = pick_three(_candidates("tmdb", "tmdb", "tmdb", "tmdb", "server"), None)

    assert [c["tmdb_id"] for c in chosen] == [1, 2, 5]
    assert chosen[2]["rank"] == 3


def test_coloc_drops_server_film_longer_than_runtime_max(tmp_path):
    store, _ = _stores(tmp_path)
    _library_film(store, 1, "Trop long")
    _library_film(store, 2, "Court")
    _library_film(store, 3, "Durée inconnue")
    tmdb = FakeTMDB(details={1: {"runtime": 141}, 2: {"runtime": 100}, 3: httpx.ConnectError("down")})

    found = run(coloc_candidates(store, tmdb, TasteProfile(), {**ANY, "runtime_max": 135}, set(), NOW))

    assert sorted(c["title"] for c in found) == ["Court", "Durée inconnue"]
