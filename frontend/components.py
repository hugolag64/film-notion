from typing import Any, Optional

from nicegui import ui


def media_poster(cover_url: Optional[str], *, height: str = "160px") -> None:
    """Affiche le poster TMDB si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if cover_url:
        ui.image(cover_url).classes("rounded w-full").style(f"height:{height}; object-fit:cover;")
    else:
        with ui.element("div").classes("bs-poster-placeholder w-full").style(f"height:{height};"):
            ui.icon("movie", size="2rem").classes("opacity-70")


def media_card(media: Any) -> None:
    """Carte poster + titre + badge année/type, partagée par le dashboard et la bibliothèque."""
    with ui.element("div").classes("bs-card p-2"):
        media_poster(media.cover_url, height="140px")
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")


def source_badge(source: str) -> None:
    color = "#7a2331" if source == "manual" else "#c9a35c"
    ui.badge("Manuel" if source == "manual" else "Auto", color=color)
