import asyncio

from backend import api
from backend.auth_api import AuthContext
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def test_new_session_does_not_repeat_recent_question_movies(tmp_path, monkeypatch):
    class FakeTMDB:
        async def discover_movies(self, **kwargs):
            return [
                {"tmdb_id": index, "title": f"Film {index}", "genre_ids": [35], "vote_average": 7}
                for index in range(1, 9)
            ]

    store = make_store(tmp_path)
    current = AuthContext(user={"id": "hugo", "role": "user"}, session_id="auth", token="token")
    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)
    monkeypatch.setattr(api, "_gemini_gateway", lambda: type("DisabledGateway", (), {"enabled": False})())

    first = asyncio.run(api.start_recommendation_session(current, store))
    first_ids = {option["tmdb_id"] for option in first["question"]["options"]}

    next_question = asyncio.run(api.answer_recommendation(
        first["session"]["id"],
        api.RecommendationAnswerRequest(answer="light"),
        current,
        store,
    ))
    next_ids = {option["tmdb_id"] for option in next_question["question"]["options"]}
    assert first_ids.isdisjoint(next_ids)

    second = asyncio.run(api.start_recommendation_session(current, store))
    second_ids = {option["tmdb_id"] for option in second["question"]["options"]}
    assert first_ids.isdisjoint(second_ids)
    assert next_ids.isdisjoint(second_ids)
