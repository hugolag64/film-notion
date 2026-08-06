import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend import api
from backend.auth_api import AuthContext
from backend.core.models import RecommendationSession
from backend.core.recommendations import RecommendationCandidate
from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def current_user(user_id="hugo", role="user"):
    return AuthContext(user={"id": user_id, "role": role}, session_id="auth", token="token")


def test_normal_user_is_rejected_after_two_daily_sessions(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    candidates = [RecommendationCandidate(tmdb_id=1, title="A", score=1), RecommendationCandidate(tmdb_id=2, title="B", score=.9)]
    monkeypatch.setattr(api, "_recommendation_pool", lambda *args: asyncio.sleep(0, result=candidates))
    current = current_user()
    asyncio.run(api.start_recommendation_session(current, store))
    asyncio.run(api.start_recommendation_session(current, store))
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.start_recommendation_session(current, store))
    assert error.value.status_code == 429


def test_admin_is_unlimited_and_quota_is_user_scoped(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    for index in range(3):
        asyncio.run(store.create_recommendation_session(RecommendationSession(
            id=f"h{index}", backstage_user_id="hugo", created_at=datetime.now(timezone.utc),
        )))
    candidates = [RecommendationCandidate(tmdb_id=1, title="A", score=1), RecommendationCandidate(tmdb_id=2, title="B", score=.9)]
    monkeypatch.setattr(api, "_recommendation_pool", lambda *args: asyncio.sleep(0, result=candidates))
    result = asyncio.run(api.start_recommendation_session(current_user("admin", "admin"), store))
    assert result["quota"]["unlimited"] is True
    assert result["quota"]["remaining"] is None


def test_quota_resets_at_europe_paris_midnight(tmp_path):
    store = make_store(tmp_path)
    asyncio.run(store.create_recommendation_session(RecommendationSession(
        id="s1", backstage_user_id="hugo", created_at=datetime(2026, 8, 6, 21, 59, tzinfo=timezone.utc),
    )))
    before = api._recommendation_quota(current_user(), store, datetime(2026, 8, 6, 21, 59, tzinfo=timezone.utc))
    after = api._recommendation_quota(current_user(), store, datetime(2026, 8, 6, 22, 1, tzinfo=timezone.utc))
    assert before["used"] == 1
    assert after["used"] == 0
