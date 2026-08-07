from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_header_uses_compact_primary_navigation_and_right_aligned_utilities():
    source = (ROOT / "proto-ui/src/BackstagePrototype.jsx").read_text(encoding="utf-8")
    assert "['dashboard', 'Accueil']" in source
    assert "['library', 'Bibliothèque']" not in source
    assert 'title="Changer de thème"' in source
    assert 'aria-label="Navigation principale"' in source


def test_continue_watching_is_a_horizontal_compact_row():
    source = (ROOT / "proto-ui/src/components/DashboardHome.jsx").read_text(encoding="utf-8")
    assert 'aria-label="Reprises en cours"' in source
    assert "grid gap-4 md:grid-cols-2" not in source
    assert "flex gap-3 overflow-x-auto" in source
