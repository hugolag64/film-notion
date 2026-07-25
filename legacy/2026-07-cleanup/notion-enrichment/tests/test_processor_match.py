from datetime import date

from backend.core.processor import EnrichmentProcessor
from backend.core.models import Media


def _bare_processor() -> EnrichmentProcessor:
    # Évite __init__ (qui crée TMDBClient/CacheService et requiert des clés/fichiers)
    return object.__new__(EnrichmentProcessor)


def _media(title="Dune", year=2021):
    return Media(id="x", title=title, release_date=date(year, 1, 1))


def test_year_disambiguates_homonyms():
    p = _bare_processor()
    results = [
        {"id": 1, "title": "Dune", "release_date": "2021-10-22", "popularity": 50},
        {"id": 2, "title": "Dune", "release_date": "1984-12-14", "popularity": 20},
    ]
    best = p._find_best_match(_media(year=2021), results)
    assert best["id"] == 1


def test_no_match_when_titles_differ():
    p = _bare_processor()
    results = [{"id": 9, "title": "Avatar", "release_date": "2009-01-01", "popularity": 80}]
    assert p._find_best_match(_media(), results) is None


def test_empty_results_returns_none():
    p = _bare_processor()
    assert p._find_best_match(_media(), []) is None


def test_exact_title_match_without_year():
    p = _bare_processor()
    m = Media(id="x", title="Inception")  # pas de date
    results = [{"id": 27205, "title": "Inception", "release_date": "2010-07-15", "popularity": 90}]
    assert p._find_best_match(m, results)["id"] == 27205


def test_map_genres_to_tags():
    p = _bare_processor()
    tags = p._map_genres_to_tags(["Comédie", "Inconnu"])
    assert "😌 Détente" in tags
    # Règle combinée horreur + thriller
    assert "⚠️ Film dur" in p._map_genres_to_tags(["Horreur", "Thriller"])


def test_result_year_parsing():
    assert EnrichmentProcessor._result_year({"release_date": "2021-10-22"}) == 2021
    assert EnrichmentProcessor._result_year({"release_date": ""}) is None
