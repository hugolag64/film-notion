from datetime import date

import pytest

from backend.core.models import Media
from frontend.pages.library import filter_and_sort_medias


def _media(title, release_date=None, rating=None):
    return Media(id=title, title=title, release_date=release_date, rating=rating)


def test_filter_by_title_substring_case_insensitive():
    medias = [_media("Blade Runner"), _media("The Matrix"), _media("blade of glory")]
    result = filter_and_sort_medias(medias, "blade", "Titre")
    assert [m.title for m in result] == ["blade of glory", "Blade Runner"]


def test_empty_query_returns_all():
    medias = [_media("B"), _media("A")]
    result = filter_and_sort_medias(medias, "", "Titre")
    assert len(result) == 2


def test_sort_by_title_alphabetical_case_insensitive():
    medias = [_media("banana"), _media("Apple"), _media("cherry")]
    result = filter_and_sort_medias(medias, "", "Titre")
    assert [m.title for m in result] == ["Apple", "banana", "cherry"]


def test_sort_by_year_recent_first_missing_last():
    medias = [
        _media("Old", release_date=date(1990, 1, 1)),
        _media("New", release_date=date(2020, 1, 1)),
        _media("Undated"),
    ]
    result = filter_and_sort_medias(medias, "", "Année")
    assert [m.title for m in result] == ["New", "Old", "Undated"]


def test_sort_by_rating_desc_missing_last():
    medias = [
        _media("Mid", rating="6"),
        _media("Top", rating="9/10"),
        _media("Unrated"),
    ]
    result = filter_and_sort_medias(medias, "", "Note")
    assert [m.title for m in result] == ["Top", "Mid", "Unrated"]


def test_unknown_sort_key_raises():
    with pytest.raises(ValueError):
        filter_and_sort_medias([], "", "Popularité")
