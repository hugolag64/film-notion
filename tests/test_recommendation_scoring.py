from datetime import datetime, timezone

from backend.core.recommendations import (
    TasteProfile,
    apply_recommendation_signal,
    build_adaptive_question,
    is_candidate_eligible,
    score_recommendation_candidate,
)


def test_not_now_is_not_a_permanent_exclusion():
    preference = {"disposition": "not_now", "expires_at": "2026-09-01T00:00:00+00:00"}
    assert is_candidate_eligible(preference, datetime(2026, 8, 10, tzinfo=timezone.utc)) is True


def test_hard_reject_is_excluded():
    preference = {"disposition": "hard_reject", "expires_at": None}
    assert is_candidate_eligible(preference, datetime.now(timezone.utc)) is False


def test_less_like_this_decays_and_session_preference_wins():
    profile = TasteProfile(genre_affinity={"Comédie": 0.8, "Drame": 0.1}, confidence=1)
    candidate = {"tmdb_id": 1, "title": "Drame", "genre_ids": [18], "vote_average": 7}
    negative = apply_recommendation_signal(profile, "less_like_this", "Drame", -0.45, datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert negative.genre_affinity["Drame"] < profile.genre_affinity["Drame"]
    scored = score_recommendation_candidate(
        candidate, negative, {"genre": "Drame"}, {}, datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    assert "session_match" in scored.reasons


def test_question_pair_prefers_diverse_genres():
    profile = TasteProfile(confidence=0.5)
    candidates = [
        {"tmdb_id": 1, "title": "A", "genre_ids": [35], "vote_average": 8},
        {"tmdb_id": 2, "title": "B", "genre_ids": [35], "vote_average": 7.9},
        {"tmdb_id": 3, "title": "C", "genre_ids": [18], "vote_average": 7.5},
    ]
    question = build_adaptive_question(candidates, profile, {})
    assert question is not None
    assert {item["tmdb_id"] for item in question["options"]} == {1, 3}
