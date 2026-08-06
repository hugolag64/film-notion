import asyncio
from datetime import datetime, timezone

from backend import api
from backend.auth_api import AuthContext
from backend.core.models import RecommendationEvent, RecommendationSession
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def test_recommendation_events_are_user_scoped_and_newest_first(tmp_path):
    store = make_store(tmp_path)
    older = RecommendationEvent(
        id="e1", backstage_user_id="hugo", event_type="shown",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    newer = older.model_copy(update={"id": "e2", "event_type": "picked", "media_id": "dune", "created_at": datetime(2026, 8, 2, tzinfo=timezone.utc)})
    asyncio.run(store.record_recommendation_event(older))
    asyncio.run(store.record_recommendation_event(newer))
    asyncio.run(store.record_recommendation_event(older.model_copy(update={"id": "e3", "backstage_user_id": "ophelie"})))

    events = asyncio.run(store.list_recommendation_events("hugo"))

    assert [event.id for event in events] == ["e2", "e1"]


def test_recommendation_session_round_trip(tmp_path):
    store = make_store(tmp_path)
    session = RecommendationSession(
        id="s1", backstage_user_id="hugo",
        created_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )
    asyncio.run(store.create_recommendation_session(session))
    updated = asyncio.run(store.update_recommendation_session(
        "s1", {"question_count": 2, "session_preferences": {"mood": "light"}},
    ))

    assert updated.question_count == 2
    assert updated.session_preferences == {"mood": "light"}


def test_recommendation_session_does_not_repeat_shown_movies(tmp_path, monkeypatch):
    class FakeTMDB:
        async def discover_movies(self, **kwargs):
            return [
                {"tmdb_id": tmdb_id, "title": f"Film {tmdb_id}", "vote_average": 7 + tmdb_id / 10}
                for tmdb_id in range(1, 7)
            ]

    store = make_store(tmp_path)
    current = AuthContext(user={"id": "hugo", "role": "user"}, session_id="session", token="token")
    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    first = asyncio.run(api.start_recommendation_session(current, store))
    first_ids = {option["tmdb_id"] for option in first["question"]["options"]}

    second = asyncio.run(api.answer_recommendation(
        first["session"]["id"],
        api.RecommendationAnswerRequest(answer="light"),
        current,
        store,
    ))
    second_ids = {option["tmdb_id"] for option in second["question"]["options"]}

    assert first_ids.isdisjoint(second_ids)
