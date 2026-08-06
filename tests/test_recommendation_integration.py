import asyncio

from backend import api
from backend.auth_api import AuthContext
from backend.core.gemini_recommendations import GeminiSelection, GeminiShortlist
from backend.core.recommendations import RecommendationCandidate
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def current_user(user_id="hugo", role="user"):
    return AuthContext(user={"id": user_id, "role": role}, session_id="auth", token="token")


def candidate_pool(count=12):
    return [
        RecommendationCandidate(
            tmdb_id=index, title=f"Film {index}", score=1 - index / 100,
            genre_ids=[35 if index % 2 else 18], vote_average=7,
        )
        for index in range(1, count + 1)
    ]


def test_full_session_uses_local_fallback_and_never_repeats(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    current = current_user()
    async def fake_pool(_current, _store, preferences):
        shown = {int(value) for value in preferences.get("shown_tmdb_ids", [])}
        return [item for item in candidate_pool() if item.tmdb_id not in shown]

    monkeypatch.setattr(api, "_recommendation_pool", fake_pool)
    monkeypatch.setattr(api, "_gemini_gateway", lambda: type("DisabledGateway", (), {"enabled": False})())

    response = asyncio.run(api.start_recommendation_session(current, store))
    session_id = response["session"]["id"]
    shown = set()
    for _ in range(5):
        shown.update(option["tmdb_id"] for option in response["question"]["options"])
        response = asyncio.run(api.answer_recommendation(
            session_id, api.RecommendationAnswerRequest(answer="light"), current, store,
        ))

    assert response["state"] == "result"
    assert response["result"]["tmdb_id"] not in shown


def test_two_pass_usage_is_user_and_session_scoped(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    current = current_user()
    pool = candidate_pool()
    monkeypatch.setattr(api, "_recommendation_pool", lambda *args: asyncio.sleep(0, result=pool))

    class FakeGateway:
        enabled = True

        def select_shortlist(self, profile, candidates):
            return GeminiShortlist(tmdb_ids=[item["tmdb_id"] for item in candidates], usage={"input_tokens": 10, "output_tokens": 3})

        def select_final(self, profile, answers, candidates):
            return GeminiSelection(tmdb_id=candidates[0]["tmdb_id"], confidence=.9, reason="fit", usage={"input_tokens": 12, "output_tokens": 4})

    monkeypatch.setattr(api, "_gemini_gateway", lambda: FakeGateway())
    response = asyncio.run(api.start_recommendation_session(current, store))
    response = asyncio.run(api.answer_recommendation(
        response["session"]["id"], api.RecommendationAnswerRequest(answer="surprise"), current, store,
    ))
    usage = asyncio.run(store.get_recommendation_usage(response["session_id"]))
    assert len(usage) == 2
    assert sum(row["input_tokens"] for row in usage) == 22
    assert all(row["backstage_user_id"] == "hugo" for row in usage)
