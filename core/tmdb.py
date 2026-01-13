from math import log10
from config import TMDB_API_KEY
from utils.text import clean_search_title, similarity
from utils.request import safe_get_json

def search_movie(title, year=None, language="fr-FR"):
    url = (
        "https://api.themoviedb.org/3/search/movie"
        f"?api_key={TMDB_API_KEY}&query={title}&language={language}"
    )
    if year:
        url += f"&year={year}"
    return safe_get_json(url).get("results", [])

def score_movie(movie, query):
    sim = max(
        similarity(clean_search_title(movie.get("title", "")), query),
        similarity(clean_search_title(movie.get("original_title", "")), query)
    )
    pop = movie.get("popularity", 0) / 100
    vote = movie.get("vote_average", 0) / 10
    cnt = log10(1 + movie.get("vote_count", 0)) / 4
    return 3*sim + 1.6*vote + 0.9*pop + 0.6*cnt
