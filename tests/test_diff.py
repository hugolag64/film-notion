from datetime import date

from backend.core.diff import summarize_changes
from backend.core.models import Media
from backend.core.mapping import Props


def test_summarize_detects_new_values():
    media = Media(id="x", title="Dune")  # tout vide
    updates = {
        Props.DIRECTOR: {"rich_text": [{"text": {"content": "Denis Villeneuve"}}]},
        Props.STATUS: {"select": {"name": "À regarder"}},
        Props.CATEGORY: {"multi_select": [{"name": "SF"}, {"name": "Aventure"}]},
        Props.TMDB_OK: {"checkbox": True},
    }
    changes = summarize_changes(media, updates, poster_url="http://img")
    fields = {c["field"]: c for c in changes}
    assert fields[Props.DIRECTOR]["new"] == "Denis Villeneuve"
    assert fields[Props.DIRECTOR]["old"] == "—"
    assert fields[Props.CATEGORY]["new"] == "SF, Aventure"
    assert "Couverture" in fields


def test_summarize_skips_unchanged():
    media = Media(id="x", title="Dune", director="Denis Villeneuve", cover_url="http://existing")
    updates = {
        Props.DIRECTOR: {"rich_text": [{"text": {"content": "Denis Villeneuve"}}]},
    }
    # même réalisateur + couverture déjà présente -> aucun changement
    assert summarize_changes(media, updates, poster_url="http://img") == []
