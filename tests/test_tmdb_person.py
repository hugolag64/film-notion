import asyncio

import httpx

from backend.core.tmdb import TMDBClient


def test_search_person_returns_tmdb_results(monkeypatch):
    async def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert url.endswith("/search/person")
        assert kwargs["params"]["query"] == "matt dam"
        return httpx.Response(200, request=httpx.Request("GET", url), json={"results": [
            {"id": 1892, "name": "Matt Damon", "profile_path": "/matt.jpg"},
        ]})

    monkeypatch.setattr("backend.core.tmdb.http.request_with_retry", fake_request)
    client = object.__new__(TMDBClient)
    client.params = {"api_key": "secret", "language": "fr-FR"}

    results = asyncio.run(client.search_person("matt dam"))

    assert results == [{"id": 1892, "name": "Matt Damon", "profile_path": "/matt.jpg"}]
