import asyncio
from datetime import datetime, timezone

from backend import api
from backend.auth_api import AuthContext
from backend.core.models import Media
from backend.core.recommendations import TasteProfile
from backend.core.store import MediaStore


def _store(tmp_path) -> MediaStore:
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def test_pool_seed_is_generated_once_and_then_stable_within_a_session():
    preferences = {}
    first = api._pool_seed(preferences)

    assert first["page"] in range(1, 6)
    assert first["sort_by"] in {"popularity.desc", "vote_average.desc", "vote_count.desc"}
    assert preferences["pool_seed"] == first

    second = api._pool_seed(preferences)

    assert second == first


def test_answered_genre_takes_priority_over_the_durable_profile():
    profile = TasteProfile(genre_affinity={"Horreur": 0.9}, confidence=1)
    preferences = {"genre": "Comédie"}

    params = api._steer_pool_params(preferences, profile, datetime.now(timezone.utc))

    assert params["with_genres"] == [35]


def test_no_answered_genre_falls_back_to_the_profiles_top_liked_genres():
    profile = TasteProfile(
        genre_affinity={"Drame": 0.4, "Horreur": -0.3, "Science-Fiction": 0.2, "Comédie": 0.1},
        confidence=1,
    )

    params = api._steer_pool_params({}, profile, datetime.now(timezone.utc))

    assert set(params["with_genres"]) == {18, 878, 35}
    assert 27 not in params["with_genres"]  # a disliked genre must not steer discovery


def test_no_genre_signal_at_all_omits_the_with_genres_filter():
    profile = TasteProfile(confidence=0)

    params = api._steer_pool_params({}, profile, datetime.now(timezone.utc))

    assert "with_genres" not in params


def test_era_recent_sets_a_lower_release_date_bound():
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)

    params = api._steer_pool_params({"era": "recent"}, TasteProfile(), now)

    assert params["release_date_gte"] == "2020-01-01"
    assert "release_date_lte" not in params


def test_era_classic_sets_an_upper_release_date_bound():
    params = api._steer_pool_params({"era": "classic"}, TasteProfile(), datetime.now(timezone.utc))

    assert params["release_date_lte"] == "2005-12-31"
    assert "release_date_gte" not in params


def test_no_era_answer_leaves_release_date_unbounded():
    params = api._steer_pool_params({}, TasteProfile(), datetime.now(timezone.utc))

    assert "release_date_gte" not in params
    assert "release_date_lte" not in params


def test_tmdb_path_is_stripped_from_a_stored_poster_url():
    assert api._tmdb_path_from_stored_url("https://image.tmdb.org/t/p/w500/abc.jpg") == "/abc.jpg"


def test_tmdb_path_is_stripped_from_a_stored_backdrop_url():
    assert api._tmdb_path_from_stored_url("https://image.tmdb.org/t/p/w1280/abc.jpg") == "/abc.jpg"


def test_tmdb_path_is_none_for_a_missing_or_unrecognized_url():
    assert api._tmdb_path_from_stored_url(None) is None
    assert api._tmdb_path_from_stored_url("https://example.com/poster.jpg") is None


def test_resolve_compare_choice_splits_picked_from_rejected():
    compare_pair = [
        {"tmdb_id": 1, "genre_ids": [878]},
        {"tmdb_id": 2, "genre_ids": [27]},
    ]

    result = api._resolve_compare_choice(compare_pair, picked_tmdb_id=1)

    assert result == ([878], [27])


def test_resolve_compare_choice_handles_picking_the_second_option():
    compare_pair = [
        {"tmdb_id": 1, "genre_ids": [878]},
        {"tmdb_id": 2, "genre_ids": [27]},
    ]

    result = api._resolve_compare_choice(compare_pair, picked_tmdb_id=2)

    assert result == ([27], [878])


def test_resolve_compare_choice_returns_none_when_pair_is_missing_or_stale():
    assert api._resolve_compare_choice(None, picked_tmdb_id=1) is None
    assert api._resolve_compare_choice([], picked_tmdb_id=1) is None
    assert api._resolve_compare_choice([{"tmdb_id": 9, "genre_ids": []}], picked_tmdb_id=1) is None
    assert api._resolve_compare_choice(
        [{"tmdb_id": 9, "genre_ids": []}, {"tmdb_id": 10, "genre_ids": []}], picked_tmdb_id=1,
    ) is None


