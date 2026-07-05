from typing import Optional

from nicegui import ui


def media_poster(cover_url: Optional[str], *, height: str = "160px") -> None:
    """Affiche le poster TMDB si disponible, sinon un placeholder dégradé cohérent avec le thème."""
    if cover_url:
        ui.image(cover_url).classes("rounded w-full").style(f"height:{height}; object-fit:cover;")
    else:
        with ui.element("div").classes("bs-poster-placeholder w-full").style(f"height:{height};"):
            ui.icon("movie", size="2rem").classes("opacity-70")
