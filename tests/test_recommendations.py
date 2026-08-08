from datetime import datetime, timezone
from random import Random

from backend.core.models import Media, RecommendationEvent, UserMediaState
from backend.core.recommendations import (
    RecommendationCandidate, TasteProfile, _rating_value, build_local_question,
    build_taste_profile, choose_from_top, score_candidate,
)


def media(media_id, title, categories):
    return Media(id=media_id, title=title, categories=categories, type="Film")


def state(media_id, rating=None, status=None, favorite=False):
    return UserMediaState(
        backstage_user_id="hugo", media_id=media_id, rating=rating, status=status,
        is_favorite=favorite, last_interacted_at=datetime.now(timezone.utc),
    )


def test_profile_prefers_genres_with_high_personal_ratings():
    profile = build_taste_profile(
        [media("a", "A", ["Science-Fiction"]), media("b", "B", ["Drame"])],
        [state("a", "5"), state("b", "2")], [], [], datetime.now(timezone.utc),
    )

    assert profile.genre_affinity["Science-Fiction"] > profile.genre_affinity["Drame"]


def test_rating_value_parses_the_legacy_ten_point_star_scale():
    # Notion V1 import left ratings as up to 10 star emoji; the engine must
    # read them on their native /10 scale, remapped to Backstage's /5.
    assert _rating_value("⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️") == 4.0
    assert _rating_value("⭐️") == 0.5
    assert _rating_value("⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️") == 5.0


def test_rating_value_still_parses_the_current_five_point_scale():
    assert _rating_value("3.5") == 3.5
    assert _rating_value("5") == 5.0


def test_rating_value_returns_none_for_blank_or_unparseable_text():
    assert _rating_value("") is None
    assert _rating_value("   ") is None
    assert _rating_value("n/a") is None
    assert _rating_value(None) is None


def test_a_revoir_status_is_a_strong_positive_signal_even_without_a_rating():
    # "A revoir" (want to watch again) is the strongest positive verdict a user
    # can leave without a numeric rating; it must outweigh a plain "Terminé".
    profile = build_taste_profile(
        [media("a", "A", ["Horreur"]), media("b", "B", ["Comédie"])],
        [state("a", status="A revoir"), state("b", status="Terminé")],
        [], [], datetime.now(timezone.utc),
    )

    assert profile.genre_affinity["Horreur"] > profile.genre_affinity["Comédie"]


def test_a_regarder_status_contributes_no_signal_at_all():
    # "À regarder" only means "not watched yet" — it is not a verdict, and must
    # not silently drag the genre's average toward zero.
    profile = build_taste_profile(
        [media("a", "A", ["Horreur"])],
        [state("a", status="À regarder")],
        [], [], datetime.now(timezone.utc),
    )

    assert "Horreur" not in profile.genre_affinity
    assert profile.confidence == 0


def test_ratings_are_centered_on_the_users_own_average_not_zero():
    # The same absolute rating (4/5) for the same genre must read very
    # differently depending on the user's own baseline: near-neutral for a
    # generous rater, strongly positive for a harsh one. The personal
    # baseline matters more than the absolute number.
    generous_rater = build_taste_profile(
        [media("a", "A", ["Drame"]), media("b", "B", ["Comédie"]), media("c", "C", ["Action"])],
        [state("a", "4"), state("b", "4.5"), state("c", "4")],
        [], [], datetime.now(timezone.utc),
    )
    harsh_rater = build_taste_profile(
        [media("a", "A", ["Drame"]), media("b", "B", ["Comédie"]), media("c", "C", ["Action"])],
        [state("a", "4"), state("b", "2"), state("c", "2")],
        [], [], datetime.now(timezone.utc),
    )

    assert generous_rater.genre_affinity["Drame"] < harsh_rater.genre_affinity["Drame"]


def test_less_like_event_reduces_genre_affinity():
    profile = build_taste_profile(
        [media("a", "A", ["Horreur"])], [state("a", "4")], [], [
            RecommendationEvent(
                id="e", backstage_user_id="hugo", media_id="a",
                event_type="less_like_this", created_at=datetime.now(timezone.utc),
            ),
        ], datetime.now(timezone.utc),
    )

    assert profile.genre_affinity["Horreur"] < 0.8


def test_seen_candidate_is_not_eligible_and_watchlist_bonus_is_small():
    profile = build_taste_profile([], [], [], [], datetime.now(timezone.utc))
    seen = score_candidate({"tmdb_id": 1, "title": "Vu", "genre_ids": []}, profile, {}, {1}, set(), datetime.now(timezone.utc))
    watchlisted = score_candidate({"tmdb_id": 2, "title": "À voir", "genre_ids": []}, profile, {}, set(), {2}, datetime.now(timezone.utc))
    plain = score_candidate({"tmdb_id": 3, "title": "Autre", "genre_ids": []}, profile, {}, set(), set(), datetime.now(timezone.utc))

    assert seen.score < 0
    assert watchlisted.score - plain.score <= 0.06


def test_choice_uses_only_top_candidates_and_is_seedable():
    candidates = [
        score_candidate({"tmdb_id": i, "title": str(i), "genre_ids": [], "vote_average": i}, build_taste_profile([], [], [], [], datetime.now(timezone.utc)), {}, set(), set(), datetime.now(timezone.utc))
        for i in range(1, 10)
    ]

    choice = choose_from_top(candidates, Random(4), top_n=3)

    assert choice.tmdb_id in {7, 8, 9}


def _question_candidates():
    return [
        RecommendationCandidate(
            tmdb_id=1, title="Film A", score=0.9, genre_ids=[35], vote_average=7.2,
            release_date="2022-01-01",
        ),
        RecommendationCandidate(
            tmdb_id=2, title="Film B", score=0.8, genre_ids=[18], vote_average=7.4,
            release_date="1998-01-01",
        ),
        RecommendationCandidate(
            tmdb_id=3, title="Film C", score=0.7, genre_ids=[27], vote_average=6.9,
            release_date="2018-01-01",
        ),
    ]


def test_build_local_question_renders_movie_comparison():
    question = build_local_question("movie_compare", _question_candidates(), TasteProfile(), {})
    assert question["type"] == "compare"
    assert question["axis"] == "movie_compare"
    assert len(question["options"]) == 2
    assert {option["tmdb_id"] for option in question["options"]} == {1, 2}


def test_build_local_question_renders_non_movie_choices():
    for axis in ("mood", "genre", "era"):
        question = build_local_question(axis, _question_candidates(), TasteProfile(), {})
        assert question["type"] == "choice"
        assert question["axis"] == axis
        assert len(question["options"]) >= 2
        assert all(option["answer"] for option in question["options"])
