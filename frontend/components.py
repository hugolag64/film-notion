from typing import Any, Callable, Optional

from nicegui import ui


def rating_badge_text(media: Any) -> Optional[str]:
    """Texte du badge note, ex. '⭐ 8/10', ou None si aucune note."""
    return f"⭐ {media.rating}" if media.rating else None


def primary_genre(media: Any) -> Optional[str]:
    """Première catégorie du média (genre principal), ou None si absente."""
    return media.categories[0] if media.categories else None


def media_poster(cover_url: Optional[str], *, height: str = "160px") -> None:
    """Affiche le poster TMDB si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if cover_url:
        ui.image(cover_url).classes("rounded w-full").style(f"height:{height}; object-fit:cover;")
    else:
        with ui.element("div").classes("bs-poster-placeholder w-full").style(f"height:{height};"):
            ui.icon("movie", size="2rem").classes("opacity-70")


def media_card(media: Any, *, on_click: Optional[Callable[[], None]] = None) -> None:
    """Carte poster + titre + badges année/type/note/genre, partagée par le dashboard et la bibliothèque."""
    card = ui.element("div").classes("bs-card p-2")
    if on_click is not None:
        card.classes("cursor-pointer").on("click", on_click)
    with card:
        media_poster(media.cover_url, height="140px")
        ui.label(media.title).classes("bs-title text-sm mt-2")
        year = media.release_date.year if media.release_date else "—"
        ui.badge(f"{year} · {media.type or '?'}").classes("bs-badge mt-1")

        rating_text = rating_badge_text(media)
        genre_text = primary_genre(media)
        if rating_text or genre_text:
            with ui.row().classes("gap-1 mt-1"):
                if rating_text:
                    ui.badge(rating_text).classes("bs-badge-secondary")
                if genre_text:
                    ui.badge(genre_text).classes("bs-badge-secondary")


def source_badge(source: str) -> None:
    color = "#7a2331" if source == "manual" else "#c9a35c"
    ui.badge("Manuel" if source == "manual" else "Auto", color=color)
