import asyncio

import httpx

from backend.core.tmdb import TMDBClient


def test_discover_movies_builds_tmdb_query_and_normalizes_candidates(monkeypatch):
    async def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert url.endswith("/discover/movie")
        assert kwargs["params"]["with_genres"] == "878|18"
        assert kwargs["params"]["vote_count.gte"] == 25
        return httpx.Response(200, request=httpx.Request("GET", url), json={"results": [
            {"id": 1, "title": "Dune", "genre_ids": [878], "vote_average": 8.2, "popularity": 100},
        ]})

    monkeypatch.setattr("backend.core.tmdb.http.request_with_retry", fake_request)
    client = object.__new__(TMDBClient)
    client.params = {"api_key": "secret", "language": "fr-FR"}

    results = asyncio.run(client.discover_movies(with_genres=[878, 18], min_vote_count=25))

    assert results[0]["tmdb_id"] == 1
    assert results[0]["title"] == "Dune"
    assert results[0]["vote_average"] == 8.2


def test_discover_movies_passes_release_date_bounds_when_given(monkeypatch):
    async def fake_request(method, url, **kwargs):
        assert kwargs["params"]["primary_release_date.gte"] == "2020-01-01"
        assert kwargs["params"]["primary_release_date.lte"] == "2005-12-31"
        return httpx.Response(200, request=httpx.Request("GET", url), json={"results": []})

    monkeypatch.setattr("backend.core.tmdb.http.request_with_retry", fake_request)
    client = object.__new__(TMDBClient)
    client.params = {"api_key": "secret", "language": "fr-FR"}

    asyncio.run(client.discover_movies(release_date_gte="2020-01-01", release_date_lte="2005-12-31"))


def test_discover_movies_omits_release_date_bounds_when_not_given(monkeypatch):
    async def fake_request(method, url, **kwargs):
        assert "primary_release_date.gte" not in kwargs["params"]
        assert "primary_release_date.lte" not in kwargs["params"]
        return httpx.Response(200, request=httpx.Request("GET", url), json={"results": []})

    monkeypatch.setattr("backend.core.tmdb.http.request_with_retry", fake_request)
    client = object.__new__(TMDBClient)
    client.params = {"api_key": "secret", "language": "fr-FR"}

    asyncio.run(client.discover_movies())
