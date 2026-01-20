import os
import re
import unicodedata

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov")


# =========================
# Normalisation des titres
# =========================
def normalize_title(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\([^)]*\)", "", text)   # supprime (2010), etc.
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def extract_year(text: str) -> str | None:
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None


# =========================
# Scan NAS
# =========================
def scan_nas_movies(base_path: str) -> list[dict]:
    """
    Retourne une liste de films présents sur le NAS :
    [
        {
            "path": "H:\\Movies\\Inception (2010).mkv",
            "filename": "Inception (2010).mkv",
            "normalized": "inception",
            "year": "2010"
        }
    ]
    """
    movies = []

    for root, _, files in os.walk(base_path):
        for f in files:
            if f.lower().endswith(VIDEO_EXTS):
                full_path = os.path.join(root, f)

                movies.append({
                    "path": full_path,
                    "filename": f,
                    "normalized": normalize_title(f),
                    "year": extract_year(f),
                })

    return movies
