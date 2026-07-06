from datetime import date

from backend.core.processor import EnrichmentProcessor
from backend.core.models import Media
from backend.core.tmdb import TMDBClient


def _bare_processor() -> EnrichmentProcessor:
    # Évite __init__ (store/cache), mais _prepare_updates a besoin de self.tmdb
    # pour les helpers purs (get_director/get_genres/get_poster_url).
    p = object.__new__(EnrichmentProcessor)
    p.tmdb = object.__new__(TMDBClient)
    return p


def test_prepare_updates_returns_plain_field_values():
    p = _bare_processor()
    media = Media(id="x", title="Dune", release_date=date(2021, 10, 22))
    tmdb_data = {
        "release_date": "2021-10-22",
        "overview": "Un noble héritier...",
        "genres": [{"name": "Science-Fiction"}, {"name": "Aventure"}],
        "credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]},
    }

    updates, poster_url = p._prepare_updates(media, tmdb_data)

    assert updates["status"] == "À regarder"
    assert updates["support"] == "À télécharger"  # date passée, pas de cinéma
    assert updates["director"] == "Denis Villeneuve"
    assert updates["synopsis"] == "Un noble héritier..."
    assert updates["tmdb_ok"] is True
    assert isinstance(updates["categories"], list)


def test_prepare_updates_does_not_overwrite_existing_fields():
    p = _bare_processor()
    media = Media(id="x", title="Dune", director="Déjà rempli", status="Vu")
    updates, _ = p._prepare_updates(media, None)

    assert "director" not in updates
    assert "status" not in updates
