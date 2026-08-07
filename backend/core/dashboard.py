"""Pure data shaping for the authenticated home dashboard."""

from datetime import datetime
from typing import Any

from backend.core.media_server import Availability
from backend.core.models import Media, Notification, Rental, UserMediaState
from backend.core.playback import PlaybackProgress


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _media_card(media: Media) -> dict[str, Any]:
    return {
        "id": media.id,
        "title": media.title,
        "type": media.type,
        "cover_url": media.cover_url,
        "backdrop_url": media.backdrop_url,
        "release_date": media.release_date.isoformat() if media.release_date else None,
    }


def _activity_item(
    item_id: str,
    kind: str,
    label: str,
    title: str,
    created_at: datetime | None,
    media_id: str | None = None,
) -> dict[str, Any] | None:
    if not created_at:
        return None
    return {
        "id": item_id,
        "kind": kind,
        "label": label,
        "title": title,
        "media_id": media_id,
        "created_at": created_at.isoformat(),
    }


def _availability_state_label(state: str) -> str:
    return {
        "available": "Disponible",
        "downloading": "Téléchargement",
        "error": "Erreur",
        "requested": "Demande en cours",
        "searching": "Recherche en cours",
        "imported": "Indexation en cours",
    }.get(state, "Demande possible")


def build_dashboard_payload(
    medias: list[Media],
    states: list[UserMediaState],
    playback: list[PlaybackProgress],
    availabilities: list[Availability],
    rentals: list[Rental],
    notifications: list[Notification],
    recommendations: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Join user-scoped data into the small, stable dashboard response contract."""
    media_by_id = {media.id: media for media in medias}
    continue_watching = []
    for progress in playback:
        if progress.played or progress.percent >= 95:
            continue
        continue_watching.append({
            **progress.model_dump(mode="json"),
            "media": _media_card(media_by_id[progress.media_id]) if progress.media_id in media_by_id else None,
        })
    continue_watching.sort(key=lambda item: item.get("last_played_at") or "", reverse=True)

    activity: list[dict[str, Any]] = []
    for media in medias:
        item = _activity_item(
            f"media-added-{media.id}", "media_added", "Ajouté à la bibliothèque",
            media.title, media.created_at, media.id,
        )
        if item:
            activity.append(item)
    for state in states:
        media = media_by_id.get(state.media_id)
        if not media:
            continue
        if state.is_watchlist:
            label = "Ajouté à la watchlist"
        elif state.is_favorite:
            label = "Ajouté aux favoris"
        elif state.rating:
            label = "Noté"
        else:
            label = "Bibliothèque mise à jour"
        item = _activity_item(
            f"media-interacted-{state.media_id}", "media_interacted", label,
            media.title, state.last_interacted_at, state.media_id,
        )
        if item:
            activity.append(item)
    for availability in availabilities:
        media = media_by_id.get(availability.media_id)
        if not media:
            continue
        item = _activity_item(
            f"availability-{availability.media_id}", "availability", _availability_state_label(availability.state),
            media.title, availability.last_synced_at, availability.media_id,
        )
        if item:
            activity.append(item)
    for rental in rentals:
        media = media_by_id.get(rental.media_id)
        if not media:
            continue
        label = "Téléchargement disponible" if rental.status == "available" else "Demande de téléchargement"
        item = _activity_item(
            f"rental-{rental.id}", "rental", label, media.title,
            rental.updated_at, rental.media_id,
        )
        if item:
            activity.append(item)
    for notification in notifications:
        item = _activity_item(
            f"notification-{notification.id}", "notification", "Notification",
            notification.message, notification.created_at,
        )
        if item:
            activity.append(item)
    activity.sort(key=lambda item: item["created_at"], reverse=True)

    availability_payload = []
    for item in sorted(
        availabilities,
        key=lambda value: value.last_synced_at or datetime.min,
        reverse=True,
    )[:8]:
        media = media_by_id.get(item.media_id)
        if not media:
            continue
        availability_payload.append({
            "media_id": item.media_id,
            "title": media.title,
            "poster": media.cover_url,
            "state": item.state,
            "status_label": _availability_state_label(item.state),
            "progress_percent": item.progress_percent,
            "last_error": item.last_error,
            "updated_at": _iso(item.last_synced_at),
        })

    timestamps = [
        item.last_played_at for item in playback if item.last_played_at
    ] + [
        item.last_synced_at for item in availabilities if item.last_synced_at
    ]
    latest_sync = max(timestamps) if timestamps else None
    return {
        "continue_watching": continue_watching[:6],
        "recommendations": recommendations[:8],
        "activity": activity[:10],
        "availability": availability_payload,
        "last_synced_at": _iso(latest_sync or now),
    }
