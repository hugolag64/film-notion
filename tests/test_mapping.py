from backend.core.mapping import Props, validate_schema, REQUIRED_PROPERTIES, GENRE_TAG_RULES


def _valid_db():
    return {name: {"type": t} for name, t in REQUIRED_PROPERTIES.items()}


def test_valid_schema_has_no_problems():
    assert validate_schema(_valid_db()) == []


def test_missing_property_is_reported():
    db = _valid_db()
    del db[Props.DIRECTOR]
    problems = validate_schema(db)
    assert any("Réalisateur" in p for p in problems)


def test_wrong_type_is_reported():
    db = _valid_db()
    db[Props.TMDB_OK] = {"type": "rich_text"}  # devrait être checkbox
    problems = validate_schema(db)
    assert any("TMDB_OK" in p for p in problems)


def test_genre_rules_cover_known_genres():
    assert GENRE_TAG_RULES["Comédie"]
    assert GENRE_TAG_RULES["Horreur"]
