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
