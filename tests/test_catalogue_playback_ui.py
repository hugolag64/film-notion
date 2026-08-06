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


def test_cleanup_simulation_is_available_to_admins():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Aperçu du nettoyage (simulation)" in account
    assert "Aucune suppression réelle" in account
    assert "fetchCleanupPreview" in api


def test_storage_quota_controls_are_visible():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Espace de stockage" in account
    assert "fetchStorageStatus" in api


def test_admin_dashboard_controls_are_visible():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Tableau de bord administrateur" in account
    assert "Expirations proches" in account
    assert "Téléchargements en cours" in account
    assert "fetchAdminDashboard" in api


def test_notification_center_supports_automatic_events():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")

    assert "Notifications" in account
    assert "notification.message" in account


def test_admin_backup_controls_are_visible():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Sauvegarde" in account
    assert "Sauvegarder maintenant" in account
    assert "fetchBackupStatus" in api
    assert "verifyBackup" in api
