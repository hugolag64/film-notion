from datetime import date

from backend.core.cache_service import CacheService
from backend.core.models import Media


def _media(**kw):
    base = dict(id="page-1", title="Dune", release_date=date(2021, 1, 1))
    base.update(kw)
    return Media(**base)


def _cache(tmp_path):
    CacheService.CACHE_FILE = str(tmp_path / "cache.json")
    return CacheService()


def test_hash_is_stable(tmp_path):
    c = _cache(tmp_path)
    assert c._content_hash(_media()) == c._content_hash(_media())


def test_hash_changes_when_content_changes(tmp_path):
    c = _cache(tmp_path)
    h1 = c._content_hash(_media())
    h2 = c._content_hash(_media(director="Denis Villeneuve"))
    assert h1 != h2


def test_processed_detected_only_for_same_content(tmp_path):
    c = _cache(tmp_path)
    m = _media()
    assert c.is_processed(m) is False
    c.mark_as_processed(m)
    assert c.is_processed(m) is True
    # La fiche change côté Notion -> doit être re-traitée
    assert c.is_processed(_media(synopsis="nouveau")) is False


def test_invalidate_and_clear(tmp_path):
    c = _cache(tmp_path)
    m = _media()
    c.mark_as_processed(m)
    c.invalidate(m.id)
    assert c.is_processed(m) is False
    c.mark_as_processed(m)
    c.clear()
    assert c.is_processed(m) is False
