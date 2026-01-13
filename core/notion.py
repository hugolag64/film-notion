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
    """
    Films sans enrichissement TMDB
    """
    return [
        page for page in pages
        if not is_tmdb_done(page)
    ]


def get_existing_tags(page) -> list[str]:
    """
    Récupère les tags déjà présents dans Notion
    """
    return [
        t["name"]
        for t in page["properties"]
        .get("Tags", {})
        .get("multi_select", [])
    ]


def get_movies_without_tags(pages):
    """
    Films déjà enrichis TMDB MAIS sans tags
    (utilisé UNIQUEMENT pour le resync one-shot)
    """
    movies = []

    for page in pages:
        if not is_tmdb_done(page):
            continue

        categories = page["properties"] \
            .get("Catégorie", {}) \
            .get("multi_select", [])

        tags = page["properties"] \
            .get("Tags", {}) \
            .get("multi_select", [])

        if categories and not tags:
            movies.append(page)

    return movies

def compute_meta_tags(movie: dict, results_count: int) -> list[str]:
    """
    Tags méta basés sur TMDB
    """
    tags = []

    rating = movie.get("vote_average", 0)
    votes = movie.get("vote_count", 0)
    popularity = movie.get("popularity", 0)

    if rating >= 7.8 and votes >= 5000:
        tags.append("⭐ Incontournable")

    if rating <= 6 and votes >= 2000:
        tags.append("⚠️ Surcoté")

    if votes < 500:
        tags.append("👀 Peu connu")

    if popularity >= 80:
        tags.append("🔥 Populaire")

    if results_count == 1:
        tags.append("🎯 Correspondance parfaite")

    return tags

# =========================
# TAGS AUTOMATIQUES
# =========================

def compute_tags_from_categories(
    categories: list[str],
    release_year: int | None
) -> list[str]:
    """
    Déduit automatiquement des TAGS à partir
    des catégories TMDB / Notion
    """

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


def add_poster_and_backdrop(
    page_id: str,
    poster_url: str | None,
    backdrop_url: str | None
):
    blocks = notion.blocks.children.list(
        block_id=page_id
    ).get("results", [])

    first_block_id = blocks[0]["id"] if blocks else None
    last_inserted_id = None

    if poster_url and not page_has_image_url(page_id, poster_url):
        add_image_block(page_id, poster_url, after_block_id=first_block_id)
        time.sleep(0.25)

        new_blocks = notion.blocks.children.list(
            block_id=page_id
        ).get("results", [])

        if new_blocks:
            last_inserted_id = new_blocks[0]["id"]

    if backdrop_url and not page_has_image_url(page_id, backdrop_url):
        add_image_block(
            page_id,
            backdrop_url,
            after_block_id=last_inserted_id or first_block_id
        )


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
