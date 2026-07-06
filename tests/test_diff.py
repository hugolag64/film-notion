from backend.core.diff import summarize_changes
from backend.core.models import Media


def test_new_values_are_reported_as_changes():
    media = Media(id="x", title="Dune")  # tout vide
    updates = {
        "director": "Denis Villeneuve",
        "status": "À regarder",
        "categories": ["SF", "Aventure"],
        "tmdb_ok": True,
    }

    changes = summarize_changes(media, updates)
    fields = {c["field"]: c for c in changes}

    assert fields["Réalisateur"]["new"] == "Denis Villeneuve"
    assert fields["Réalisateur"]["old"] == "—"
    assert fields["Catégorie"]["new"] == "SF, Aventure"
    assert fields["TMDB_OK"]["new"] == "Oui"


def test_unchanged_values_are_not_reported():
    media = Media(id="x", title="Dune", director="Denis Villeneuve", cover_url="http://existing")
    updates = {"director": "Denis Villeneuve"}

    changes = summarize_changes(media, updates)
    assert changes == []


def test_poster_change_reported_when_no_existing_cover():
    media = Media(id="x", title="Dune")
    changes = summarize_changes(media, {}, poster_url="http://tmdb/poster.jpg")
    assert changes == [{"field": "Couverture", "old": "—", "new": "Affiche TMDB"}]


def test_poster_change_not_reported_when_cover_already_set():
    media = Media(id="x", title="Dune", cover_url="http://existing")
    changes = summarize_changes(media, {}, poster_url="http://tmdb/poster.jpg")
    assert changes == []
