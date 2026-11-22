import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from backend import api
from backend.core.media_server import Availability
from backend.core.models import Media
from backend.core.recommendations import RecommendationCandidate


def _candidate(tmdb_id, score):
    return RecommendationCandidate(tmdb_id=tmdb_id, title=f"Film {tmdb_id}", score=score, genre_ids=[878])


class _Store:
    def __init__(self, medias, availabilities):
        self.medias, self.availabilities = medias, availabilities

    async def fetch_all(self):
        return self.medias

    async def list_availabilities(self):
        return self.availabilities


def _run(monkeypatch, *, owned):
    # Discoveries score higher than the two films already on the server.
    pool = [_candidate(tmdb_id, 10 - index) for index, tmdb_id in enumerate([1, 2, 3, 4, 5, 6, 101, 102])]
    medias = [Media(id=f"m{tmdb_id}", title=f"Film {tmdb_id}", type="Film", tmdb_id=tmdb_id) for tmdb_id in (101, 102)]
    availabilities = [Availability(media_id=media.id, provider="radarr", jellyfin_id=f"j-{media.id}", state="available") for media in medias]

    async def fake_pool(current, store, preferences):
        return pool

    async def fake_access(current, media_id, store):
        if media_id not in owned:
            raise HTTPException(status_code=403, detail="Tu n'as pas accès à ce contenu")

    monkeypatch.setattr(api, "_recommendation_pool", fake_pool)
    monkeypatch.setattr(api, "_ensure_playback_access", fake_access)
    monkeypatch.setattr(api, "_gemini_gateway", lambda: SimpleNamespace(enabled=False))
    current = SimpleNamespace(user={"id": "coloc", "role": "user"})
    return asyncio.run(api._guided_results(current, _Store(medias, availabilities), SimpleNamespace(id="s"), {"answers": [], "genres": []}))


def test_films_already_on_the_server_come_first_even_when_the_user_must_rent_them(monkeypatch):
    results = _run(monkeypatch, owned=set())

    assert [item["tmdb_id"] for item in results[:2]] == [101, 102]
    assert all(item["ready_tonight"] and item["action"] == "rent" for item in results[:2])
    assert not any(item["ready_tonight"] for item in results[2:])


def test_playable_films_rank_before_instant_rentals(monkeypatch):
    results = _run(monkeypatch, owned={"m102"})

    assert [(item["tmdb_id"], item["action"]) for item in results[:2]] == [(102, "play"), (101, "rent")]
