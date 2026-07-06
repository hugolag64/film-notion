from backend.core.mapping import FIELD_LABELS, GENRE_TAG_RULES, is_series


def test_genre_rules_cover_known_genres():
    assert GENRE_TAG_RULES["Comédie"]
    assert GENRE_TAG_RULES["Horreur"]


def test_field_labels_cover_diff_fields():
    for field in ("status", "support", "director", "synopsis", "release_date", "categories", "tags", "tmdb_ok"):
        assert field in FIELD_LABELS


def test_is_series_matches_known_types():
    assert is_series("Série") is True
    assert is_series("Film") is False
    assert is_series(None) is False
