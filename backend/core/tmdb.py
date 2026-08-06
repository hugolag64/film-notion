import logging
from typing import Optional, Dict, Any, List
from backend.config import Config
from backend.core import http

logger = logging.getLogger(__name__)


class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self):
        if not Config.TMDB_API_KEY:
            raise ValueError("TMDB_API_KEY is not set in configuration")
        self.api_key = Config.TMDB_API_KEY
        # Clé v3 passée en paramètre de requête
        self.params = {"api_key": self.api_key, "language": "fr-FR"}

    async def search_movie(self, query: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Recherche des films par titre. Retourne les 5 premiers résultats."""
        url = f"{self.BASE_URL}/search/movie"
        params = {**self.params, "query": query}
        if year:
            params["year"] = year

        try:
            response = await http.request_with_retry("GET", url, params=params)
            response.raise_for_status()
            results = response.json().get("results", [])
            query_key = query.strip().casefold()
            results.sort(key=lambda result: 0 if (
                (result.get("title") or result.get("original_title") or "").strip().casefold() == query_key
            ) else 1)
            return results[:20]
        except Exception as e:
            logger.error("Erreur recherche film '%s': %s", query, e)
            return []

    async def search_tv(self, query: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Recherche des séries par titre. Résultats normalisés (title/release_date)."""
        url = f"{self.BASE_URL}/search/tv"
        params = {**self.params, "query": query}
        if year:
            params["first_air_date_year"] = year

        try:
            response = await http.request_with_retry("GET", url, params=params)
            response.raise_for_status()
            results = response.json().get("results", [])
            return [self._normalize_tv(r) for r in results[:5]]
        except Exception as e:
            logger.error("Erreur recherche série '%s': %s", query, e)
            return []

    async def search_person(self, query: str) -> List[Dict[str, Any]]:
        """Recherche des personnes (notamment les acteurs) dans TMDB."""
        url = f"{self.BASE_URL}/search/person"
        params = {**self.params, "query": query}
        try:
            response = await http.request_with_retry("GET", url, params=params)
            response.raise_for_status()
            return response.json().get("results", [])[:8]
        except Exception as e:
            logger.error("Erreur recherche personne '%s': %s", query, e)
            return []

    async def discover_movies(
        self,
        *,
        with_genres: Optional[List[int]] = None,
        page: int = 1,
        sort_by: str = "popularity.desc",
        min_vote_count: int = 50,
    ) -> List[Dict[str, Any]]:
        """Discover French-language movie candidates for recommendations."""
        url = f"{self.BASE_URL}/discover/movie"
        params = {
            **self.params,
            "page": page,
            "sort_by": sort_by,
            "vote_count.gte": min_vote_count,
        }
        if with_genres:
            params["with_genres"] = "|".join(str(genre_id) for genre_id in with_genres)
        try:
            response = await http.request_with_retry("GET", url, params=params)
            response.raise_for_status()
            return [
                {
                    "tmdb_id": result.get("id"),
                    "title": result.get("title") or result.get("original_title") or "Sans titre",
                    "overview": result.get("overview") or "",
                    "genre_ids": result.get("genre_ids") or [],
                    "release_date": result.get("release_date") or None,
                    "vote_average": float(result.get("vote_average") or 0),
                    "popularity": float(result.get("popularity") or 0),
                    "poster_path": result.get("poster_path"),
                    "backdrop_path": result.get("backdrop_path"),
                }
                for result in response.json().get("results", [])
                if result.get("id")
            ]
        except Exception as error:
            logger.error("Erreur découverte TMDB : %s", error)
            return []

    async def search(self, query: str, is_series: bool = False, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Dispatch film/série."""
        return await (self.search_tv(query, year) if is_series else self.search_movie(query, year))

    @staticmethod
    def _normalize_tv(r: Dict[str, Any]) -> Dict[str, Any]:
        """Aligne un résultat TV sur la forme des films (title / release_date)."""
        r = dict(r)
        r["title"] = r.get("name") or r.get("title") or ""
        r["release_date"] = r.get("first_air_date") or ""
        r["_media_type"] = "tv"
        return r

    async def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Récupère les détails complets d'un film (genres, runtime, crew pour réalisateur)."""
        url = f"{self.BASE_URL}/movie/{tmdb_id}"
        params = {**self.params, "append_to_response": "credits,release_dates"}

        try:
            response = await http.request_with_retry("GET", url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Erreur détails film TMDB ID %s: %s", tmdb_id, e)
            return None

    async def get_tv_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Récupère les détails d'une série, normalisés sur la forme film."""
        url = f"{self.BASE_URL}/tv/{tmdb_id}"
        params = {**self.params, "append_to_response": "credits"}
        try:
            response = await http.request_with_retry("GET", url, params=params)
            response.raise_for_status()
            data = response.json()
            data["_media_type"] = "tv"
            # Aligne les champs utilisés par le reste du code
            data.setdefault("title", data.get("name"))
            data.setdefault("release_date", data.get("first_air_date"))
            return data
        except Exception as e:
            logger.error("Erreur détails série TMDB ID %s: %s", tmdb_id, e)
            return None

    async def get_tv_season_details(
        self, tmdb_id: int, season_number: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a TV season's episodes."""
        url = f"{self.BASE_URL}/tv/{tmdb_id}/season/{season_number}"
        try:
            response = await http.request_with_retry("GET", url, params=self.params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("TMDB season details failed for %s/%s: %s", tmdb_id, season_number, e)
            return None

    async def get_details(self, tmdb_id: int, is_series: bool = False) -> Optional[Dict[str, Any]]:
        return await (self.get_tv_details(tmdb_id) if is_series else self.get_movie_details(tmdb_id))

    # --- Helpers purs (pas d'I/O, travaillent sur un dict déjà récupéré) ---

    def get_director(self, details: Dict[str, Any]) -> Optional[str]:
        """Réalisateur (film) ou créateur (série)."""
        if details.get("_media_type") == "tv" or details.get("created_by"):
            creators = details.get("created_by") or []
            if creators:
                return creators[0].get("name")
        crew = details.get("credits", {}).get("crew", [])
        for member in crew:
            if member.get("job") == "Director":
                return member.get("name")
        return None

    def get_genres(self, movie_details: Dict[str, Any]) -> List[str]:
        """Extrait les noms des genres."""
        return [g.get("name") for g in movie_details.get("genres", [])]

    @staticmethod
    def poster_url_from_path(poster_path: Optional[str], size: str = "w500") -> Optional[str]:
        """Construit l'URL d'affiche à partir d'un poster_path brut."""
        if poster_path:
            return f"https://image.tmdb.org/t/p/{size}{poster_path}"
        return None

    def get_poster_url(self, movie_details: Dict[str, Any]) -> Optional[str]:
        """Construit l'URL complète de l'affiche à partir des détails d'un film."""
        return self.poster_url_from_path(movie_details.get("poster_path"))

    def get_backdrop_url(self, movie_details: Dict[str, Any]) -> Optional[str]:
        """Construit l'URL complète de l'image de bannière horizontale (backdrop)."""
        return self.poster_url_from_path(movie_details.get("backdrop_path"), size="w1280")

    def get_cast(self, movie_details: Dict[str, Any], limit: int = 5) -> List[str]:
        """Extrait les noms des acteurs principaux du film/série."""
        credits = movie_details.get("credits", {})
        cast = credits.get("cast", [])
        return [member.get("name") for member in cast[:limit] if member.get("name")]
