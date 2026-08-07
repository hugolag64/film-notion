from datetime import datetime, timezone

from backend.core.dashboard import build_dashboard_payload
from backend.core.media_server import Availability
from backend.core.models import Media, Notification, Rental, UserMediaState
from backend.core.playback import PlaybackProgress


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def media(media_id, title, created_at):
    return Media(
        id=media_id,
        title=title,
        type="Film",
        cover_url=f"https://img.test/{media_id}.jpg",
        created_at=created_at,
    )


def test_dashboard_only_keeps_unfinished_playback_and_resolves_media():
    medias = [media("m1", "Dune", NOW)]
    playback = [
        PlaybackProgress(
            backstage_user_id="u1", jellyfin_id="j1", media_id="m1",
            title="Dune", percent=42, last_played_at=NOW,
        ),
        PlaybackProgress(
            backstage_user_id="u1", jellyfin_id="j2", media_id="m1",
            title="Finished", percent=96, played=True, last_played_at=NOW,
        ),
    ]

    payload = build_dashboard_payload(
        medias, [], playback, [], [], [], [], NOW,
    )

    assert [item["media_id"] for item in payload["continue_watching"]] == ["m1"]
    assert payload["continue_watching"][0]["media"]["title"] == "Dune"
    assert payload["continue_watching"][0]["percent"] == 42


def test_dashboard_activity_mixes_sources_and_sorts_newest_first():
    older = NOW.replace(hour=8)
    newer = NOW.replace(hour=11)
    medias = [media("m1", "Ajout récent", older)]
    states = [UserMediaState(
        backstage_user_id="u1", media_id="m1", is_watchlist=True,
        last_interacted_at=newer,
    )]
    notifications = [Notification(
        id="n1", backstage_user_id="u1", kind="availability",
        message="Ajout récent est disponible", created_at=NOW.replace(hour=10),
    )]

    payload = build_dashboard_payload(
        medias, states, [], [], [], notifications, [], NOW,
    )

    assert [item["kind"] for item in payload["activity"][:3]] == [
        "media_interacted", "notification", "media_added",
    ]
    assert payload["activity"][0]["media_id"] == "m1"


def test_dashboard_availability_joins_titles_and_preserves_explicit_status():
    medias = [media("m1", "Dune", NOW)]
    availability = [Availability(
        media_id="m1", provider="radarr", state="downloading",
        progress_percent=68, last_synced_at=NOW,
    )]

    payload = build_dashboard_payload(
        medias, [], [], availability, [], [], [], NOW,
    )

    assert payload["availability"] == [{
        "media_id": "m1",
        "title": "Dune",
        "poster": "https://img.test/m1.jpg",
        "state": "downloading",
        "status_label": "Téléchargement",
        "progress_percent": 68,
        "last_error": None,
        "updated_at": NOW.isoformat(),
    }]


def test_dashboard_normalizes_seerr_requests_for_the_request_queue():
    payload = build_dashboard_payload(
        [], [], [], [], [], [], [], NOW,
        requests=[{
            "id": 42,
            "mediaType": "movie",
            "status": 2,
            "media": {
                "tmdbId": 438631,
                "title": "Dune",
                "status": 3,
                "posterPath": "/dune.jpg",
                "progress": 64,
            },
            "createdAt": "2026-08-07T10:00:00Z",
            "updatedAt": "2026-08-07T11:00:00Z",
        }],
    )

    assert payload["requests"] == [{
        "id": 42,
        "tmdb_id": 438631,
        "title": "Dune",
        "media_type": "movie",
        "status": "processing",
        "status_label": "Téléchargement",
        "progress_percent": 64,
        "poster_url": "https://image.tmdb.org/t/p/w342/dune.jpg",
        "created_at": "2026-08-07T10:00:00Z",
        "updated_at": "2026-08-07T11:00:00Z",
        "cancellable": False,
    }]


def test_dashboard_uses_seerr_request_status_when_media_is_still_pending():
    payload = build_dashboard_payload(
        [], [], [], [], [], [], [], NOW,
        requests=[{"id": 7, "status": 1, "media": {"status": 2, "title": "The Odyssey"}}],
    )

    assert payload["requests"][0]["status_label"] == "En attente"
    assert payload["requests"][0]["cancellable"] is True


def test_dashboard_keeps_all_active_seerr_requests_for_the_manager():
    requests = [{"id": index, "media": {"status": 2, "title": f"Film {index}"}} for index in range(1, 10)]

    payload = build_dashboard_payload(
        [], [], [], [], [], [], [], NOW, requests=requests,
    )

    assert len(payload["requests"]) == 9


def test_dashboard_marks_future_release_requests_as_pending():
    payload = build_dashboard_payload(
        [], [], [], [], [], [], [], NOW,
        requests=[{
            "id": 10,
            "media": {"status": 3, "title": "L'Odyssée", "releaseDate": "2099-01-01"},
        }],
    )

    assert payload["requests"][0]["status"] == "pending"
    assert payload["requests"][0]["status_label"] == "En attente"
