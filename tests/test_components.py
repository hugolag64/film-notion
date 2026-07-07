from backend.core.models import Media
from frontend.components import primary_genre, rating_badge_text


def _media(**overrides):
    fields = {"id": "1", "title": "Test"}
    fields.update(overrides)
    return Media(**fields)


def test_rating_badge_text_with_rating():
    assert rating_badge_text(_media(rating="8/10")) == "⭐ 8/10"


def test_rating_badge_text_without_rating():
    assert rating_badge_text(_media(rating=None)) is None


def test_primary_genre_with_categories():
    assert primary_genre(_media(categories=["Drame", "Thriller"])) == "Drame"


def test_primary_genre_without_categories():
    assert primary_genre(_media(categories=[])) is None
