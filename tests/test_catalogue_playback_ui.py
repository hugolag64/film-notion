from pathlib import Path


ROOT = Path(__file__).parents[1]
UI_SOURCE = ROOT / "proto-ui" / "src" / "BackstagePrototype.jsx"
ACCOUNT_SOURCE = ROOT / "proto-ui" / "src" / "AccountPanel.jsx"
ADMIN_SOURCE = ROOT / "proto-ui" / "src" / "components" / "AdminCenter.jsx"
USER_MANAGEMENT_SOURCE = ROOT / "proto-ui" / "src" / "components" / "UserManagement.jsx"
API_SOURCE = ROOT / "proto-ui" / "src" / "api.js"


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
    assert "Demander cette série" in source or "Demander cette sÃ©rie" in source
    assert "Demande en cours" in source
    assert "Téléchargement en cours" in source or "TÃ©lÃ©chargement en cours" in source
    assert "Indexation Jellyfin en cours" in source
    assert "mediaAction.canPlay ? '▶' : '+'" not in source
    assert "user?.role === 'admin'" in source
    assert "Demander à conserver" in source or "Demander Ã  conserver" in source
    assert "fetchRentals" in source


def test_retention_admin_controls_and_notifications_are_present():
    source = UI_SOURCE.read_text(encoding="utf-8")
    admin = ADMIN_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Demandes de conservation" in admin
    assert "Conserver" in admin
    assert "Refuser" in admin
    assert "Prolonger" in admin
    assert "Conserv" in source
    assert "fetchKeepRequests" in api
    assert "fetchNotifications" in api


def test_cleanup_simulation_is_available_to_admins():
    admin = ADMIN_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Aperçu du nettoyage" in admin
    assert "aucune suppression automatique" in admin
    assert "fetchCleanupPreview" in api


def test_storage_quota_controls_are_visible():
    admin = ADMIN_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Stockage et quotas" in admin
    assert "fetchStorageStatus" in api


def test_admin_dashboard_controls_are_visible():
    admin = ADMIN_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Expirations proches" in admin
    assert "Téléchargements" in admin
    assert "fetchAdminDashboard" in api


def test_notification_center_supports_automatic_events():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")

    assert "Mes notifications" in account
    assert "notification.message" in account


def test_admin_backup_controls_are_visible():
    admin = ADMIN_SOURCE.read_text(encoding="utf-8")
    api = API_SOURCE.read_text(encoding="utf-8")

    assert "Sauvegarde" in admin
    assert "Sauvegarder maintenant" in admin
    assert "fetchBackupStatus" in api
    assert "verifyBackup" in api


def test_account_panel_contains_only_personal_controls():
    account = ACCOUNT_SOURCE.read_text(encoding="utf-8")

    assert "Mes appareils mémorisés" in account
    assert "Demandes de conservation" not in account
    assert "Sauvegarde" not in account
    assert "Espace de stockage" not in account


def test_admin_user_management_is_interactive_and_complete():
    admin = ADMIN_SOURCE.read_text(encoding="utf-8")
    users = USER_MANAGEMENT_SOURCE.read_text(encoding="utf-8")

    assert "UserManagement" in admin
    assert "aria-expanded={expanded}" in users
    assert "onClick={() => setExpandedUserId" in users
    assert "Créer un utilisateur" in users
    assert "Supprimer" in users
    assert "Un administrateur ne peut pas supprimer son propre compte." in users


def test_catalogue_refreshes_after_server_action():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "syncMediaServer" in source
    assert "await loadRealMedias()" in source


def test_acquisition_defaults_are_used_and_non_admin_options_are_filtered():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "default_quality_profile_id" in source
    assert "user?.role === 'admin'" in source


def test_availability_is_refreshed_periodically_with_cleanup():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "setInterval" in source
    assert "clearInterval" in source


def test_series_detail_uses_the_centered_film_detail_shell():
    source = UI_SOURCE.read_text(encoding="utf-8")
    series = source[source.index("{selectedSeries && ("):source.index("{/* TMDB Search & Relink Modal */}")]

    assert "<FilmDetailView" in series
    assert "FICHE SÉRIE" in series
    assert "Statut & support de stockage" in series


def test_series_detail_keeps_details_and_episodes_tabs():
    source = UI_SOURCE.read_text(encoding="utf-8")
    series = source[source.index("{selectedSeries && ("):source.index("{/* TMDB Search & Relink Modal */}")]

    assert "Détails" in series
    assert "Épisodes" in series
    assert "groupEpisodesBySeason" in source
