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


from backend.core.recommendation_explanations import build_guided_explanation, is_readable_title


def test_titles_without_latin_letters_are_not_readable():
    assert is_readable_title("The Thing")
    assert is_readable_title("Amélie")
    assert is_readable_title("M3GAN")
    assert not is_readable_title("أوسكار: عودة الماموث")
    assert not is_readable_title("千と千尋の神隠し")
    assert not is_readable_title("")


def test_guided_explanation_quotes_the_answers_the_film_actually_matches():
    preferences = {"mood": "intense", "genres": ["Science-Fiction"], "refinement": "Mystère"}
    candidate = {"title": "The Thing", "release_date": "1982-06-25", "vote_average": 8.1,
                 "genre_ids": [27, 9648, 878]}

    explanation = build_guided_explanation(candidate, preferences)

    assert "The Thing" in explanation
    assert "science-fiction" in explanation
    assert "énigme" in explanation
    assert "prenant" in explanation
    assert "8,1/10" in explanation
    assert "TMDB" not in explanation


def test_guided_explanation_is_honest_when_the_film_matches_nothing():
    preferences = {"mood": "light", "genres": ["Comédie"]}
    candidate = {"title": "War Machine", "vote_average": 7.5, "genre_ids": [28, 10752]}

    explanation = build_guided_explanation(candidate, preferences)

    assert "War Machine" in explanation
    assert "comédie" not in explanation.lower().split(":")[-1]
    assert "change" in explanation or "écart" in explanation


def test_animation_alone_does_not_make_a_film_light_or_funny():
    preferences = {"mood": "light", "genres": ["Science-Fiction"]}
    candidate = {"title": "The End of Evangelion", "release_date": "1997-07-19",
                 "vote_average": 8.3, "genre_ids": [16, 878, 18]}

    explanation = build_guided_explanation(candidate, preferences)

    assert "science-fiction" in explanation
    assert "léger" not in explanation
