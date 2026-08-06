from pathlib import Path


UI_SOURCE = Path(__file__).parents[1] / "proto-ui" / "src" / "BackstagePrototype.jsx"


def test_resume_section_is_not_rendered_in_catalogue_but_detail_keeps_playback_action():
    source = UI_SOURCE.read_text(encoding="utf-8")
    catalogue = source[source.index('<main key={collection}'):source.index('{selectedMovie && (')]
    detail = source[source.index('{selectedMovie && ('):]

    assert "Reprendre la lecture" not in catalogue
    assert "mediaAction.label" in detail
    assert "label: 'Lire'" in source


def test_media_action_labels_are_user_facing_and_cover_pending_states():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "Demander via Seerr" not in source
    assert "Demander ce film" in source
    assert "Demander cette série" in source
    assert "Demande en cours" in source
    assert "Téléchargement en cours" in source
