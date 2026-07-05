from frontend.theme import TOKENS, build_theme_css


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
                       ".bs-badge", ".bs-poster-placeholder", ".bs-topbar", ".bs-navlink"):
        assert class_name in css
