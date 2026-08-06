from pathlib import Path


UI_SOURCE = Path(__file__).parents[1] / "proto-ui" / "src" / "BackstagePrototype.jsx"
ACCOUNT_SOURCE = Path(__file__).parents[1] / "proto-ui" / "src" / "AccountPanel.jsx"
API_SOURCE = Path(__file__).parents[1] / "proto-ui" / "src" / "api.js"


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
    assert "Indexation Jellyfin en cours" in source
    assert "mediaAction.canPlay ? '▶' : '+'" not in source
    assert "user?.role === 'admin'" in source
    assert "Demander à conserver" in source
    assert "fetchRentals" in source


def test_retention_admin_controls_and_notifications_are_present():
    source = UI_SOURCE.read_text(encoding="utf-8")
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Demandes de conservation" in account
    assert "Conserver définitivement" in account
    assert "Refuser" in account
    assert "Prolonger de 7 jours" in account
    assert "Conservé définitivement" in source
    assert "fetchKeepRequests" in api
    assert "fetchNotifications" in api
