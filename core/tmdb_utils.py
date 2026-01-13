import re
import os
import requests

TMDB_API_KEY = os.getenv("TMDB_API_KEY")


def extract_tmdb_id_from_url(url: str) -> str | None:
    match = re.search(r"/movie/(\d+)", url)
    return match.group(1) if match else None


def extract_imdb_id_from_url(url: str) -> str | None:
    match = re.search(r"/title/(tt\d+)", url)
    return match.group(1) if match else None


def get_movie_by_tmdb_id(tmdb_id: str) -> dict | None:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "fr-FR"
    }

    r = requests.get(url, params=params, timeout=10)
    return r.json() if r.ok else None


def get_tmdb_movie_from_imdb_id(imdb_id: str) -> dict | None:
    url = f"https://api.themoviedb.org/3/find/{imdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "external_source": "imdb_id",
        "language": "fr-FR"
    }

    r = requests.get(url, params=params, timeout=10)
    if not r.ok:
        return None

    data = r.json()
    movies = data.get("movie_results", [])
    return movies[0] if movies else None
