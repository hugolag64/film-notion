from datetime import date

import pytest

from backend.core.models import Media
from frontend.pages.library import (
    apply_filters,
    distinct_filter_options,
    filter_and_sort_medias,
    get_library_state,
    paginate_medias,
    total_pages,
)


def _media(title, release_date=None, rating=None, categories=None, status=None, support=None):
    return Media(
        id=title,
        title=title,
        release_date=release_date,
        rating=rating,
        categories=categories or [],
        status=status,
        support=support,
    )


def test_filter_by_title_substring_case_insensitive():
    medias = [_media("Blade Runner"), _media("The Matrix"), _media("blade of glory")]
    result = filter_and_sort_medias(medias, "blade", "Titre")
    # Case-insensitive ascending sort: "blade of glory" < "Blade Runner" ('o' < 'r' after shared "blade " prefix).
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


def test_sort_by_date_added_most_recent_first():
    medias = [_media("First"), _media("Second"), _media("Third")]
    result = filter_and_sort_medias(medias, "", "Date d'ajout")
    assert [m.title for m in result] == ["Third", "Second", "First"]


def test_sort_by_date_added_respects_filter():
    medias = [_media("First"), _media("Blade"), _media("Third")]
    result = filter_and_sort_medias(medias, "bla", "Date d'ajout")
    assert [m.title for m in result] == ["Blade"]


def test_unknown_sort_key_raises():
    with pytest.raises(ValueError):
        filter_and_sort_medias([], "", "Popularité")


def test_total_pages_exact_multiple():
    assert total_pages(48, page_size=24) == 2


def test_total_pages_rounds_up():
    assert total_pages(49, page_size=24) == 3


def test_total_pages_empty_is_one():
    assert total_pages(0, page_size=24) == 1


def test_paginate_medias_first_page():
    medias = [_media(str(i)) for i in range(30)]
    page = paginate_medias(medias, 1, page_size=24)
    assert [m.title for m in page] == [str(i) for i in range(24)]


def test_paginate_medias_second_page_partial():
    medias = [_media(str(i)) for i in range(30)]
    page = paginate_medias(medias, 2, page_size=24)
    assert [m.title for m in page] == [str(i) for i in range(24, 30)]


def test_paginate_medias_out_of_range_page_is_empty():
    medias = [_media(str(i)) for i in range(10)]
    assert paginate_medias(medias, 5, page_size=24) == []


def test_get_library_state_defaults_on_first_call():
    ui_state = {}
    state = get_library_state(ui_state)
    assert state == {
        "query": "",
        "sort": "Titre",
        "page": 1,
        "filters": {"genres": [], "statuses": [], "supports": []},
    }


def test_get_library_state_persists_across_calls():
    ui_state = {}
    state1 = get_library_state(ui_state)
    state1["sort"] = "Date d'ajout"
    state1["page"] = 3

    state2 = get_library_state(ui_state)
    assert state2["sort"] == "Date d'ajout"
    assert state2["page"] == 3


def test_get_library_state_independent_per_ui_state_dict():
    ui_state_a = {}
    ui_state_b = {}
    get_library_state(ui_state_a)["sort"] = "Note"

    state_b = get_library_state(ui_state_b)
    assert state_b["sort"] == "Titre"


def test_distinct_filter_options_categories_flattened_and_sorted():
    medias = [
        _media("A", categories=["Drame", "Action"]),
        _media("B", categories=["Comédie"]),
        _media("C", categories=["Action"]),
    ]
    assert distinct_filter_options(medias, "categories") == ["Action", "Comédie", "Drame"]


def test_distinct_filter_options_status_skips_missing():
    medias = [_media("A", status="Terminé"), _media("B", status=None), _media("C", status="À revoir")]
    assert distinct_filter_options(medias, "status") == sorted(["Terminé", "À revoir"])


def test_distinct_filter_options_empty_list():
    assert distinct_filter_options([], "categories") == []


def test_apply_filters_no_filters_returns_all():
    medias = [_media("A"), _media("B")]
    result = apply_filters(medias, {"genres": [], "statuses": [], "supports": []})
    assert result == medias


def test_apply_filters_genre_or_logic():
    medias = [
        _media("A", categories=["Action"]),
        _media("B", categories=["Comédie"]),
        _media("C", categories=["Drame"]),
    ]
    result = apply_filters(medias, {"genres": ["Action", "Comédie"], "statuses": [], "supports": []})
    assert [m.title for m in result] == ["A", "B"]


def test_apply_filters_status_exact_match():
    medias = [_media("A", status="Terminé"), _media("B", status="À revoir")]
    result = apply_filters(medias, {"genres": [], "statuses": ["Terminé"], "supports": []})
    assert [m.title for m in result] == ["A"]


def test_apply_filters_support_exact_match():
    medias = [_media("A", support="NAS"), _media("B", support="Cinéma")]
    result = apply_filters(medias, {"genres": [], "statuses": [], "supports": ["NAS"]})
    assert [m.title for m in result] == ["A"]


def test_apply_filters_and_logic_across_dimensions():
    medias = [
        _media("A", categories=["Action"], status="Terminé"),
        _media("B", categories=["Action"], status="À revoir"),
        _media("C", categories=["Drame"], status="Terminé"),
    ]
    result = apply_filters(medias, {"genres": ["Action"], "statuses": ["Terminé"], "supports": []})
    assert [m.title for m in result] == ["A"]


def test_apply_filters_missing_dimension_key_treated_as_empty():
    medias = [_media("A"), _media("B")]
    assert apply_filters(medias, {}) == medias


def test_filter_and_sort_medias_applies_filters_before_sort():
    medias = [
        _media("Zeta", categories=["Action"]),
        _media("Alpha", categories=["Action"]),
        _media("Beta", categories=["Drame"]),
    ]
    result = filter_and_sort_medias(medias, "", "Titre", filters={"genres": ["Action"], "statuses": [], "supports": []})
    assert [m.title for m in result] == ["Alpha", "Zeta"]


def test_filter_and_sort_medias_combines_search_and_filters():
    medias = [
        _media("Blade Runner", categories=["Science-Fiction"]),
        _media("Blade of Glory", categories=["Comédie"]),
    ]
    result = filter_and_sort_medias(medias, "blade", "Titre", filters={"genres": ["Comédie"], "statuses": [], "supports": []})
    assert [m.title for m in result] == ["Blade of Glory"]


def test_filter_and_sort_medias_no_filters_arg_behaves_as_before():
    medias = [_media("B"), _media("A")]
    result = filter_and_sort_medias(medias, "", "Titre")
    assert [m.title for m in result] == ["A", "B"]
