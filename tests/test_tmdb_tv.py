from backend.core.tmdb import TMDBClient


def _bare():
    return object.__new__(TMDBClient)


def test_normalize_tv_aligns_fields():
    r = TMDBClient._normalize_tv({
        "id": 1, "name": "Severance", "first_air_date": "2022-02-18", "poster_path": "/x.jpg",
    })
    assert r["title"] == "Severance"
    assert r["release_date"] == "2022-02-18"
    assert r["_media_type"] == "tv"


def test_get_director_movie_uses_crew():
    c = _bare()
    details = {"credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]}}
    assert c.get_director(details) == "Denis Villeneuve"


def test_get_director_tv_uses_created_by():
    c = _bare()
    details = {"_media_type": "tv", "created_by": [{"name": "Dan Erickson"}]}
    assert c.get_director(details) == "Dan Erickson"


def test_poster_url_from_path():
    assert TMDBClient.poster_url_from_path("/p.jpg", "w185") == "https://image.tmdb.org/t/p/w185/p.jpg"
    assert TMDBClient.poster_url_from_path(None) is None
