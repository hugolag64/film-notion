from types import SimpleNamespace

import pytest

from backend.core.gemini_recommendations import GeminiQuestionPlan, GeminiRecommendationGateway


class FakeModels:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            text=self.text,
            usage_metadata=SimpleNamespace(
                prompt_token_count=120,
                candidates_token_count=24,
                total_token_count=144,
            ),
        )


class FakeClient:
    def __init__(self, text):
        self.models = FakeModels(text)


def candidates():
    return [
        {"tmdb_id": 42, "title": "Play", "overview": "Comédie française", "genre_ids": [35]},
        {"tmdb_id": 99, "title": "Autre", "overview": "Drame", "genre_ids": [18]},
    ]


def test_disabled_gemini_falls_back_without_call():
    gateway = GeminiRecommendationGateway(api_key=None)
    assert gateway.select_final({}, [], candidates()) is None
    assert gateway.plan_questions({}, []) is None


def test_question_plan_keeps_supported_unique_axes():
    gateway = GeminiRecommendationGateway(
        api_key="secret",
        client=FakeClient('{"axes":["mood","movie_compare","mood","bogus","genre"]}'),
    )
    result = gateway.plan_questions({"confidence": 0.5}, ["mood"])
    assert isinstance(result, GeminiQuestionPlan)
    assert result.axes == ["mood", "movie_compare", "genre"]
    assert result.usage["input_tokens"] == 120


def test_valid_json_selection_is_limited_to_supplied_tmdb_ids():
    gateway = GeminiRecommendationGateway(
        api_key="secret", client=FakeClient('{"tmdb_id": 42, "confidence": 0.91, "reason": "profil"}'),
    )
    result = gateway.select_final({"genres": ["Comédie"]}, [], candidates())
    assert result.tmdb_id == 42
    assert result.confidence == 0.91
    assert result.usage["input_tokens"] == 120


def test_unknown_tmdb_id_is_rejected():
    gateway = GeminiRecommendationGateway(
        api_key="secret", client=FakeClient('{"tmdb_id": 404, "confidence": 1, "reason": "x"}'),
    )
    with pytest.raises(ValueError, match="TMDB"):
        gateway.select_final({}, [], candidates())


def test_max_output_tokens_is_configured():
    client = FakeClient('{"tmdb_id": 42, "confidence": 0.5, "reason": "x"}')
    gateway = GeminiRecommendationGateway(api_key="secret", client=client, max_output_tokens=256)
    gateway.select_final({}, [], candidates())
    assert gateway.max_output_tokens == 256
    assert client.models.calls[0]["config"].max_output_tokens == 256
