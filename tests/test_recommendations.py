from datetime import datetime, timezone
from random import Random

from backend.core.models import Media, RecommendationEvent, UserMediaState
from backend.core.recommendations import (
    RecommendationCandidate, TasteProfile, build_local_question, build_taste_profile,
    choose_from_top, score_candidate,
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
