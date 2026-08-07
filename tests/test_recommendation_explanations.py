from backend.core.recommendation_explanations import build_recommendation_explanation
from backend.core.recommendations import TasteProfile


def test_explanation_uses_a_preferred_genre_and_tmdb_score():
    profile = TasteProfile(genre_affinity={"Drame": 0.8}, confidence=0.75)
    candidate = {
        "title": "Anatomie d'une chute",
        "genre_names": ["Drame", "Thriller"],
        "vote_average": 8.1,
        "reasons": ["genre_match"],
        "tmdb_id": 123,
    }

    explanation = build_recommendation_explanation(candidate, profile, {})

    assert "Anatomie d'une chute" in explanation
    assert "Drame" in explanation
    assert "8.1" in explanation
    assert "genre_match" not in explanation


def test_explanation_is_natural_when_no_profile_signal_exists():
    profile = TasteProfile(confidence=0)
    candidate = {
        "title": "Un film surprise",
        "genre_names": ["Aventure"],
        "vote_average": 7.4,
        "reasons": ["discovery_pick"],
        "tmdb_id": 456,
    }

    explanation = build_recommendation_explanation(candidate, profile, {})

    assert explanation.startswith("Un film surprise") or "Un film surprise" in explanation
    assert "discovery_pick" not in explanation
