import asyncio

from backend import api
from backend.auth_api import AuthContext
from backend.core.gemini_recommendations import GeminiQuestionPlan, GeminiSelection
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
        shown.update(option["tmdb_id"] for option in response["question"]["options"] if "tmdb_id" in option)
        response = asyncio.run(api.answer_recommendation(
            session_id, api.RecommendationAnswerRequest(answer="light"), current, store,
        ))
        if response["state"] == "result":
            break

    assert response["state"] == "result"
    assert response["result"]["tmdb_id"] not in shown


def test_two_pass_usage_is_user_and_session_scoped(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    current = current_user()
    pool = candidate_pool()
    monkeypatch.setattr(api, "_recommendation_pool", lambda *args: asyncio.sleep(0, result=pool))

    class FakeGateway:
        enabled = True
        final_answers = []

        def plan_questions(self, profile, recent_axes, recent_plans=None):
            return GeminiQuestionPlan(
                axes=["movie_compare", "mood", "genre", "era"],
                usage={"input_tokens": 10, "output_tokens": 3},
            )

        def select_final(self, profile, answers, candidates):
            self.final_answers = answers
            return GeminiSelection(tmdb_id=candidates[0]["tmdb_id"], confidence=.9, reason="fit", usage={"input_tokens": 12, "output_tokens": 4})

    gateway = FakeGateway()
    monkeypatch.setattr(api, "_gemini_gateway", lambda: gateway)
    response = asyncio.run(api.start_recommendation_session(current, store))
    session_id = response["session"]["id"]
    assert response["question"]["axis"] == "movie_compare"
    for answer in ("picked", "light", "genre:Comédie", "era:classic"):
        value = "1" if answer == "picked" else None
        response = asyncio.run(api.answer_recommendation(
            session_id, api.RecommendationAnswerRequest(answer=answer, value=value), current, store,
        ))
    assert response["state"] == "result"
    assert [item["answer"] for item in gateway.final_answers] == ["picked", "light", "genre:Comédie", "era:classic"]
    usage = asyncio.run(store.get_recommendation_usage(response["session_id"]))
    assert len(usage) == 2
    assert sum(row["input_tokens"] for row in usage) == 22
    assert all(row["backstage_user_id"] == "hugo" for row in usage)


def test_empty_local_pool_skips_gemini_planner(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    current = current_user()
    monkeypatch.setattr(api, "_recommendation_pool", lambda *args: asyncio.sleep(0, result=[]))

    class FailingGateway:
        enabled = True

        def plan_questions(self, profile, recent_axes, recent_plans=None):
            raise AssertionError("Gemini planner must not run without local candidates")

    monkeypatch.setattr(api, "_gemini_gateway", lambda: FailingGateway())
    response = asyncio.run(api.start_recommendation_session(current, store))
    assert response["state"] == "empty"


def test_each_session_gets_a_different_path_even_when_gemini_repeats_plan(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    current = current_user()
    pool = candidate_pool()
    monkeypatch.setattr(api, "_recommendation_pool", lambda *args: asyncio.sleep(0, result=pool))

    class RepeatingGateway:
        enabled = True
        calls = 0

        def plan_questions(self, profile, recent_axes, recent_plans=None):
            self.calls += 1
            return GeminiQuestionPlan(
                axes=["movie_compare", "mood", "genre", "era"],
                usage={"input_tokens": 10, "output_tokens": 3},
            )

    gateway = RepeatingGateway()
    monkeypatch.setattr(api, "_gemini_gateway", lambda: gateway)
    first = asyncio.run(api.start_recommendation_session(current, store))
    second = asyncio.run(api.start_recommendation_session(current, store))

    assert gateway.calls == 2
    assert first["question"]["axis"] != second["question"]["axis"]
