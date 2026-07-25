from pathlib import Path

from frontend.theme import TOKENS, build_theme_css


def test_topbar_uses_root_logo_from_static_url():
    project_root = Path(__file__).resolve().parents[1]
    ui_source = (project_root / "frontend" / "ui.py").read_text(encoding="utf-8")
    app_source = (project_root / "main.py").read_text(encoding="utf-8")
    react_source = (project_root / "proto-ui" / "src" / "BackstagePrototype.jsx").read_text(encoding="utf-8")

    assert (project_root / "Logo.png").is_file()
    assert 'ui.image("/static/Logo.png")' in ui_source
    assert '@app.get("/static/Logo.png", include_in_schema=False)' in app_source
    assert '<img src="/static/Logo.png" alt="Backstage"' in react_source


def test_react_exposes_series_collection_switch():
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "proto-ui" / "src" / "BackstagePrototype.jsx").read_text(encoding="utf-8")

    assert "Films | Séries" in source
    assert "series-progress" in source


def test_react_preserves_series_progress_statuses():
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "proto-ui" / "src" / "library.js").read_text(encoding="utf-8")

    assert "'Terminée'" in source
    assert "'En cours'" in source


def test_react_series_completed_filter_accepts_feminine_status():
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "proto-ui" / "src" / "BackstagePrototype.jsx").read_text(encoding="utf-8")

    assert "['Terminé', 'Terminée'].includes(movie.status)" in source


def test_react_serializes_episode_updates_and_guards_series_loads():
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "proto-ui" / "src" / "BackstagePrototype.jsx").read_text(encoding="utf-8")

    assert "episodeUpdateQueue" in source
    assert "seriesRequestId" in source


def test_react_reconciles_queued_episode_successes_in_grid_and_drawer():
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "proto-ui" / "src" / "BackstagePrototype.jsx").read_text(encoding="utf-8")
    toggle_source = source[source.index("const toggleEpisode"):]

    assert "replaceEpisode(current, result.episode)" in toggle_source
    assert toggle_source.index("setMovies((current)") < toggle_source.index("const isCurrentSeries")
    assert "episodeIntents" in toggle_source
    assert "const isCurrentSeries" in toggle_source


def test_tokens_match_spec():
    assert TOKENS["--bg"] == "#faf6ef"
    assert TOKENS["--accent"] == "#7a2331"
    assert TOKENS["--accent-gold"] == "#c9a35c"
    assert TOKENS["--text"] == "#2b2420"


def test_build_theme_css_declares_all_tokens():
    css = build_theme_css()
    assert css.strip().startswith("<style>")
    for name, value in TOKENS.items():
        assert f"{name}: {value};" in css


def test_build_theme_css_defines_component_classes():
    css = build_theme_css()
    for class_name in (".bs-card", ".bs-title", ".bs-accent-btn", ".bs-outline-btn",
                       ".bs-badge", ".bs-badge-secondary", ".bs-poster-placeholder",
                       ".bs-topbar", ".bs-navlink"):
        assert class_name in css


def test_topbar_is_ivory_not_dark():
    css = build_theme_css()
    assert ".bs-topbar { background: var(--surface); border-bottom: 1px solid var(--border); }" in css
    assert ".bs-navlink { color: var(--text-muted) !important; opacity: 1; font-size: 0.85rem; }" in css
    assert ".bs-navlink.active { color: var(--accent) !important; border-bottom: 2px solid var(--accent-gold); }" in css
    assert "background: var(--text); color: var(--bg); }} .bs-topbar" not in css
