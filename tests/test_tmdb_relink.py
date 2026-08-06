from datetime import date
import asyncio
import csv

from backend.core.models import Media
from backend.core.store import MediaStore
from backend.core.tmdb_relink import build_relink_updates, select_confident_match
from backend.scripts.relink_tmdb import relink_missing_tmdb_ids


def _media(**overrides) -> Media:
    return Media(id="local-id", type="Film", title=overrides.pop("title", "Dune"), **overrides)


def test_selects_an_exact_title_with_the_same_year():
    media = _media(release_date=date(2021, 10, 22))
    candidates = [
        {"id": 438631, "title": "Dune", "release_date": "1984-12-14"},
        {"id": 4386310, "title": "Dune", "release_date": "2021-10-22"},
    ]

    assert select_confident_match(media, candidates) == candidates[1]


def test_leaves_homonymous_title_without_a_year_for_manual_review():
    media = _media()
    candidates = [
        {"id": 438631, "title": "Dune", "release_date": "1984-12-14"},
        {"id": 4386310, "title": "Dune", "release_date": "2021-10-22"},
    ]

    assert select_confident_match(media, candidates) is None


def test_accepts_accent_and_punctuation_differences_for_one_result():
    media = _media(title="L'Auberge espagnole")
    candidates = [{"id": 123, "title": "L Auberge Espagnole", "release_date": "2002-05-17"}]

    assert select_confident_match(media, candidates) == candidates[0]


def test_relink_does_not_turn_tmdb_score_into_personal_rating():
    media = _media(rating=None)

    updates = build_relink_updates(
        media,
        {
            "title": "Dune",
            "vote_average": 9.1,
            "genres": [],
            "credits": {"cast": [], "crew": []},
        },
        FakeTMDB(),
        123,
    )

    assert updates["rating"] is None


class FakeTMDB:
    async def search(self, title, is_series, year=None):
        if title == "Dune":
            return [{"id": 2, "title": "Dune", "release_date": "2021-10-22"}]
        return [
            {"id": 3, "title": "The Office", "release_date": "2001-07-09"},
            {"id": 4, "title": "The Office", "release_date": "2005-03-24"},
        ]

    async def get_details(self, tmdb_id, is_series):
        return {
            "title": "Dune", "original_title": "Dune", "release_date": "2021-10-22",
            "overview": "Un film.", "genres": [{"name": "Science-Fiction"}],
            "credits": {"cast": [{"name": "Timothée Chalamet"}], "crew": []},
        }

    def get_poster_url(self, details):
        return None

    def get_backdrop_url(self, details):
        return None

    def get_cast(self, details, limit=5):
        return [member["name"] for member in details["credits"]["cast"][:limit]]

    def get_director(self, details):
        return None

    def get_genres(self, details):
        return [genre["name"] for genre in details["genres"]]


def test_batch_relink_applies_only_confident_matches_and_reports_other_cases(tmp_path):
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    linked = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    asyncio.run(store.create({"title": "The Office", "type": "Série"}))
    existing = asyncio.run(store.create({"title": "Déjà relié", "type": "Film", "tmdb_id": 99}))
    report_path = tmp_path / "tmdb-a-verifier.csv"

    summary = asyncio.run(relink_missing_tmdb_ids(store, FakeTMDB(), apply=True, report_path=report_path))

    assert summary == {"linked": 1, "to_review": 1, "already_linked": 1}
    assert asyncio.run(store.fetch_one(linked.id)).tmdb_id == 2
    assert asyncio.run(store.fetch_one(existing.id)).tmdb_id == 99
    with report_path.open(encoding="utf-8", newline="") as report:
        rows = list(csv.DictReader(report))
    assert rows[0]["title"] == "The Office"
    assert rows[0]["reason"] == "ambiguous"
    assert "3: The Office (2001)" in rows[0]["candidates"]


def test_manual_relink_uses_tv_details_for_a_series(tmp_path, monkeypatch):
    from backend import api

    class TVTMDB(FakeTMDB):
        async def get_details(self, tmdb_id, is_series):
            assert is_series is True
            return await self.get_tv_details(tmdb_id)

        async def get_tv_details(self, tmdb_id):
            assert tmdb_id == 77
            return {
                "name": "Severance", "original_name": "Severance",
                "first_air_date": "2022-02-18", "overview": "Une série.",
                "genres": [], "credits": {"cast": [], "crew": []}, "created_by": [],
            }

        async def get_movie_details(self, tmdb_id):
            raise AssertionError("Une série ne doit pas utiliser les détails film")

    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    series = asyncio.run(store.create({"title": "Severance", "type": "Série"}))
    monkeypatch.setattr(api, "TMDBClient", TVTMDB)

    relinked = asyncio.run(api.relink_tmdb(series.id, api.RelinkTMDBRequest(tmdb_id=77), store))

    assert relinked.tmdb_id == 77
    assert relinked.title == "Severance"
