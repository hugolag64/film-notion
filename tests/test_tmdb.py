import asyncio

from backend.config import Config
from backend.core import tmdb
from backend.core.tmdb import TMDBClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_search_movie_promotes_exact_title_beyond_first_five(monkeypatch):
    candidates = [
        {"id": index, "title": title}
        for index, title in enumerate(
            ["Play Motel", "Play Dirty", "Play Dead", "Jeu d'enfant", "Games Women Play", "Fair Play", "Money Play$", "Play"],
            start=1,
        )
    ]

    async def fake_request(*args, **kwargs):
        return FakeResponse({"results": candidates})

    monkeypatch.setattr(Config, "TMDB_API_KEY", "test-key")
    monkeypatch.setattr(tmdb.http, "request_with_retry", fake_request)

    results = asyncio.run(TMDBClient().search_movie("Play"))

    assert results[0]["title"] == "Play"
    assert len(results) == 8


def test_search_movie_keeps_tmdb_relevance_for_punctuation_variant(monkeypatch):
    candidates = [
        {"id": 252178, "title": "'71"},
        {"id": 1018488, "title": "71"},
        {"id": 881525, "title": "71"},
    ]

    async def fake_request(*args, **kwargs):
        return FakeResponse({"results": candidates})

    monkeypatch.setattr(Config, "TMDB_API_KEY", "test-key")
    monkeypatch.setattr(tmdb.http, "request_with_retry", fake_request)

    results = asyncio.run(TMDBClient().search_movie("71"))

    assert results[0]["id"] == 252178


def test_search_ranking_puts_the_popular_exact_title_before_obscure_matches():
    from backend.core.tmdb import _rank_search_results

    results = [
        {"id": 1, "title": "Interstellar Wars", "popularity": 1.2},
        {"id": 2, "title": "Lolita from Interstellar Space", "popularity": 0.8},
        {"id": 3, "title": "The Science of Interstellar", "popularity": 3.0},
        {"id": 4, "title": "Interstellar", "popularity": 140.0},
    ]

    assert [r["id"] for r in _rank_search_results(results, "interstellar")] == [4, 1, 3, 2]
    # While typing, prefix matches come first, most popular on top.
    assert [r["id"] for r in _rank_search_results(results, "interstel")][:2] == [4, 1]
