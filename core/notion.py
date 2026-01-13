from datetime import datetime
import time
from config import notion, DATABASE_ID


# =========================
# Récupération des pages
# =========================

def fetch_all_pages():
    pages = []
    cursor = None

    while True:
        response = notion.databases.query(
            database_id=DATABASE_ID,
            start_cursor=cursor
        )

        pages.extend(response.get("results", []))

        if not response.get("has_more"):
            break

        cursor = response.get("next_cursor")

    return pages


# =========================
# Sélecteurs métier
# =========================

def get_title(page):
    title_prop = page["properties"].get("Nom", {}).get("title")
    if title_prop:
        return title_prop[0]["text"]["content"]
    return None


def is_tmdb_done(page) -> bool:
    return page["properties"].get("TMDB_OK", {}).get("checkbox", False)


def get_release_date(page):
    date_prop = page["properties"].get("Date de sortie", {}).get("date")
    if date_prop and date_prop.get("start"):
        return datetime.strptime(date_prop["start"][:10], "%Y-%m-%d")
    return None


def get_movies_to_enrich(pages):
    """Films sans enrichissement TMDB"""
    return [
        page for page in pages
        if not is_tmdb_done(page)
    ]


def get_movies_without_tags(pages):
    """Films enrichis TMDB mais sans tags (resync one-shot)"""
    movies = []

    for page in pages:
        if not is_tmdb_done(page):
            continue

        categories = page["properties"].get("Catégorie", {}).get("multi_select", [])
        tags = page["properties"].get("Tags", {}).get("multi_select", [])

        if categories and not tags:
            movies.append(page)

    return movies


# =========================
# TAGS AUTOMATIQUES
# =========================

def compute_tags_from_categories(
    categories: list[str],
    release_year: int | None
) -> list[str]:

    tags = []

    if any(g in categories for g in [
        "Comédie", "Animation", "Familial",
        "Romance", "Musical", "Humour"
    ]):
        tags.append("😌 Détente")

    if any(g in categories for g in [
        "Psychologique", "Drame",
        "Mystère", "Film noir", "Historique"
    ]):
        tags.append("🧠 Complexe")

    if any(g in categories for g in [
        "Horreur", "Guerre",
        "Crime", "Thriller", "Policier"
    ]):
        tags.append("⚠️ Film dur")

    if release_year and release_year < 2000:
        tags.append("🎬 Classique")

    if any(g in categories for g in [
        "Animation", "Familial"
    ]):
        tags.append("👨‍👩‍👧 Familial")

    return tags


# =========================
# Images / Blocs Notion
# =========================

def page_has_image_url(page_id: str, image_url: str) -> bool:
    blocks = notion.blocks.children.list(
        block_id=page_id
    ).get("results", [])

    for block in blocks:
        if block.get("type") == "image":
            ext = block["image"].get("external", {})
            if ext.get("url") == image_url:
                return True

    return False


def add_image_block(
    page_id: str,
    image_url: str,
    *,
    after_block_id: str | None = None
):
    image_block = {
        "object": "block",
        "type": "image",
        "image": {
            "type": "external",
            "external": {"url": image_url}
        }
    }

    if after_block_id:
        notion.blocks.children.append(
            block_id=page_id,
            after=after_block_id,
            children=[image_block]
        )
    else:
        notion.blocks.children.append(
            block_id=page_id,
            children=[image_block]
        )


# =========================
# Cover + Poster (nouveaux films)
# =========================

def add_poster_and_backdrop(
    page_id: str,
    poster_url: str | None,
    backdrop_url: str | None
):
    """
    - Cover Notion = backdrop si dispo, sinon poster
    - Poster vertical ajouté dans la page
    - Aucun doublon
    """

    # 🎨 Cover explicite
    cover_url = backdrop_url or poster_url
    if cover_url:
        notion.pages.update(
            page_id=page_id,
            cover={
                "type": "external",
                "external": {"url": cover_url}
            }
        )

    # 📎 Poster dans le contenu
    if not poster_url or page_has_image_url(page_id, poster_url):
        return

    blocks = notion.blocks.children.list(
        block_id=page_id
    ).get("results", [])

    first_block_id = blocks[0]["id"] if blocks else None

    add_image_block(
        page_id,
        poster_url,
        after_block_id=first_block_id
    )

    time.sleep(0.25)


# =========================
# RESYNC COVERS (films existants)
# =========================

def set_page_cover(page_id: str, image_url: str):
    notion.pages.update(
        page_id=page_id,
        cover={
            "type": "external",
            "external": {"url": image_url}
        }
    )


def resync_covers_from_backdrop(pages: list[dict]):
    """
    One-shot safe :
    - si la page a déjà une cover → on ne touche pas
    - sinon, si une image backdrop existe → on la met en cover
    """

    for page in pages:
        if page.get("cover"):
            continue

        page_id = page["id"]

        blocks = notion.blocks.children.list(
            block_id=page_id
        ).get("results", [])

        for block in blocks:
            if block.get("type") != "image":
                continue

            ext = block["image"].get("external", {})
            url = ext.get("url", "")

            # Heuristique simple : image large = backdrop
            if "w780" in url or "original" in url:
                set_page_cover(page_id, url)
                time.sleep(0.25)
                break


# =========================
# Mise à jour Notion
# =========================

def update_movie_page(
    page_id: str,
    *,
    title: str,
    synopsis: str,
    genres: list[str],
    tags: list[str],
    director: str,
    release_date: datetime | None,
    support: str,
    status: str = "À regarder"
):
    properties = {
        "Type": {"select": {"name": "Film"}},
        "Nom": {"title": [{"text": {"content": title}}]},
        "Synopsis": {"rich_text": [{"text": {"content": synopsis}}]},
        "Réalisateur": {"rich_text": [{"text": {"content": director}}]},
        "Statut": {"select": {"name": status}},
        "Support": {"select": {"name": support}},
        "TMDB_OK": {"checkbox": True},
    }

    if genres:
        properties["Catégorie"] = {
            "multi_select": [{"name": g} for g in genres]
        }

    if tags:
        properties["Tags"] = {
            "multi_select": [{"name": t} for t in tags]
        }

    if release_date:
        properties["Date de sortie"] = {
            "date": {"start": release_date.strftime("%Y-%m-%d")}
        }

    notion.pages.update(
        page_id=page_id,
        properties=properties
    )
