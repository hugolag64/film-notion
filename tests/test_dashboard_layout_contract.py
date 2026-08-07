from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_header_uses_compact_primary_navigation_and_right_aligned_utilities():
    source = (ROOT / "proto-ui/src/BackstagePrototype.jsx").read_text(encoding="utf-8")
    assert "['dashboard', 'Accueil']" in source
    assert "['library', 'Bibliothèque']" not in source
    assert 'title="Changer de thème"' in source
    assert 'aria-label="Navigation principale"' in source
    assert 'border-b-2 border-[#635bff]' in source
    assert 'FILM VAULT' not in source
    assert '+ Ajouter un film' not in source
    assert 'Ajouter un film' in source
    assert source.index('title="Changer de thème"') > source.index('title="Ouvrir le compte"')
    assert 'grid-cols-[1fr_auto_1fr]' in source
    assert 'absolute left-1/2' not in source


def test_dashboard_exposes_seerr_request_queue_and_tmdb_request_action():
    dashboard = (ROOT / "proto-ui/src/components/DashboardHome.jsx").read_text(encoding="utf-8")
    preview = (ROOT / "proto-ui/src/components/TMDBMoviePreview.jsx").read_text(encoding="utf-8")
    api = (ROOT / "proto-ui/src/api.js").read_text(encoding="utf-8")
    assert "Mes demandes" in dashboard
    assert "Annuler la demande" in dashboard
    assert "Demander à Seerr" in preview
    assert "createSeerrRequest" in api
    assert "cancelSeerrRequest" in api
    assert "RequestDetailModal" in dashboard
    assert "onOpenRequest" in dashboard


def test_continue_watching_is_a_horizontal_compact_row():
    source = (ROOT / "proto-ui/src/components/DashboardHome.jsx").read_text(encoding="utf-8")
    assert 'aria-label="Reprises en cours"' in source
    assert "grid gap-4 md:grid-cols-2" not in source
    assert "flex gap-3 overflow-x-auto" in source
