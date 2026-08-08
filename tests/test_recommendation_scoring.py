from datetime import datetime, timezone

from backend.core.recommendations import (
    TasteProfile,
    apply_recommendation_signal,
    apply_session_genre_delta,
    build_adaptive_question,
    is_candidate_eligible,
    record_compare_choice,
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


def test_a_film_with_no_genre_data_does_not_outscore_a_well_rated_film_during_cold_start():
    # At cold start (confidence 0, nothing known about the user's taste yet), a
    # candidate lacking genre tags must not outrank a better-rated candidate —
    # the neutral prior should not become a hidden advantage.
    profile = TasteProfile(confidence=0)
    no_genre = score_recommendation_candidate(
        {"tmdb_id": 1, "title": "Sans genre", "genre_ids": [], "vote_average": 7.0},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    well_rated = score_recommendation_candidate(
        {"tmdb_id": 2, "title": "Bien noté", "genre_ids": [18], "vote_average": 8.5},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    assert well_rated.score > no_genre.score


def test_a_multi_genre_film_is_not_penalized_for_genres_the_profile_does_not_know():
    # Unknown genres on a candidate must be ignored, not averaged in as zeros —
    # a film in a loved genre plus three unrated ones should score close to a
    # single-genre film in that same loved genre, not roughly half as well.
    profile = TasteProfile(genre_affinity={"Drame": 0.5}, confidence=1)
    single_genre = score_recommendation_candidate(
        {"tmdb_id": 1, "title": "Solo", "genre_ids": [18], "vote_average": 8.5},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    multi_genre = score_recommendation_candidate(
        {"tmdb_id": 2, "title": "Multi", "genre_ids": [18, 28, 878, 53], "vote_average": 8.5},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    assert multi_genre.score >= single_genre.score * 0.85


def test_watchlisted_candidate_is_boosted_more_than_the_old_five_percent_bonus():
    # A watchlisted title is an explicit "I want to see this" — it must move
    # the score by more than the historical 0.05 * 1.0 = 0.05 bonus, or
    # merging watchlist items into the pool (see _watchlist_candidate) is
    # pointless: they'd still rank at the very bottom.
    profile = TasteProfile(confidence=0)
    plain = score_recommendation_candidate(
        {"tmdb_id": 1, "title": "Plain", "genre_ids": [], "vote_average": 6.5},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    watchlisted = score_recommendation_candidate(
        {"tmdb_id": 2, "title": "Watchlisted", "genre_ids": [], "vote_average": 6.5},
        profile, {}, {"watchlisted_tmdb_ids": {2}}, datetime.now(timezone.utc),
    )
    assert watchlisted.score - plain.score >= 0.15


def test_record_compare_choice_rewards_picked_genres_and_penalizes_rejected_only_genres():
    session_preferences = {}

    record_compare_choice(session_preferences, picked_genre_ids=[878], rejected_genre_ids=[27])

    delta = session_preferences["genre_delta"]
    assert delta["Science-Fiction"] > 0
    assert delta["Horreur"] < 0


def test_record_compare_choice_does_not_penalize_a_genre_shared_by_both_films():
    # Both films being a Drame says nothing about Drame specifically — only
    # genres exclusive to the rejected film should be penalized.
    session_preferences = {}

    record_compare_choice(session_preferences, picked_genre_ids=[18, 878], rejected_genre_ids=[18, 27])

    delta = session_preferences["genre_delta"]
    assert "Drame" not in delta
    assert delta["Science-Fiction"] > 0
    assert delta["Horreur"] < 0


def test_record_compare_choice_accumulates_across_multiple_answers_in_a_session():
    session_preferences = {}

    record_compare_choice(session_preferences, picked_genre_ids=[878], rejected_genre_ids=[])
    record_compare_choice(session_preferences, picked_genre_ids=[878], rejected_genre_ids=[])

    assert session_preferences["genre_delta"]["Science-Fiction"] > 0.3


def test_apply_session_genre_delta_boosts_a_candidates_score_within_the_session():
    profile = TasteProfile(confidence=1)
    session_preferences = {"genre_delta": {"Science-Fiction": 0.5}}

    adjusted = apply_session_genre_delta(profile, session_preferences, datetime.now(timezone.utc))

    assert adjusted.genre_affinity["Science-Fiction"] > 0
    assert profile.genre_affinity == {}  # the durable, cross-session profile is untouched


def test_apply_session_genre_delta_is_a_no_op_without_a_delta():
    profile = TasteProfile(genre_affinity={"Drame": 0.4}, confidence=1)

    adjusted = apply_session_genre_delta(profile, {}, datetime.now(timezone.utc))

    assert adjusted.genre_affinity == profile.genre_affinity


def test_novelty_rewards_candidates_whose_genres_are_mostly_unknown_to_the_profile():
    # A confident profile facing a candidate entirely outside its known genres
    # should score it as more novel than one squarely inside a known genre.
    profile = TasteProfile(genre_affinity={"Drame": 0.2}, confidence=1)
    known = score_recommendation_candidate(
        {"tmdb_id": 1, "title": "Connu", "genre_ids": [18], "vote_average": 7},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    unknown = score_recommendation_candidate(
        {"tmdb_id": 2, "title": "Inconnu", "genre_ids": [16], "vote_average": 7},
        profile, {}, {}, datetime.now(timezone.utc),
    )
    assert "discovery_pick" in unknown.reasons
    assert "discovery_pick" not in known.reasons
