from backend.core.stats import compute_stats, find_duplicates, compute_enrichment_progression
from backend.core.models import Media


def _m(title, **kw):
    return Media(id=kw.pop("id", title), title=title, **kw)


def test_compute_stats_basic():
    medias = [
        _m("A", tmdb_ok=True, rating="8", categories=["Drame"], support="NAS", status="Terminé"),
        _m("B", tmdb_ok=False, categories=["Drame", "Comédie"], support="NAS"),
        _m("C", tmdb_ok=True, director="X", categories=["Comédie"]),
    ]
    s = compute_stats(medias)
    assert s["total"] == 3
    assert s["enriched"] == 2
    assert s["enriched_pct"] == 67
    assert s["rated"] == 1
    assert s["without_director"] == 2
    assert ("Drame", 2) in s["top_genres"]


def test_compute_stats_empty():
    s = compute_stats([])
    assert s["total"] == 0 and s["enriched_pct"] == 0


def test_find_duplicates_normalizes_accents_and_case():
    medias = [
        _m("Amélie", id="1"),
        _m("amelie", id="2"),
        _m("Inception", id="3"),
    ]
    dups = find_duplicates(medias)
    assert len(dups) == 1
    assert dups[0]["count"] == 2
    assert set(dups[0]["ids"]) == {"1", "2"}


def test_compute_enrichment_progression_cumulative_by_day():
    entries = [
        {"ts": "2026-07-01T10:00:00+00:00"},
        {"ts": "2026-07-01T18:00:00+00:00"},
        {"ts": "2026-07-03T09:00:00+00:00"},
    ]
    progression = compute_enrichment_progression(entries)
    assert progression == [
        {"date": "2026-07-01", "cumulative": 2},
        {"date": "2026-07-03", "cumulative": 3},
    ]


def test_compute_enrichment_progression_empty():
    assert compute_enrichment_progression([]) == []


def test_compute_enrichment_progression_ignores_entries_without_ts():
    entries = [{"ts": ""}, {"ts": "2026-07-01T10:00:00+00:00"}]
    progression = compute_enrichment_progression(entries)
    assert progression == [{"date": "2026-07-01", "cumulative": 1}]