def test_watchlist_candidate_is_shaped_like_a_tmdb_discover_result():
    media = Media(
        id="m1", tmdb_id=42, title="Un film en watchlist",
        categories=["Drame", "Un genre inconnu"], synopsis="Résumé.",
        cover_url="https://image.tmdb.org/t/p/w500/poster.jpg",
        backdrop_url="https://image.tmdb.org/t/p/w1280/backdrop.jpg",
    )

    candidate = api._watchlist_candidate(media)

    assert candidate["tmdb_id"] == 42
    assert candidate["title"] == "Un film en watchlist"
    assert candidate["genre_ids"] == [18]  # the unknown category name is dropped, not guessed
    assert candidate["poster_path"] == "/poster.jpg"
    assert candidate["backdrop_path"] == "/backdrop.jpg"


class FakeCompareTMDB:
    """Always returns the same 4 films, so a movie_compare pick's effect on
    subsequent scoring can be observed without genuine TMDB variety masking it."""

    async def discover_movies(self, **kwargs):
        return [
            {"tmdb_id": 1, "title": "Film SF A", "genre_ids": [878], "vote_average": 7.0},
            {"tmdb_id": 2, "title": "Film Horreur A", "genre_ids": [27], "vote_average": 7.0},
            {"tmdb_id": 3, "title": "Film SF B", "genre_ids": [878], "vote_average": 6.8},
            {"tmdb_id": 4, "title": "Film Horreur B", "genre_ids": [27], "vote_average": 6.8},
        ]


def test_picking_a_movie_compare_option_persists_a_genre_delta_on_the_session(tmp_path, monkeypatch):
    store = _store(tmp_path)
    # role=admin sidesteps the recommendation-quota's timezone lookup, which
    # this dev machine's Python install cannot resolve (tracked separately,
    # unrelated to this test).
    current = AuthContext(user={"id": "hugo", "role": "admin"}, session_id="auth", token="token")
    monkeypatch.setattr(api, "TMDBClient", FakeCompareTMDB)
    monkeypatch.setattr(api, "_gemini_gateway", lambda: type("DisabledGateway", (), {"enabled": False})())

    started = asyncio.run(api.start_recommendation_session(current, store))
    assert started["question"]["axis"] == "movie_compare"
    picked_id = started["question"]["options"][0]["tmdb_id"]

    asyncio.run(api.answer_recommendation(
        started["session"]["id"],
        api.RecommendationAnswerRequest(answer="picked", value=str(picked_id)),
        current, store,
    ))

    session = asyncio.run(store.get_recommendation_session(started["session"]["id"]))
    assert session.session_preferences.get("genre_delta")


def test_picking_a_movie_compare_option_boosts_its_genre_for_the_rest_of_the_session(tmp_path, monkeypatch):
    store = _store(tmp_path)
    current = AuthContext(user={"id": "hugo", "role": "admin"}, session_id="auth", token="token")
    monkeypatch.setattr(api, "TMDBClient", FakeCompareTMDB)
    monkeypatch.setattr(api, "_gemini_gateway", lambda: type("DisabledGateway", (), {"enabled": False})())

    started = asyncio.run(api.start_recommendation_session(current, store))
    sf_option = next(o for o in started["question"]["options"] if o["genre_ids"] == [878])
    asyncio.run(api.answer_recommendation(
        started["session"]["id"],
        api.RecommendationAnswerRequest(answer="picked", value=str(sf_option["tmdb_id"])),
        current, store,
    ))

    session = asyncio.run(store.get_recommendation_session(started["session"]["id"]))
    pool = asyncio.run(api._recommendation_pool(current, store, session.session_preferences))
    remaining_sf = next(c for c in pool if c.tmdb_id == 3)      # the unshown SF film
    remaining_horreur = next(c for c in pool if c.tmdb_id == 4)  # the unshown Horreur film

    # Both films have an identical vote_average (6.8); only the in-session
    # genre delta from the earlier pick can explain SF now scoring higher.
    assert remaining_sf.score > remaining_horreur.score
